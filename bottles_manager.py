#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bottles/Wine Management Script for Arch Linux
Manages Wine bottles via bottles-cli (native or Flatpak).

Security & Performance hardened version.
"""

import copy
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Minimum Python version guard
# ---------------------------------------------------------------------------
if sys.version_info < (3, 12):
    print("ERROR: Python 3.12+ required.", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bottles_manager")

# ---------------------------------------------------------------------------
# ANSI colours
# ---------------------------------------------------------------------------
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    CYAN    = "\033[96m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    DIM     = "\033[2m"

def cprint(color: str, text: str) -> None:
    """Print with ANSI colour."""
    print(f"{color}{text}{C.RESET}")

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
# Bottle names: alphanumeric, hyphens, underscores; 1-63 chars
_BOTTLE_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,62}$")
# Env var: UPPER_CASE_VAR=value
_ENV_VAR_RE: re.Pattern[str] = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}=.{1,512}$")
# Param: key:value  (no shell metacharacters)
_PARAM_RE: re.Pattern[str] = re.compile(r"^[a-z_][a-z0-9_]{0,63}:[^\s;|&<>]{1,128}$")
# Component name: alphanumeric, hyphens, dots (e.g. caffe-7.5, dxvk-2.0)
_COMPONENT_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-\.]{0,127}$")


def validate_bottle_name(name: str) -> str:
    """Validate and return bottle name; raise ValueError on invalid input."""
    if not _BOTTLE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid bottle name '{name}'. "
            "Allowed: A-Z a-z 0-9 _ -  (1-63 chars, must start with alphanumeric)."
        )
    return name


def validate_env_var(var: str) -> str:
    """Validate VAR=value format; raise ValueError on invalid input."""
    if not _ENV_VAR_RE.match(var):
        raise ValueError(
            f"Invalid env var '{var}'. Expected format: UPPER_VAR=value"
        )
    return var


def validate_param(param: str) -> str:
    """Validate key:value param format; raise ValueError on invalid input."""
    if not _PARAM_RE.match(param):
        raise ValueError(
            f"Invalid parameter '{param}'. "
            "Expected format: key:value  (no shell metacharacters)"
        )
    return param


def validate_component(name: str, label: str = "component") -> str:
    """Validate a component name (runner/dxvk/vkd3d etc.)."""
    if not _COMPONENT_RE.match(name):
        raise ValueError(f"Invalid {label} name '{name}'.")
    return name


def validate_executable_path(exe: str) -> str:
    """
    Warn if path looks suspicious (path traversal, unusual extension).
    Does NOT block execution – user knows what they are doing.
    """
    if ".." in exe:
        cprint(C.YELLOW, "  WARNING: Path contains '..'. Verify this is intentional.")
    p = exe.lower()
    if not (p.endswith(".exe") or p.endswith(".msi") or p.endswith(".bat")):
        cprint(C.YELLOW, f"  WARNING: Unusual extension in '{exe}'. Proceed carefully.")
    return exe


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class BottleEnv(StrEnum):
    GAMING      = "gaming"
    APPLICATION = "application"
    CUSTOM      = "custom"


class WinVersion(StrEnum):
    WIN10 = "win10"
    WIN11 = "win11"
    WIN7  = "win7"
    WIN81 = "win81"


class WineTool(StrEnum):
    CMD         = "cmd"
    WINECFG     = "winecfg"
    UNINSTALLER = "uninstaller"
    REGEDIT     = "regedit"
    TASKMGR     = "taskmgr"
    CONTROL     = "control"
    EXPLORER    = "explorer"


# ---------------------------------------------------------------------------
# Bottle preset dataclass
# ---------------------------------------------------------------------------
@dataclass
class BottlePreset:
    """Preset configuration for a new bottle (always deepcopy before use!)."""
    env: BottleEnv
    arch: str = "win64"
    win_version: WinVersion = WinVersion.WIN10
    params: dict[str, Any] = field(default_factory=dict)
    env_vars: dict[str, str] = field(default_factory=dict)
    description: str = ""


# ---------------------------------------------------------------------------
# Predefined presets  (immutable templates – ALWAYS deepcopy before mutating)
# ---------------------------------------------------------------------------
#
# Performance env vars reference:
#   WINEFSYNC=1                    futex_waitv sync  (kernel 5.16+); best latency
#   WINEESYNC=1                    eventfd sync fallback
#   WINEDEBUG=-all                 suppress Wine debug I/O
#   DXVK_LOG_LEVEL=none            suppress DXVK log overhead
#   DXVK_ASYNC=1                   async pipeline compile – DISABLE for EAC/BattlEye
#   WINE_LARGE_ADDRESS_AWARE=1     32-bit procs > 2 GB RAM
#   VKD3D_CONFIG=dxr11             DX12 ray tracing via VKD3D-Proton
#   VKD3D_FEATURE_LEVEL=12_2       expose DX12 12.2
#   RADV_PERFTEST=gpl              AMD RADV: Graphics Pipeline Library (less stutter)
#   __GL_THREADED_OPTIMIZATIONS=1  NVIDIA: threaded OpenGL driver
#   STAGING_SHARED_MEMORY=1        wine-staging IPC shared memory
#
# Security notes:
#   Wine maps host / to Z:\ – Windows processes can read your entire filesystem.
#   Mitigation: run 'winetricks sandbox' inside every bottle, or remove Z: symlink.
#   Flatpak Bottles provides additional filesystem isolation via xdg-portal.
#   NEVER run untrusted .exe without a proper sandbox (Flatpak / Firejail / VM).
#

_GAMING_PARAMS: dict[str, Any] = {
    "dxvk":               True,    # DirectX 9/10/11 -> Vulkan (DXVK)
    "vkd3d":              True,    # DirectX 12 -> Vulkan (VKD3D-Proton)
    "dxvk_nvapi":         True,    # NVIDIA NvAPI / DLSS emulation
    "latencyflex":        False,   # AMD LatencyFleX (opt-in)
    "mangohud":           False,   # MangoHud FPS overlay (opt-in)
    "gamemode":           False,   # Feral GameMode (opt-in)
    "sync":               "fsync", # futex_waitv-based sync (kernel 5.16+)
    "fsr":                False,   # AMD FidelityFX SR (opt-in)
    "discrete_gpu":       False,   # Force discrete GPU via PRIME (opt-in)
    "virtual_desktop":    False,   # Wine virtual desktop (opt-in)
    "pulseaudio_latency": 60,      # PulseAudio/PipeWire buffer in ms
}

_GAMING_ENV_VARS: dict[str, str] = {
    # Synchronisation (fsync primary, esync fallback)
    "WINEFSYNC":                   "1",
    "WINEESYNC":                   "1",
    # Logging – disable in production for performance
    "WINEDEBUG":                   "-all",
    "DXVK_LOG_LEVEL":              "none",
    # DXVK async shader compilation
    # IMPORTANT: disable (set to 0) for anti-cheat protected games (EAC/BattlEye/FACEIT)
    "DXVK_ASYNC":                  "1",
    # Allow 32-bit processes to use > 2 GB RAM
    "WINE_LARGE_ADDRESS_AWARE":    "1",
    # VKD3D-Proton (DX12) hints
    "VKD3D_CONFIG":                "dxr11",
    "VKD3D_FEATURE_LEVEL":         "12_2",
    # AMD RADV Graphics Pipeline Library (reduces shader compile stutter)
    "RADV_PERFTEST":               "gpl",
    # NVIDIA threaded OpenGL driver optimizations
    "__GL_THREADED_OPTIMIZATIONS": "1",
    # wine-staging shared memory IPC
    "STAGING_SHARED_MEMORY":       "1",
}

_APPLICATION_PARAMS: dict[str, Any] = {
    "dxvk":               True,
    "vkd3d":              True,
    "dxvk_nvapi":         False,
    "latencyflex":        False,
    "mangohud":           False,
    "gamemode":           False,
    "sync":               "esync",  # esync sufficient for non-gaming workloads
    "fsr":                False,
    "discrete_gpu":       False,
    "virtual_desktop":    False,
    "pulseaudio_latency": 60,
}

_APPLICATION_ENV_VARS: dict[str, str] = {
    "WINEFSYNC":               "1",
    "WINEESYNC":               "1",
    "WINEDEBUG":               "-all",
    "DXVK_LOG_LEVEL":          "none",
    "WINE_LARGE_ADDRESS_AWARE": "1",
    "STAGING_SHARED_MEMORY":   "1",
}

PRESET_GAMING = BottlePreset(
    env=BottleEnv.GAMING,
    arch="win64",
    win_version=WinVersion.WIN10,
    params=_GAMING_PARAMS,
    env_vars=_GAMING_ENV_VARS,
    description="Optimised for games: DXVK+VKD3D+NvAPI+fsync+RADV_PERFTEST",
)

PRESET_APPLICATION = BottlePreset(
    env=BottleEnv.APPLICATION,
    arch="win64",
    win_version=WinVersion.WIN10,
    params=_APPLICATION_PARAMS,
    env_vars=_APPLICATION_ENV_VARS,
    description="Optimised for apps: DXVK+VKD3D+esync+fonts+mono",
)

PRESET_CUSTOM = BottlePreset(
    env=BottleEnv.CUSTOM,
    arch="win64",
    win_version=WinVersion.WIN10,
    params={},
    env_vars={},
    description="Clean slate – configure manually",
)

PRESETS: dict[BottleEnv, BottlePreset] = {
    BottleEnv.GAMING:      PRESET_GAMING,
    BottleEnv.APPLICATION: PRESET_APPLICATION,
    BottleEnv.CUSTOM:      PRESET_CUSTOM,
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CLI_TIMEOUT: int   = 120      # seconds; non-interactive subprocess limit
_ESYNC_FD_MINIMUM: int = 524_288   # minimum nofile limit for WINEESYNC


# ---------------------------------------------------------------------------
# bottles-cli wrapper
# ---------------------------------------------------------------------------
class BottlesCLI:
    """Thin wrapper around bottles-cli (native or Flatpak)."""

    def __init__(self) -> None:
        self._cmd_prefix: list[str] = self._detect_cli()

    def _detect_cli(self) -> list[str]:
        """Detect bottles-cli binary; prefer native, fall back to Flatpak."""
        if shutil.which("bottles-cli"):
            log.debug("Using native bottles-cli")
            return ["bottles-cli"]
        if shutil.which("flatpak"):
            result = subprocess.run(
                ["flatpak", "list", "--app", "--columns=application"],
                capture_output=True, text=True, timeout=15,
            )
            if "com.usebottles.bottles" in result.stdout:
                log.debug("Using Flatpak bottles-cli")
                return [
                    "flatpak", "run",
                    "--command=bottles-cli",
                    "com.usebottles.bottles",
                ]
        log.error(
            "bottles-cli not found. Install via AUR (bottles) "
            "or Flatpak (com.usebottles.bottles)."
        )
        sys.exit(1)

    def _run(
        self,
        args: list[str],
        *,
        json_output: bool = False,
        check: bool = True,
        timeout: int | None = _CLI_TIMEOUT,
    ) -> subprocess.CompletedProcess[str]:
        """
        Execute bottles-cli via list-form subprocess (no shell=True).
        Shell injection is structurally impossible: args are passed as a list.
        Raises subprocess.TimeoutExpired after `timeout` seconds (None = no limit).
        """
        cmd: list[str] = self._cmd_prefix.copy()
        if json_output:
            cmd.append("--json")
        cmd.extend(args)
        log.debug("Executing: %s", " ".join(cmd))
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=check,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            log.error("Command timed out after %ss: %s", timeout, " ".join(cmd))
            cprint(C.RED, f"  Timeout nach {timeout}s – Befehl abgebrochen.")
            raise

    def health_check(self) -> dict[str, Any]:
        result = self._run(["info", "health-check"], json_output=True)
        return json.loads(result.stdout)  # type: ignore[return-value]

    def list_bottles(self) -> list[str]:
        result = self._run(["list", "bottles"], json_output=True, check=False)
        if result.returncode != 0 or not result.stdout.strip():
            return []
        try:
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                return list(data.keys())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        return []

    def list_components(self, category: str) -> list[str]:
        result = self._run(
            ["list", "components", "-f", f"category:{category}"],
            json_output=True, check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        try:
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        return v
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        return []

    def list_programs(self, bottle: str) -> list[dict[str, Any]]:
        validate_bottle_name(bottle)
        result = self._run(["programs", "-b", bottle], json_output=True, check=False)
        if result.returncode != 0 or not result.stdout.strip():
            return []
        try:
            return json.loads(result.stdout)  # type: ignore[return-value]
        except json.JSONDecodeError:
            return []

    def create_bottle(
        self,
        name: str,
        preset: BottlePreset,
        runner: str | None = None,
        dxvk: str | None = None,
        vkd3d: str | None = None,
        nvapi: str | None = None,
        latencyflex: str | None = None,
    ) -> bool:
        """Create a new bottle. Validates all inputs before invoking CLI."""
        name = validate_bottle_name(name)
        if runner:
            runner = validate_component(runner, "runner")
        if dxvk:
            dxvk = validate_component(dxvk, "dxvk")
        if vkd3d:
            vkd3d = validate_component(vkd3d, "vkd3d")
        if nvapi:
            nvapi = validate_component(nvapi, "nvapi")
        if latencyflex:
            latencyflex = validate_component(latencyflex, "latencyflex")

        args: list[str] = [
            "new",
            "--bottle-name", name,
            "--environment", str(preset.env),
            "--arch", preset.arch,
        ]
        if runner:
            args += ["--runner", runner]
        if dxvk:
            args += ["--dxvk", dxvk]
        if vkd3d:
            args += ["--vkd3d", vkd3d]
        if nvapi:
            args += ["--nvapi", nvapi]
        if latencyflex:
            args += ["--latencyflex", latencyflex]

        result = self._run(args, check=False, timeout=300)
        if result.returncode != 0:
            log.error("Bottle creation failed:\n%s", result.stderr)
            return False

        for key, value in preset.params.items():
            param_str = (
                f"{key}:{str(value).lower()}"
                if isinstance(value, bool)
                else f"{key}:{value}"
            )
            try:
                validate_param(param_str)
            except ValueError:
                log.warning("Skipping invalid param: %s", param_str)
                continue
            self._run(["edit", "-b", name, "--params", param_str], check=False)

        for var, val in preset.env_vars.items():
            env_str = f"{var}={val}"
            try:
                validate_env_var(env_str)
            except ValueError:
                log.warning("Skipping invalid env var: %s", env_str)
                continue
            self._run(["edit", "-b", name, "--env-var", env_str], check=False)

        self._run(["edit", "-b", name, "--win", str(preset.win_version)], check=False)
        return True

    def open_tool(self, bottle: str, tool: WineTool) -> None:
        validate_bottle_name(bottle)
        result = self._run(["tools", "-b", bottle, str(tool)], check=False, timeout=300)
        if result.returncode != 0:
            log.error("Tool launch failed:\n%s", result.stderr)

    def run_executable(self, bottle: str, executable: str, args: str = "") -> None:
        validate_bottle_name(bottle)
        validate_executable_path(executable)
        cmd_args: list[str] = ["run", "-b", bottle, "-e", executable]
        if args:
            cmd_args += ["-a", args]
        self._run(cmd_args, check=False, timeout=None)  # no timeout during runtime

    def edit_bottle(
        self,
        bottle: str,
        *,
        params: str | None = None,
        env_var: str | None = None,
        win: str | None = None,
        runner: str | None = None,
        dxvk: str | None = None,
        vkd3d: str | None = None,
        nvapi: str | None = None,
    ) -> bool:
        validate_bottle_name(bottle)
        if params:
            params = validate_param(params)
        if env_var:
            env_var = validate_env_var(env_var)
        if runner:
            runner = validate_component(runner, "runner")
        if dxvk:
            dxvk = validate_component(dxvk, "dxvk")
        if vkd3d:
            vkd3d = validate_component(vkd3d, "vkd3d")
        if nvapi:
            nvapi = validate_component(nvapi, "nvapi")

        cli_args: list[str] = ["edit", "-b", bottle]
        if params:
            cli_args += ["--params", params]
        if env_var:
            cli_args += ["--env-var", env_var]
        if win:
            cli_args += ["--win", win]
        if runner:
            cli_args += ["--runner", runner]
        if dxvk:
            cli_args += ["--dxvk", dxvk]
        if vkd3d:
            cli_args += ["--vkd3d", vkd3d]
        if nvapi:
            cli_args += ["--nvapi", nvapi]

        result = self._run(cli_args, check=False)
        if result.returncode != 0:
            log.error("Edit failed:\n%s", result.stderr)
            return False
        return True

    def shell(self, bottle: str, command: str) -> None:
        validate_bottle_name(bottle)
        # command passed as single -i argument; not shell-expanded
        self._run(["shell", "-b", bottle, "-i", command], check=False, timeout=300)


# ---------------------------------------------------------------------------
# System check utilities
# ---------------------------------------------------------------------------
@dataclass
class SysCheckResult:
    name: str
    ok: bool
    message: str
    severity: str = "info"   # "ok" | "warn" | "error" | "info"


def _check_fd_limit() -> SysCheckResult:
    """Check open-file-descriptor limit (WINEESYNC needs >= 524288)."""
    try:
        import resource
        soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        ok = soft >= _ESYNC_FD_MINIMUM
        hint = (
            "" if ok
            else f" – add 'DefaultLimitNOFILE={_ESYNC_FD_MINIMUM}' to /etc/systemd/system.conf"
        )
        return SysCheckResult(
            name="File Descriptors (esync)",
            ok=ok,
            message=f"ulimit -n = {soft:,}  (min {_ESYNC_FD_MINIMUM:,}){hint}",
            severity="ok" if ok else "error",
        )
    except Exception as exc:
        return SysCheckResult("File Descriptors", False, str(exc), "error")


def _check_fsync_kernel() -> SysCheckResult:
    """Check futex_waitv support (Linux 5.16+ required for WINEFSYNC)."""
    try:
        r = subprocess.run(["uname", "-r"], capture_output=True, text=True, timeout=5)
        ver = r.stdout.strip()
        parts = ver.split(".")
        major, minor = int(parts[0]), int(parts[1].split("-")[0])
        ok = (major, minor) >= (5, 16)
        return SysCheckResult(
            name="fsync / futex_waitv",
            ok=ok,
            message=(
                f"Kernel {ver}  "
                f"({'OK – WINEFSYNC=1 supported' if ok else 'WARN – 5.16+ required for WINEFSYNC=1'})"
            ),
            severity="ok" if ok else "warn",
        )
    except Exception as exc:
        return SysCheckResult("fsync kernel", False, str(exc), "warn")


def _check_vulkan() -> SysCheckResult:
    """Check Vulkan ICD loader availability."""
    has_vulkaninfo = bool(shutil.which("vulkaninfo"))
    has_icd = (
        Path("/usr/share/vulkan/icd.d").exists()
        or Path("/etc/vulkan/icd.d").exists()
    )
    ok = has_vulkaninfo or has_icd
    return SysCheckResult(
        name="Vulkan ICD",
        ok=ok,
        message=(
            f"vulkaninfo: {'found' if has_vulkaninfo else 'missing'}  "
            f"ICD dir: {'found' if has_icd else 'missing'}"
            + ("" if ok else "  – install: pacman -S vulkan-icd-loader mesa/nvidia-utils")
        ),
        severity="ok" if ok else "error",
    )


def _check_32bit_libs() -> SysCheckResult:
    """Check for 32-bit Vulkan libraries (required for 32-bit DX games)."""
    paths = [
        "/usr/lib32/libvulkan.so",
        "/usr/lib32/libvulkan.so.1",
        "/usr/lib/i386-linux-gnu/libvulkan.so.1",
    ]
    found = any(Path(p).exists() for p in paths)
    return SysCheckResult(
        name="32-bit Vulkan libs",
        ok=found,
        message=(
            "lib32-vulkan-icd-loader: found"
            if found
            else "NOT found – pacman -S lib32-vulkan-icd-loader lib32-mesa / lib32-nvidia-utils"
        ),
        severity="ok" if found else "warn",
    )


def _check_cpu_governor() -> SysCheckResult:
    """Check CPU frequency scaling governor (performance = best for gaming)."""
    gov_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    if not gov_path.exists():
        return SysCheckResult(
            "CPU Governor", True,
            "cpufreq not exposed (HW-managed or not available)", "info",
        )
    gov = gov_path.read_text().strip()
    ok = gov == "performance"
    return SysCheckResult(
        name="CPU Governor",
        ok=ok,
        message=(
            f"Current: {gov}"
            + ("" if ok else "  – switch: cpupower frequency-set -g performance")
        ),
        severity="ok" if ok else "warn",
    )


def _check_gamemode() -> SysCheckResult:
    found = bool(shutil.which("gamemoded"))
    return SysCheckResult(
        "GameMode (Feral)", found,
        "gamemoded: found" if found else "not installed – pacman -S gamemode  (optional)",
        "ok" if found else "info",
    )


def _check_mangohud() -> SysCheckResult:
    found = bool(shutil.which("mangohud"))
    return SysCheckResult(
        "MangoHud", found,
        "mangohud: found" if found else "not installed – pacman -S mangohud  (optional)",
        "ok" if found else "info",
    )


def _check_z_drive_security() -> SysCheckResult:
    """Inform about the Wine Z: drive host-filesystem exposure."""
    return SysCheckResult(
        name="Z: Drive (Security)",
        ok=False,
        message=(
            "Wine maps host / to Z:\\ – Windows processes can read your filesystem.\n"
            "         Fix: 'winetricks sandbox' in each bottle, or remove\n"
            "         <prefix>/dosdevices/z: symlink.  Flatpak adds portal isolation."
        ),
        severity="warn",
    )


def _check_dxvk_async_ac() -> SysCheckResult:
    """Warn about DXVK_ASYNC=1 and anti-cheat bans."""
    return SysCheckResult(
        name="DXVK_ASYNC + Anti-Cheat",
        ok=False,
        message=(
            "DXVK_ASYNC=1 is active in the gaming preset.\n"
            "         DISABLE (set to 0) for EAC / BattlEye / FACEIT protected games\n"
            "         to avoid false-positive bans in competitive / online titles."
        ),
        severity="warn",
    )


def run_system_checks() -> list[SysCheckResult]:
    return [
        _check_fd_limit(),
        _check_fsync_kernel(),
        _check_vulkan(),
        _check_32bit_libs(),
        _check_cpu_governor(),
        _check_gamemode(),
        _check_mangohud(),
        _check_z_drive_security(),
        _check_dxvk_async_ac(),
    ]


# ---------------------------------------------------------------------------
# TUI helpers
# ---------------------------------------------------------------------------
def clear_screen() -> None:
    os.system("clear")


def separator(char: str = "─", width: int = 60) -> None:
    cprint(C.BLUE, char * width)


def header(title: str) -> None:
    clear_screen()
    separator("═")
    cprint(C.BOLD + C.CYAN, f"  Bottles Manager  |  {title}")
    separator("═")
    print()


def pause() -> None:
    input(f"\n{C.YELLOW}[Enter druecken...]{C.RESET}")


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{C.CYAN}{prompt}{suffix}: {C.RESET}").strip()
        if value:
            return value
        if default:
            return default


def ask_validated(prompt: str, validator: Any, default: str = "") -> str:
    """Read and validate input; repeat on ValueError."""
    while True:
        raw = ask(prompt, default)
        try:
            return validator(raw)
        except ValueError as exc:
            cprint(C.RED, f"  Fehler: {exc}")


def choose(options: list[str], prompt: str = "Auswahl") -> int:
    for i, opt in enumerate(options, 1):
        print(f"  {C.YELLOW}{i:>2}{C.RESET}. {opt}")
    print()
    while True:
        raw = input(f"{C.CYAN}{prompt}: {C.RESET}").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        cprint(C.RED, f"  Bitte 1-{len(options)} eingeben.")


def select_bottle(cli: BottlesCLI) -> str | None:
    bottles = cli.list_bottles()
    if not bottles:
        cprint(C.RED, "  Keine Bottles gefunden.")
        return None
    idx = choose(bottles, "Bottle waehlen")
    return bottles[idx]


def select_component(cli: BottlesCLI, category: str, label: str) -> str | None:
    components = cli.list_components(category)
    if not components:
        cprint(C.YELLOW, f"  Keine {label} gefunden (werden bei Bedarf heruntergeladen).")
        return None
    options = ["(automatisch - neueste Version)"] + components
    idx = choose(options, f"{label} waehlen")
    return None if idx == 0 else options[idx]


# ---------------------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------------------
def action_create_gaming(cli: BottlesCLI) -> None:
    header("Neues Gaming-Bottle")
    # IMPORTANT: deepcopy prevents global preset mutation across multiple creations
    preset = copy.deepcopy(PRESETS[BottleEnv.GAMING])
    cprint(C.GREEN, f"  Preset: {preset.description}\n")
    _print_preset_summary(preset)

    name = ask_validated("  Bottle-Name", validate_bottle_name)

    cprint(C.YELLOW, "\n  WARNUNG: DXVK_ASYNC=1 ist aktiv.")
    cprint(C.YELLOW, "  Fuer Anti-Cheat-Spiele (EAC/BattlEye) DXVK_ASYNC=0 setzen!\n")

    runner = select_component(cli, "runners", "Runner (Proton/Caffe)")
    dxvk   = select_component(cli, "dxvk",    "DXVK-Version")
    vkd3d  = select_component(cli, "vkd3d",   "VKD3D-Version")
    nvapi  = select_component(cli, "nvapi",   "DXVK-NVAPI-Version")

    print()
    cprint(C.CYAN, "  Optionale Performance-Features:")
    if _confirm("  MangoHud (FPS-Overlay) aktivieren?"):
        preset.params["mangohud"] = True
    if _confirm("  GameMode (Feral) aktivieren?"):
        preset.params["gamemode"] = True
    if _confirm("  FSR (AMD FidelityFX Super Resolution) aktivieren?"):
        preset.params["fsr"] = True
    if _confirm("  LatencyFleX (AMD GPU) aktivieren?"):
        preset.params["latencyflex"] = True
        # LatencyFleX is incompatible with fsync/esync
        preset.params["sync"] = "wine"
        preset.env_vars.pop("WINEFSYNC", None)
        preset.env_vars.pop("WINEESYNC", None)
    if _confirm("  PRIME Discrete GPU erzwingen?"):
        preset.params["discrete_gpu"] = True
    if _confirm("  DXVK_ASYNC deaktivieren? (fuer Anti-Cheat-Spiele)"):
        preset.env_vars["DXVK_ASYNC"] = "0"

    print()
    cprint(C.YELLOW,
        "  SICHERHEIT: Wine Z:\\ gibt Windows-Prozessen Lesezugriff auf das "
        "Dateisystem.\n  Empfehlung: 'winetricks sandbox' nach der Erstellung ausfuehren."
    )

    print()
    cprint(C.YELLOW, f"  Erstelle Gaming-Bottle '{name}'...")
    ok = cli.create_bottle(name, preset, runner=runner, dxvk=dxvk, vkd3d=vkd3d, nvapi=nvapi)
    if ok:
        cprint(C.GREEN, f"\n  Gaming-Bottle '{name}' erfolgreich erstellt.")
        log.info("Gaming bottle '%s' created.", name)
    else:
        cprint(C.RED, f"\n  Erstellung von '{name}' fehlgeschlagen.")
    pause()


def action_create_application(cli: BottlesCLI) -> None:
    header("Neues Applikations-Bottle")
    preset = copy.deepcopy(PRESETS[BottleEnv.APPLICATION])
    cprint(C.GREEN, f"  Preset: {preset.description}\n")
    _print_preset_summary(preset)

    name   = ask_validated("  Bottle-Name", validate_bottle_name)
    runner = select_component(cli, "runners", "Runner (Caffe/Vaniglia)")
    dxvk   = select_component(cli, "dxvk",   "DXVK-Version")

    win_versions = [str(v) for v in WinVersion]
    cprint(C.CYAN, "\n  Windows-Version waehlen:")
    win_idx = choose(win_versions, "  Version")
    preset.win_version = WinVersion(win_versions[win_idx])

    print()
    cprint(C.YELLOW,
        "  SICHERHEIT: Wine Z:\\ gibt Zugriff auf das Host-Dateisystem.\n"
        "  'winetricks sandbox' nach der Erstellung empfohlen."
    )

    print()
    cprint(C.YELLOW, f"  Erstelle Applikations-Bottle '{name}'...")
    ok = cli.create_bottle(name, preset, runner=runner, dxvk=dxvk)
    if ok:
        cprint(C.GREEN, f"\n  Applikations-Bottle '{name}' erfolgreich erstellt.")
        log.info("Application bottle '%s' created.", name)
    else:
        cprint(C.RED, f"\n  Erstellung von '{name}' fehlgeschlagen.")
    pause()


def action_create_custom(cli: BottlesCLI) -> None:
    header("Neues Custom-Bottle")
    preset = copy.deepcopy(PRESETS[BottleEnv.CUSTOM])
    cprint(C.GREEN, f"  Preset: {preset.description}\n")

    name = ask_validated("  Bottle-Name", validate_bottle_name)

    arch_idx = choose(["win64 (empfohlen)", "win32"], "  Architektur")
    preset.arch = "win64" if arch_idx == 0 else "win32"

    runner = select_component(cli, "runners", "Runner")
    dxvk   = select_component(cli, "dxvk",   "DXVK")
    vkd3d  = select_component(cli, "vkd3d",  "VKD3D")
    nvapi  = select_component(cli, "nvapi",  "DXVK-NVAPI")

    print()
    cprint(C.YELLOW, f"  Erstelle Custom-Bottle '{name}'...")
    ok = cli.create_bottle(name, preset, runner=runner, dxvk=dxvk, vkd3d=vkd3d, nvapi=nvapi)
    if ok:
        cprint(C.GREEN, f"\n  Custom-Bottle '{name}' erfolgreich erstellt.")
    else:
        cprint(C.RED, "\n  Erstellung fehlgeschlagen.")
    pause()


def action_list_bottles(cli: BottlesCLI) -> None:
    header("Bottles-Uebersicht")
    bottles = cli.list_bottles()
    if not bottles:
        cprint(C.YELLOW, "  Keine Bottles vorhanden.")
    else:
        for b in bottles:
            cprint(C.GREEN, f"  * {b}")
    pause()


def action_list_components(cli: BottlesCLI) -> None:
    header("Installierte Komponenten")
    for category in ("runners", "dxvk", "vkd3d", "nvapi", "latencyflex"):
        components = cli.list_components(category)
        cprint(C.CYAN, f"\n  [{category.upper()}]")
        if components:
            for c in components:
                print(f"    * {c}")
        else:
            cprint(C.YELLOW, "    (keine installiert)")
    pause()


def action_open_tool(cli: BottlesCLI) -> None:
    header("Wine-Tool oeffnen")
    bottle = select_bottle(cli)
    if not bottle:
        pause()
        return
    print()
    tools = [str(t) for t in WineTool]
    cprint(C.CYAN, "  Tool waehlen:")
    idx = choose(tools, "  Tool")
    selected_tool = WineTool(tools[idx])
    cprint(C.YELLOW, f"\n  Starte {selected_tool} in '{bottle}'...")
    cli.open_tool(bottle, selected_tool)
    pause()


def action_run_executable(cli: BottlesCLI) -> None:
    header("Programm ausfuehren")
    bottle = select_bottle(cli)
    if not bottle:
        pause()
        return

    programs = cli.list_programs(bottle)
    if programs:
        cprint(C.CYAN, "\n  Registrierte Programme:")
        prog_names = [p.get("name", "?") for p in programs]
        options = ["(anderen Pfad eingeben)"] + prog_names
        idx = choose(options, "  Auswahl")
        if idx == 0:
            exe = ask_validated("  Pfad zur .exe", validate_executable_path)
            exe_args = ask("  Argumente (leer = keine)", default="")
            cli.run_executable(bottle, exe, exe_args)
        else:
            prog = programs[idx - 1]
            cprint(C.YELLOW, f"\n  Starte '{prog.get('name')}'...")
            cli.run_executable(bottle, prog.get("path", ""), prog.get("arguments", ""))
    else:
        exe = ask_validated("  Pfad zur .exe", validate_executable_path)
        exe_args = ask("  Argumente (leer = keine)", default="")
        cli.run_executable(bottle, exe, exe_args)
    pause()


def action_edit_bottle(cli: BottlesCLI) -> None:
    header("Bottle bearbeiten")
    bottle = select_bottle(cli)
    if not bottle:
        pause()
        return

    edit_options = [
        "Parameter setzen (key:value)",
        "Umgebungsvariable setzen (VAR=Wert)",
        "Windows-Version aendern",
        "Runner wechseln",
        "DXVK-Version wechseln",
        "VKD3D-Version wechseln",
        "DXVK-NVAPI wechseln",
        "Zurueck",
    ]

    while True:
        print()
        cprint(C.CYAN, f"  Bottle: {C.BOLD}{bottle}")
        print()
        idx = choose(edit_options, "  Aktion")
        ok = True

        try:
            if idx == 0:
                param = ask_validated("  Parameter (key:value)", validate_param)
                ok = cli.edit_bottle(bottle, params=param)
            elif idx == 1:
                env_var = ask_validated("  Variable (UPPER_VAR=Wert)", validate_env_var)
                ok = cli.edit_bottle(bottle, env_var=env_var)
            elif idx == 2:
                versions = [str(v) for v in WinVersion]
                win_idx = choose(versions, "  Windows-Version")
                ok = cli.edit_bottle(bottle, win=versions[win_idx])
            elif idx == 3:
                runner = select_component(cli, "runners", "Runner")
                if runner:
                    ok = cli.edit_bottle(bottle, runner=runner)
            elif idx == 4:
                dxvk = select_component(cli, "dxvk", "DXVK")
                if dxvk:
                    ok = cli.edit_bottle(bottle, dxvk=dxvk)
            elif idx == 5:
                vkd3d = select_component(cli, "vkd3d", "VKD3D")
                if vkd3d:
                    ok = cli.edit_bottle(bottle, vkd3d=vkd3d)
            elif idx == 6:
                nvapi = select_component(cli, "nvapi", "DXVK-NVAPI")
                if nvapi:
                    ok = cli.edit_bottle(bottle, nvapi=nvapi)
            elif idx == 7:
                break
        except ValueError as exc:
            cprint(C.RED, f"  Validierungsfehler: {exc}")
            continue

        cprint(C.GREEN if ok else C.RED,
               "  Gespeichert." if ok else "  Fehler beim Speichern (siehe Log).")
    pause()


def action_shell(cli: BottlesCLI) -> None:
    header("Wine Shell")
    bottle = select_bottle(cli)
    if not bottle:
        pause()
        return
    cprint(C.YELLOW,
        "  SICHERHEIT: Shell hat vollen Zugriff auf das Bottle-Prefix.\n"
        "  Nur vertrauenswuerdige Befehle ausfuehren!"
    )
    command = ask("  Shell-Befehl")
    cprint(C.YELLOW, f"\n  Ausfuehren in '{bottle}': {command}")
    cli.shell(bottle, command)
    pause()


def action_system_check(_cli: BottlesCLI) -> None:
    """Comprehensive performance and security system check."""
    header("System-Check (Performance + Security)")
    results = run_system_checks()

    ok_count   = sum(1 for r in results if r.severity == "ok")
    warn_count = sum(1 for r in results if r.severity == "warn")
    err_count  = sum(1 for r in results if r.severity == "error")

    for r in results:
        color, icon = {
            "ok":    (C.GREEN,  "[OK ]"),
            "warn":  (C.YELLOW, "[WRN]"),
            "error": (C.RED,    "[ERR]"),
        }.get(r.severity, (C.DIM, "[INF]"))
        print(f"  {color}{icon} {r.name:<34}{C.RESET} {r.message}")

    print()
    separator()
    print(
        f"  {C.GREEN}OK: {ok_count}{C.RESET}   "
        f"{C.YELLOW}WARN: {warn_count}{C.RESET}   "
        f"{C.RED}ERR: {err_count}{C.RESET}"
    )
    pause()


def action_health_check(cli: BottlesCLI) -> None:
    header("Bottles Health-Check")
    try:
        info = cli.health_check()
        _print_json_tree(info, indent=2)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            json.JSONDecodeError) as exc:
        cprint(C.RED, f"  Fehler: {exc}")
    pause()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [j/N] ").strip().lower()
    return answer in {"j", "y", "ja", "yes"}


def _print_preset_summary(preset: BottlePreset) -> None:
    separator()
    cprint(C.MAGENTA, "  Preset-Konfiguration:")
    print(f"  {'Architektur':<24} {preset.arch}")
    print(f"  {'Windows-Version':<24} {preset.win_version}")
    for k, v in preset.params.items():
        color = C.GREEN if (v and v is not False) else C.YELLOW
        print(f"  {k:<24} {color}{v}{C.RESET}")
    if preset.env_vars:
        cprint(C.MAGENTA, "\n  Umgebungsvariablen:")
        for k, v in preset.env_vars.items():
            print(f"  {k:<32} {v}")
    separator()
    print()


def _print_json_tree(data: Any, indent: int = 0) -> None:
    prefix = " " * indent
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                cprint(C.CYAN, f"{prefix}{key}:")
                _print_json_tree(value, indent + 4)
            else:
                color = C.GREEN if value else C.YELLOW
                print(f"{prefix}{C.CYAN}{key}{C.RESET}: {color}{value}{C.RESET}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                _print_json_tree(item, indent)
            else:
                print(f"{prefix}* {item}")
    else:
        print(f"{prefix}{data}")


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------
MAIN_MENU: list[tuple[str, Any]] = [
    ("[GAME] Gaming-Bottle erstellen",        action_create_gaming),
    ("[APP]  Applikations-Bottle erstellen",   action_create_application),
    ("[CUST] Custom-Bottle erstellen",         action_create_custom),
    ("[LIST] Bottles auflisten",               action_list_bottles),
    ("[COMP] Komponenten auflisten",           action_list_components),
    ("[EDIT] Bottle bearbeiten",               action_edit_bottle),
    ("[TOOL] Wine-Tool oeffnen",               action_open_tool),
    ("[RUN]  Programm ausfuehren",             action_run_executable),
    ("[SH]   Wine-Shell",                      action_shell),
    ("[CHK]  System-Check (Perf + Security)",  action_system_check),
    ("[HLT]  Bottles Health-Check",            action_health_check),
    ("[EXIT] Beenden",                         None),
]


def main() -> int:
    cli = BottlesCLI()

    while True:
        header("Hauptmenue")
        labels = [label for label, _ in MAIN_MENU]
        idx = choose(labels, "Auswahl")
        _, action = MAIN_MENU[idx]

        if action is None:
            cprint(C.CYAN, "\n  Auf Wiedersehen!\n")
            break

        try:
            action(cli)
        except KeyboardInterrupt:
            print()
            cprint(C.YELLOW, "  Abgebrochen.")
            pause()
        except subprocess.TimeoutExpired:
            cprint(C.RED, "\n  Timeout - Befehl wurde beendet.")
            pause()
        except Exception as exc:  # noqa: BLE001
            cprint(C.RED, f"\n  Unerwarteter Fehler: {exc}")
            log.exception("Unexpected error in %s", getattr(action, "__name__", "?"))
            pause()

    return 0


if __name__ == "__main__":
    sys.exit(main())
