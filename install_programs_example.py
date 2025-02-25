#!/usr/bin/env python

import subprocess
import os

def run_command(command):
    """Run a shell command and print the output."""
    print(f"Running command: {command}")
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
    else:
        print(result.stdout)

def main():
    input("Press any key to continue..")

    # Refresh and update the system
    run_command("sudo zypper refresh")
    run_command("sudo zypper -n dup")

    # Needed system packages
    packages = [
        "dkms", "bind", "samba", "git", "openssh", "fakeroot", "irqbalance", "quota", "ccache", "mono-basic",
        "hdparm", "sdparm", "hwdata", "sof-firmware", "fwupd", "gsmartcontrol",
        "gnome-disk-utility", "mtools", "xfsdump", "jfsutils", "f2fs-tools", "libf2fs_format9",
        "ntfs-3g", "libfsntfs1", "libluksde1", "libftxf1",
        "xdg-utils", "xdg-desktop-portal", "xdg-desktop-portal-gtk", "xdg-user-dirs",
        "fastfetch", "fastfetch-bash-completion",
        "devel_basis", "fetchmsttfonts"
    ]
    run_command("sudo zypper -n install " + " ".join(packages))

    # Set fastfetch to start with the terminal
    with open(os.path.expanduser("~/.bashrc"), "a") as bashrc:
        bashrc.write("fastfetch\n")

    # Recommend packages: AMD GPU driver
    amd_gpu_packages = [
        "libdrm_amdgpu1", "kernel-firmware-amdgpu", "libvdpau_va_gl1", "libva-vdpau-driver",
        "Mesa-libva", "libOSMesa8",
        "vulkan-validationlayers", "Mesa-vulkan-overlay", "libvkd3d1"
    ]
    run_command("sudo zypper -n install " + " ".join(amd_gpu_packages))

    # Environment variables
    environment_variables = """
CPU_LIMIT=0
CPU_GOVERNOR=performance
GPU_USE_SYNC_OBJECTS=1
PYTHONOPTIMIZE=1
AMD_VULKAN_ICD=RADV
RADV_PERFTEST=aco,sam,nggc
RADV_DEBUG=novrsflatshading
GAMEMODE=1
vblank_mode=1
PROTON_LOG=0
PROTON_USE_WINED3D=0
PROTON_FORCE_LARGE_ADDRESS_AWARE=1
PROTON_USE_FSYNC=1
DXVK_ASYNC=1
WINE_FSR_OVERRIDE=1
WINE_FULLSCREEN_FSR=1
WINE_VK_USE_FSR=1
WINEFSYNC_SPINCOUNT=24
MESA_BACK_BUFFER=ximage
MESA_NO_DITHER=1
MESA_SHADER_CACHE_DISABLE=false
mesa_glthread=true
MESA_DEBUG=0
MESA_VK_ENABLE_SUBMIT_THREAD=1
ANV_ENABLE_PIPELINE_CACHE=1
LIBGL_DEBUG=0
LIBC_FORCE_NOCHECK=1
__GLX_VENDOR_LIBRARY_NAME=mesa
__GL_THREADED_OPTIMIZATIONS=1
"""
    with open("/etc/environment", "a") as env_file:
        env_file.write(environment_variables)

    # Recommend packages: Various needed packages
    run_command("sudo zypper -n install thunderbird discord")

    # Recommend packages: Codecs
    codecs_packages = [
        "gstreamer-plugins-good-extra", "gstreamer-plugin-openh264", "gstreamer-plugins-ugly",
        "gstreamer-plugin-pipewire", "gstreamer-plugin-python", "gstreamer-plugins-libav", "gstreamer-plugins-vaapi",
        "lame", "flac", "libmad0", "ffmpeg-7", "rtkit", "libopenal0", "libsoxr-lsr0", "opus-tools"
    ]
    run_command("sudo zypper -n install " + " ".join(codecs_packages))

    # Multimedia
    multimedia_packages = [
        "celluloid", "strawberry", "soundconverter", "yt-dlp", "pavucontrol"
    ]
    run_command("sudo zyp -n install " + " ".join(multimedia_packages))

if __name__ == "__main__":
    main()