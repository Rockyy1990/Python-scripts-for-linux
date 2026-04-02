#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║         GStreamer Musik Player  –  PipeWire Backend          ║
║         Lautstärke-Normalisierung via ReplayGain             ║
╚══════════════════════════════════════════════════════════════╝

Abhängigkeiten (Debian/Ubuntu):
  sudo apt install python3-gi gstreamer1.0-tools \
       gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
       gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
       gstreamer1.0-pipewire

Arch:
  sudo pacman -S python-gobject gstreamer gst-plugins-base \
       gst-plugins-good gst-plugins-bad gst-plugins-ugly \
       gst-plugin-pipewire
"""

import os
import sys
import threading
import time

# ── GObject / GStreamer Imports ────────────────────────────────────────────────
try:
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version("GLib", "2.0")
    from gi.repository import Gst, GLib
except ImportError:
    print("[FEHLER] python3-gi (PyGObject) ist nicht installiert.")
    print("         sudo apt install python3-gi")
    sys.exit(1)

# ── GStreamer initialisieren ───────────────────────────────────────────────────
Gst.init(None)

# ── ANSI-Farben ───────────────────────────────────────────────────────────────
COLOR_ORANGE = "\033[38;5;208m"
COLOR_RESET  = "\033[0m"

# ══════════════════════════════════════════════════════════════════════════════
#  CODEC-ERKENNUNG
# ══════════════════════════════════════════════════════════════════════════════

# Bekannte Audio-Decoder-Elemente und ihre Formate
KNOWN_AUDIO_DECODERS = {
    # Format-Name         : GStreamer-Element-Name
    "MP3"                 : "mpegaudioparse",
    "AAC"                 : "aacparse",
    "FLAC"                : "flacparse",
    "OGG/Vorbis"          : "vorbisdec",
    "OGG/Opus"            : "opusdec",
    "WAV"                 : "wavparse",
    "AIFF"                : "aiffparse",
    "WMA"                 : "wmadec",
    "ALAC"                : "avdec_alac",
    "MP4/M4A (AAC)"       : "faad",
    "MP4/M4A (avdec)"     : "avdec_aac",
    "Musepack (MPC)"      : "musepackdec",
    "Monkey's Audio"      : "avdec_ape",
    "WavPack"             : "wavpackdec",
    "Speex"               : "speexdec",
    "TrueAudio (TTA)"     : "avdec_tta",
    "DSD (DSF/DFF)"       : "dsddec",
    "AC-3 / Dolby"        : "avdec_ac3",
    "DTS"                 : "avdec_dts",
    "MP2"                 : "avdec_mp2float",
}

# Dateiendungen für die Playlist-Erkennung
AUDIO_EXTENSIONS = {
    ".mp3", ".aac", ".m4a", ".mp4", ".flac", ".ogg", ".opus",
    ".wav", ".aiff", ".aif", ".wma", ".mpc", ".ape", ".wv",
    ".spx", ".tta", ".dsf", ".dff", ".ac3", ".dts", ".mp2",
    ".webm", ".mkv",
}


def check_available_codecs() -> dict:
    """
    Prüft welche Audio-Codecs über GStreamer verfügbar sind.
    Gibt ein Dict {Format: verfügbar (bool)} zurück.
    """
    available = {}
    registry = Gst.Registry.get()
    for fmt, element_name in KNOWN_AUDIO_DECODERS.items():
        feature = registry.find_feature(element_name, Gst.ElementFactory.__gtype__)
        available[fmt] = feature is not None
    return available


def print_codec_banner(codecs: dict):
    """Gibt eine formatierte Codec-Übersicht aus."""
    width = 62
    print("╔" + "═" * width + "╗")
    print("║{:^{w}}║".format("  Verfügbare GStreamer Audio-Codecs  ", w=width))
    print("╠" + "═" * width + "╣")

    available_list   = [f for f, ok in codecs.items() if ok]
    unavailable_list = [f for f, ok in codecs.items() if not ok]

    print("║  ✔  Verfügbar:{:<{w}}║".format("", w=width - 15))
    for fmt in available_list:
        print("║     ✔  {:<{w}}║".format(fmt, w=width - 8))

    if unavailable_list:
        print("╠" + "─" * width + "╣")
        print("║  ✘  Nicht verfügbar:{:<{w}}║".format("", w=width - 21))
        for fmt in unavailable_list:
            print("║     ✘  {:<{w}}║".format(fmt, w=width - 8))

    print("╚" + "═" * width + "╝")
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  MUSIK-PLAYER KLASSE
# ══════════════════════════════════════════════════════════════════════════════

class MusicPlayer:
    """
    GStreamer-basierter Musik-Player mit PipeWire-Backend.

    Verwendet 'playbin' als All-in-One-Pipeline-Element.
    Lautstärke-Normalisierung erfolgt über den GStreamer
    ReplayGain-Filter (rgvolume + rglimiter).
    """

    def __init__(self):
        self.playlist: list[str] = []   # Absolute Dateipfade
        self.current_index: int  = -1   # Aktuell spielender Track
        self.normalization: bool = False
        self._volume: float      = 1.0  # 0.0 – 1.0 (intern)
        self._paused: bool       = False
        self._playing: bool      = False

        # ── GLib Main-Loop (läuft in eigenem Thread für Bus-Events) ───────────
        self._loop = GLib.MainLoop()
        self._loop_thread = threading.Thread(
            target=self._loop.run, daemon=True
        )
        self._loop_thread.start()

        # ── Playbin-Pipeline aufbauen ──────────────────────────────────────────
        self._build_pipeline()

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def _build_pipeline(self):
        """Erstellt die GStreamer-Pipeline (playbin)."""
        self._player = Gst.ElementFactory.make("playbin", "player")
        if not self._player:
            print("[FEHLER] GStreamer 'playbin' konnte nicht erstellt werden.")
            sys.exit(1)

        # Standard-Audio-Sink setzen (PipeWire bevorzugen)
        self._player.set_property("audio-sink", self._make_default_sink())

        # Video-Ausgabe deaktivieren (reiner Audio-Player)
        fake_video = Gst.ElementFactory.make("fakesink", "video-sink")
        if fake_video:
            self._player.set_property("video-sink", fake_video)

        # Lautstärke setzen
        self._player.set_property("volume", self._volume)

        # Bus-Nachrichten abonnieren
        bus = self._player.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos",   self._on_eos)
        bus.connect("message::error", self._on_error)
        bus.connect("message::tag",   self._on_tag)

    def _make_default_sink(self):
        """Erstellt den Standard-Audio-Sink (PipeWire → autoaudiosink)."""
        sink = Gst.ElementFactory.make("pipewiresink", None)
        if not sink:
            sink = Gst.ElementFactory.make("autoaudiosink", None)
        return sink

    def _build_normalization_bin(self):
        """
        Erstellt einen Audio-Sink-Bin mit ReplayGain-Normalisierung via
        Gst.parse_bin_from_description().

        Dadurch werden Elemente automatisch eindeutig benannt (kein
        Namenskonflikt bei erneutem Aufruf), verlinkt und der Ghost-Pad
        korrekt gesetzt.

        Pipeline: rgvolume → rglimiter → audioconvert → audioresample → autoaudiosink
        autoaudiosink wählt PipeWire automatisch – sicherer als pipewiresink
        direkt in einem benutzerdefinierten Bin.
        """
        if not Gst.ElementFactory.find("rgvolume"):
            return None

        pipeline_desc = (
            "rgvolume pre-amp=0.0 album-mode=false "
            "! rglimiter "
            "! audioconvert "
            "! audioresample "
            "! autoaudiosink"
        )

        try:
            bin_ = Gst.parse_bin_from_description(pipeline_desc, ghost_unlinked_pads=True)
            return bin_
        except Exception as exc:
            print(f"[WARNUNG] Normalisierungs-Bin Fehler: {exc}")
            return None

    # ── Bus-Callbacks ──────────────────────────────────────────────────────────

    def _on_eos(self, bus, message):
        """End-of-Stream: automatisch zum nächsten Track springen."""
        self._playing = False
        self._paused  = False
        GLib.idle_add(self._auto_next)

    def _on_error(self, bus, message):
        """Fehler-Callback."""
        err, debug = message.parse_error()
        print(f"\n[FEHLER] GStreamer: {err.message}")
        if debug:
            print(f"         Debug: {debug}")
        self._playing = False
        self._paused  = False

    def _on_tag(self, bus, message):
        """Tag-Callback: Metadaten (Titel, Künstler) ausgeben."""
        tags = message.parse_tag()
        title  = tags.get_string("title")
        artist = tags.get_string("artist")
        if title[0] and title[1]:
            info = f"♪  {title[1]}"
            if artist[0] and artist[1]:
                info += f"  –  {artist[1]}"
            print(f"   {info}")

    def _auto_next(self):
        """Wird nach EOS aufgerufen – nächsten Track starten."""
        if self.current_index < len(self.playlist) - 1:
            self.current_index += 1
            self._start_current()
        else:
            print("   ✔  Playlist beendet.")
        return False  # GLib.idle_add einmalig ausführen

    # ── Interne Wiedergabe-Steuerung ───────────────────────────────────────────

    def _start_current(self):
        """Startet den aktuellen Track (self.current_index)."""
        if not self.playlist or self.current_index < 0:
            return
        if self.current_index >= len(self.playlist):
            self.current_index = len(self.playlist) - 1

        path = self.playlist[self.current_index]
        if not os.path.isfile(path):
            print(f"[WARNUNG] Datei nicht gefunden: {path}")
            return

        # Pipeline in NULL bringen – Sink kann nur im NULL-Zustand gewechselt werden
        self._player.set_state(Gst.State.NULL)

        if self.normalization:
            norm_bin = self._build_normalization_bin()
            if norm_bin:
                self._player.set_property("audio-sink", norm_bin)
            else:
                print("[WARNUNG] ReplayGain nicht verfügbar – "
                      "Standard-Sink wird verwendet.")
                self._player.set_property("audio-sink", self._make_default_sink())
        else:
            self._player.set_property("audio-sink", self._make_default_sink())

        uri = Gst.filename_to_uri(path)
        self._player.set_property("uri", uri)
        self._player.set_property("volume", self._volume)
        self._player.set_state(Gst.State.PLAYING)
        self._playing = True
        self._paused  = False

        filename = os.path.basename(path)
        idx_str  = f"{self.current_index + 1}/{len(self.playlist)}"
        print(f"   ▶  [{idx_str}] {filename}")

    # ── Öffentliche Player-API ─────────────────────────────────────────────────

    def play(self):
        """Startet die Wiedergabe oder setzt nach Pause fort."""
        if self._paused:
            self._player.set_state(Gst.State.PLAYING)
            self._playing = True
            self._paused  = False
            print("   ▶  Wiedergabe fortgesetzt.")
            return

        if not self.playlist:
            print("   [!] Playlist ist leer.")
            return

        if self.current_index < 0:
            self.current_index = 0

        self._start_current()

    def pause(self):
        """Pausiert die Wiedergabe."""
        if self._playing and not self._paused:
            self._player.set_state(Gst.State.PAUSED)
            self._paused  = True
            self._playing = False
            print("   ⏸  Pausiert.")
        elif self._paused:
            print("   [!] Bereits pausiert. 'Play' zum Fortsetzen.")
        else:
            print("   [!] Kein Track wird abgespielt.")

    def stop(self):
        """Stoppt die Wiedergabe vollständig."""
        self._player.set_state(Gst.State.NULL)
        self._playing = False
        self._paused  = False
        print("   ⏹  Gestoppt.")

    def skip(self):
        """Springt zum nächsten Track in der Playlist."""
        if not self.playlist:
            print("   [!] Playlist ist leer.")
            return
        if self.current_index < len(self.playlist) - 1:
            self.current_index += 1
            self._start_current()
        else:
            print("   [!] Letzter Track – kein nächster vorhanden.")

    def toggle_normalization(self):
        """Schaltet die Lautstärke-Normalisierung (ReplayGain) um."""
        if not Gst.ElementFactory.find("rgvolume"):
            print("   [!] ReplayGain (rgvolume) ist nicht installiert.")
            print("       sudo apt install gstreamer1.0-plugins-good")
            return

        self.normalization = not self.normalization
        status = "AN" if self.normalization else "AUS"
        print(f"   🔊  Lautstärke-Normalisierung: {status}")

        # Wenn gerade ein Track läuft oder pausiert ist, neu starten
        # damit der neue Sink-Typ sofort aktiv wird.
        if self._playing or self._paused:
            was_paused = self._paused
            self._start_current()
            if was_paused:
                self._player.set_state(Gst.State.PAUSED)
                self._playing = False
                self._paused  = True

    def set_volume(self, volume_percent: int):
        """Setzt die Lautstärke (0–100%)."""
        vol = max(0, min(100, volume_percent)) / 100.0
        self._volume = vol
        self._player.set_property("volume", vol)
        bar = "█" * int(vol * 20) + "░" * (20 - int(vol * 20))
        print(f"   🔊  Lautstärke: [{bar}] {volume_percent}%")

    def get_status(self) -> str:
        """Gibt den aktuellen Player-Status zurück."""
        if self._playing:
            return "▶ Spielt"
        elif self._paused:
            return "⏸ Pausiert"
        else:
            return "⏹ Gestoppt"

    def get_position_str(self) -> str:
        """Gibt Position / Dauer als String zurück."""
        try:
            ok_pos, pos = self._player.query_position(Gst.Format.TIME)
            ok_dur, dur = self._player.query_duration(Gst.Format.TIME)
            if ok_pos and ok_dur and dur > 0:
                pos_s = pos // Gst.SECOND
                dur_s = dur // Gst.SECOND
                return (f"{pos_s // 60:02d}:{pos_s % 60:02d} / "
                        f"{dur_s // 60:02d}:{dur_s % 60:02d}")
        except Exception:
            pass
        return "--:-- / --:--"

    def cleanup(self):
        """Ressourcen freigeben."""
        self._player.set_state(Gst.State.NULL)
        self._loop.quit()


# ══════════════════════════════════════════════════════════════════════════════
#  PLAYLIST-VERWALTUNG
# ══════════════════════════════════════════════════════════════════════════════

def add_file(player: MusicPlayer):
    """Einzelne Datei zur Playlist hinzufügen."""
    path = input("   Dateipfad: ").strip().strip("'\"")
    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    if not os.path.isfile(path):
        print(f"   [!] Datei nicht gefunden: {path}")
        return

    ext = os.path.splitext(path)[1].lower()
    if ext not in AUDIO_EXTENSIONS:
        print(f"   [!] Unbekannte Dateiendung '{ext}'. Trotzdem hinzufügen? (j/n): ",
              end="")
        if input().strip().lower() != "j":
            return

    player.playlist.append(path)
    print(f"   ✔  Hinzugefügt: {os.path.basename(path)}")
    print(f"      Playlist: {len(player.playlist)} Track(s)")


def add_directory(player: MusicPlayer):
    """Alle Audio-Dateien eines Verzeichnisses zur Playlist hinzufügen."""
    path = input("   Verzeichnispfad: ").strip()
    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    if not os.path.isdir(path):
        print(f"   [!] Verzeichnis nicht gefunden: {path}")
        return

    recursive    = input("   Unterverzeichnisse einschließen? (j/n): ").strip().lower()
    count_before = len(player.playlist)

    if recursive == "j":
        for root, _, files in os.walk(path):
            for f in sorted(files):
                if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS:
                    player.playlist.append(os.path.join(root, f))
    else:
        for f in sorted(os.listdir(path)):
            full = os.path.join(path, f)
            if os.path.isfile(full) and \
               os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS:
                player.playlist.append(full)

    added = len(player.playlist) - count_before
    print(f"   ✔  {added} Track(s) hinzugefügt. "
          f"Gesamt: {len(player.playlist)} Track(s)")


def show_playlist(player: MusicPlayer):
    """Playlist anzeigen."""
    if not player.playlist:
        print("   [!] Playlist ist leer.")
        return

    width = 66
    print("╔" + "═" * width + "╗")
    print("║{:^{w}}║".format("  PLAYLIST  ", w=width))
    print("╠" + "═" * width + "╣")

    for i, path in enumerate(player.playlist):
        marker = "▶ " if i == player.current_index else "  "
        name   = os.path.basename(path)
        if len(name) > width - 8:
            name = name[:width - 11] + "..."
        line = f"{marker}{i + 1:3d}. {name}"
        print(f"║ {line:<{width - 2}} ║")

    print("╠" + "─" * width + "╣")
    norm_str = "AN" if player.normalization else "AUS"
    vol_str  = f"{int(player._volume * 100)}%"
    info = (f"  Tracks: {len(player.playlist)}  │  "
            f"Status: {player.get_status()}  │  "
            f"Normalisierung: {norm_str}  │  "
            f"Lautstärke: {vol_str}")
    print(f"║{info:<{width}}║")
    print("╚" + "═" * width + "╝")


def remove_track(player: MusicPlayer):
    """Track aus der Playlist entfernen."""
    if not player.playlist:
        print("   [!] Playlist ist leer.")
        return

    show_playlist(player)
    try:
        idx = int(input("   Track-Nummer entfernen (0 = Abbrechen): ").strip())
    except ValueError:
        print("   [!] Ungültige Eingabe.")
        return

    if idx == 0:
        return
    idx -= 1  # 0-basiert

    if idx < 0 or idx >= len(player.playlist):
        print("   [!] Ungültige Track-Nummer.")
        return

    removed = os.path.basename(player.playlist[idx])
    player.playlist.pop(idx)

    # current_index anpassen
    if player.current_index == idx:
        player.stop()
        player.current_index = -1
    elif player.current_index > idx:
        player.current_index -= 1

    print(f"   ✔  Entfernt: {removed}")


def clear_playlist(player: MusicPlayer):
    """Playlist leeren."""
    if not player.playlist:
        print("   [!] Playlist ist bereits leer.")
        return
    confirm = input(f"   {len(player.playlist)} Track(s) löschen? (j/n): ").strip()
    if confirm.lower() == "j":
        player.stop()
        player.playlist.clear()
        player.current_index = -1
        print("   ✔  Playlist geleert.")


# ══════════════════════════════════════════════════════════════════════════════
#  MENÜ
# ══════════════════════════════════════════════════════════════════════════════

def print_menu(player: MusicPlayer):
    """Hauptmenü ausgeben."""
    width    = 50
    norm_str = "✔ AN" if player.normalization else "✘ AUS"
    vol_str  = f"{int(player._volume * 100)}%"

    # Status-Zeile
    if player._playing or player._paused:
        current_name = (os.path.basename(player.playlist[player.current_index])
                        if 0 <= player.current_index < len(player.playlist)
                        else "–")
        if len(current_name) > 38:
            current_name = current_name[:35] + "..."
        pos         = player.get_position_str()
        status_line = f"{player.get_status()}  {pos}  {current_name}"
    else:
        status_line = f"{player.get_status()}  │  Playlist: {len(player.playlist)} Track(s)"

    print("╔" + "═" * width + "╗")
    print("║{:^{w}}║".format("    GStreamer Musik Player   ", w=width))
    print("╠" + "═" * width + "╣")
    print(f"║  {status_line:<{width - 2}}║")
    print(f"║  Lautstärke: {vol_str:<4}  │  Normalisierung: {norm_str:<{width - 39}}║")
    print("╠" + "═" * width + "╣")
    print("║  PLAYLIST                                        ║")
    print("║  [1]  Einzelne Datei hinzufügen                  ║")
    print("║  [2]  Verzeichnis hinzufügen                     ║")
    print("║  [3]  Playlist anzeigen                          ║")
    print("║  [4]  Track entfernen                            ║")
    print("║  [5]  Playlist leeren                            ║")
    print("╠" + "─" * width + "╣")
    print("║  WIEDERGABE                                      ║")
    print("║  [6]  Play / Fortsetzen                          ║")
    print("║  [7]  Skip  (nächster Track)                     ║")
    print("║  [8]  Pause                                      ║")
    print("║  [9]  Stop                                       ║")
    print("║  [10] Lautstärke einstellen                      ║")
    print("║  [11] Lautstärke-Normalisierung umschalten       ║")
    print("╠" + "─" * width + "╣")
    print("║  SYSTEM                                          ║")
    opt12 = "  [12] Verfügbare Codecs anzeigen"
    print(f"║{COLOR_ORANGE}{opt12:<{width}}{COLOR_RESET}║")
    print("╠" + "─" * width + "╣")
    print("║  [0]  Beenden                                    ║")
    print("╚" + "═" * width + "╝")


def volume_menu(player: MusicPlayer):
    """Lautstärke-Untermenü."""
    print(f"   Aktuelle Lautstärke: {int(player._volume * 100)}%")
    try:
        val = int(input("   Neue Lautstärke (0–100): ").strip())
        player.set_volume(val)
    except ValueError:
        print("   [!] Bitte eine Zahl zwischen 0 und 100 eingeben.")


# ══════════════════════════════════════════════════════════════════════════════
#  HAUPTPROGRAMM
# ══════════════════════════════════════════════════════════════════════════════

def main():
    if Gst.ElementFactory.find("pipewiresink"):
        print("  ✔  PipeWire-Sink (pipewiresink) verfügbar.")
    elif Gst.ElementFactory.find("autoaudiosink"):
        print("  ⚠  PipeWire-Sink nicht gefunden – "
              "verwende autoaudiosink (wählt PipeWire automatisch).")
    else:
        print("  ✘  Kein Audio-Sink gefunden! "
              "Bitte GStreamer-Plugins installieren.")

    player = MusicPlayer()

    # Menü einmalig beim Start anzeigen
    print_menu(player)

    try:
        while True:
            try:
                choice = input("  Auswahl (m = Menü): ").strip().lower()
            except EOFError:
                break

            if   choice == "m":  print_menu(player)
            elif choice == "1":  add_file(player)
            elif choice == "2":  add_directory(player)
            elif choice == "3":  show_playlist(player)
            elif choice == "4":  remove_track(player)
            elif choice == "5":  clear_playlist(player)
            elif choice == "6":  player.play()
            elif choice == "7":  player.skip()
            elif choice == "8":  player.pause()
            elif choice == "9":  player.stop()
            elif choice == "10": volume_menu(player)
            elif choice == "11": player.toggle_normalization()
            elif choice == "12":
                codecs = check_available_codecs()
                print_codec_banner(codecs)
                print(f"  {COLOR_ORANGE}(wird in 6 Sekunden ausgeblendet …){COLOR_RESET}")
                def _hide_codecs(p=player):
                    time.sleep(6)
                    print("\033[2J\033[H", end="", flush=True)
                    print_menu(p)
                threading.Thread(target=_hide_codecs, daemon=True).start()
            elif choice == "0":
                print("  Auf Wiederhören! 👋")
                break
            else:
                print("  [!] Ungültige Auswahl.")

            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\n  [!] Abbruch durch Benutzer (Ctrl+C).")
    finally:
        player.cleanup()


if __name__ == "__main__":
    main()
