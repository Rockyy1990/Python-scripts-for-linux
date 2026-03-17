#!/usr/bin/env python3

import subprocess
import os
import sys
from pathlib import Path

def convert_to_x265(input_file, output_file):
    """
    Konvertiert eine Videodatei zu H.265 (HEVC) mit AAC Audio.

    Args:
        input_file (str): Pfad zur Eingabedatei
        output_file (str): Pfad zur Ausgabedatei

    Returns:
        bool: True bei erfolgreicher Konvertierung, False bei Fehler
    """
    # Überprüfe, ob Eingabedatei existiert
    if not Path(input_file).exists():
        print(f"Fehler: Eingabedatei '{input_file}' nicht gefunden.")
        return False

    # Überprüfe, ob ffmpeg installiert ist
    if not _check_ffmpeg_installed():
        print("Fehler: ffmpeg ist nicht installiert oder nicht im PATH.")
        return False

    # Warnung, wenn Ausgabedatei bereits existiert
    if Path(output_file).exists():
        response = input(f"Datei '{output_file}' existiert bereits. Überschreiben? (j/n): ")
        if response.lower() != 'j':
            print("Konvertierung abgebrochen.")
            return False

    # FFmpeg-Befehl mit optimierten Parametern
    ffmpeg_command = [
        'ffmpeg',
        '-i', input_file,
        '-vcodec', 'libx265',
        '-crf', '20',
        '-preset', 'medium',
        '-x265-params', 'log-level=error',
        '-acodec', 'aac',
        '-ab', '224k',
        '-ac', '2',
        '-y',
        output_file
    ]

    print(f"\nStarte Konvertierung: {input_file} → {output_file}")
    print("Dies kann einige Zeit dauern...\n")

    try:
        result = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=False)

        if result.returncode == 0:
            print("✓ Konvertierung erfolgreich abgeschlossen!")
            return True
        else:
            print(f"✗ Fehler bei der Konvertierung:\n{result.stderr}")
            return False

    except FileNotFoundError:
        print("Fehler: ffmpeg wurde nicht gefunden.")
        return False
    except Exception as e:
        print(f"Unerwarteter Fehler: {e}")
        return False

def _check_ffmpeg_installed():
    """Überprüft, ob ffmpeg verfügbar ist."""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False

def get_valid_input(prompt, check_exists=False):
    """
    Fordert den Benutzer zur Eingabe auf und validiert diese.

    Args:
        prompt (str): Eingaueaufforderung
        check_exists (bool): Wenn True, prüfe ob Datei existiert

    Returns:
        str: Validierte Eingabe mit expandiertem Pfad
    """
    while True:
        user_input = input(prompt).strip().strip("'\"")

        if not user_input:
            print("Fehler: Eingabe darf nicht leer sein.")
            continue

        # Expandiere ~ zu Home-Verzeichnis
        expanded_path = os.path.expanduser(user_input)

        if check_exists and not Path(expanded_path).exists():
            print(f"Fehler: Datei '{expanded_path}' nicht gefunden.")
            continue

        return expanded_path

def main():
    """Hauptfunktion des Konverters."""
    print("\n" + "="*50)
    print(" FFMPEG x265 (CRF 20) AAC (224k) Video Converter")
    print("="*50 + "\n")

    try:
        # Eingabedatei erfragen
        input_file = get_valid_input("Eingabedatei (Pfad): ", check_exists=True)

        # Ausgabedatei erfragen
        output_file = get_valid_input("Ausgabedatei (Pfad mit Erweiterung, z.B. output.mp4): ")

        # Konvertierung durchführen
        success = convert_to_x265(input_file, output_file)

        if success:
            file_size = Path(output_file).stat().st_size / (1024 * 1024)
            print(f"\nDateigröße: {file_size:.2f} MB")

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\nProgramm durch Benutzer unterbrochen.")
        sys.exit(130)
    except Exception as e:
        print(f"\nFehler: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
