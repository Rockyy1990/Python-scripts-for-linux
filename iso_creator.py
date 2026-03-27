#!/usr/bin/env python3
"""
ISO Creator - Erstellt normale und bootfähige ISO-Dateien
Unterstützt: ArchLinux, Debian und UEFI-Kompatibilität
Voraussetzungen: xorriso, mkisofs, syslinux installiert
"""

import os
import sys
import subprocess
import argparse
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum


# ==================== KONFIGURATION ====================

class DistributionType(Enum):
    """Unterstützte Linux-Distributionen"""
    ARCHLINUX = "archlinux"
    DEBIAN = "debian"
    GENERIC = "generic"


@dataclass
class ISOConfig:
    """Konfiguration für ISO-Erstellung"""
    source_dir: Path
    output_iso: Path
    volume_label: str
    bootable: bool = False
    uefi_support: bool = True
    bios_support: bool = True
    distribution: DistributionType = DistributionType.GENERIC
    efi_boot_image: Optional[Path] = None
    isolinux_bin: Optional[Path] = None
    isolinux_cat: Optional[Path] = None
    mbr_file: Optional[Path] = None
    rock_ridge: bool = True
    joliet: bool = True
    udf: bool = True


# ==================== LOGGING ====================

def setup_logging(verbose: bool = False) -> logging.Logger:
    """Konfiguriert Logging"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


logger = setup_logging()


# ==================== DEPENDENCY CHECKS ====================

class DependencyChecker:
    """Überprüft erforderliche Abhängigkeiten"""
    
    REQUIRED_TOOLS = ['xorriso', 'mkisofs', 'syslinux']
    
    @staticmethod
    def check_command_exists(command: str) -> bool:
        """Prüft ob ein Kommando verfügbar ist"""
        result = subprocess.run(
            ['which', command],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    
    @classmethod
    def check_all_dependencies(cls) -> bool:
        """Überprüft alle erforderlichen Dependencies"""
        missing = []
        
        for tool in cls.REQUIRED_TOOLS:
            if not cls.check_command_exists(tool):
                missing.append(tool)
        
        if missing:
            logger.error(f"Fehlende Programme: {', '.join(missing)}")
            logger.info("Installation auf Debian/Ubuntu:")
            logger.info("sudo apt-get install xorriso syslinux-utils")
            logger.info("\nInstallation auf ArchLinux:")
            logger.info("sudo pacman -S xorriso syslinux")
            return False
        
        logger.info("✓ Alle Abhängigkeiten verfügbar")
        return True
    
    @staticmethod
    def get_syslinux_path() -> Optional[Path]:
        """Findet den Pfad zu syslinux Dateien"""
        possible_paths = [
            Path('/usr/share/syslinux'),
            Path('/usr/lib/syslinux'),
            Path('/usr/share/syslinux/modules/bios'),
        ]
        
        for path in possible_paths:
            if path.exists():
                return path
        
        return None


# ==================== ISO-ERSTELLUNG ====================

class ISOCreator:
    """Erstellt ISO-Dateien mit verschiedenen Optionen"""
    
    def __init__(self, config: ISOConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
    
    def validate_source(self) -> bool:
        """Validiert das Quellverzeichnis"""
        if not self.config.source_dir.exists():
            self.logger.error(f"Quellverzeichnis existiert nicht: {self.config.source_dir}")
            return False
        
        if not self.config.source_dir.is_dir():
            self.logger.error(f"Quelle ist kein Verzeichnis: {self.config.source_dir}")
            return False
        
        self.logger.info(f"✓ Quellverzeichnis validiert: {self.config.source_dir}")
        return True
    
    def prepare_output(self) -> bool:
        """Bereitet das Ausgabeverzeichnis vor"""
        try:
            self.config.output_iso.parent.mkdir(parents=True, exist_ok=True)
            
            # Entfernt bestehende ISO
            if self.config.output_iso.exists():
                self.logger.warning(f"Überschreibe bestehende ISO: {self.config.output_iso}")
                self.config.output_iso.unlink()
            
            self.logger.info(f"✓ Ausgabeverzeichnis vorbereitet: {self.config.output_iso.parent}")
            return True
        except Exception as e:
            self.logger.error(f"Fehler beim Vorbereiten des Ausgabeverzeichnisses: {e}")
            return False
    
    def detect_boot_files(self) -> bool:
        """Erkennt Boot-Dateien im Quellverzeichnis"""
        if not self.config.bootable:
            return True
        
        # Sucht nach isolinux.bin
        isolinux_paths = list(self.config.source_dir.glob('**/isolinux.bin'))
        if isolinux_paths:
            self.config.isolinux_bin = isolinux_paths[0]
            self.logger.info(f"✓ isolinux.bin gefunden: {self.config.isolinux_bin}")
        
        # Sucht nach boot.cat
        bootcat_paths = list(self.config.source_dir.glob('**/boot.cat'))
        if bootcat_paths:
            self.config.isolinux_cat = bootcat_paths[0]
            self.logger.info(f"✓ boot.cat gefunden: {self.config.isolinux_cat}")
        
        # Sucht nach EFI-Boot-Image
        efi_paths = list(self.config.source_dir.glob('**/efiboot*.img'))
        if efi_paths:
            self.config.efi_boot_image = efi_paths[0]
            self.logger.info(f"✓ EFI-Boot-Image gefunden: {self.config.efi_boot_image}")
        
        # Sucht nach bootx64.efi
        bootx64_paths = list(self.config.source_dir.glob('**/BOOTX64.EFI')) + \
                        list(self.config.source_dir.glob('**/bootx64.efi'))
        if bootx64_paths:
            self.logger.info(f"✓ UEFI-Bootloader gefunden: {bootx64_paths[0]}")
        
        return True
    
    def create_simple_iso(self) -> bool:
        """Erstellt eine einfache (nicht-bootfähige) ISO"""
        self.logger.info("Erstelle einfache ISO-Datei...")
        
        cmd = [
            'xorriso',
            '-as', 'mkisofs',
            '-R',  # Rock Ridge Erweiterung
            '-J',  # Joliet Erweiterung
            '-v',  # Verbose
            '-V', self.config.volume_label,  # Volume Label
        ]
        
        if self.config.udf:
            cmd.append('-udf')
        
        cmd.extend([
            '-o', str(self.config.output_iso),
            str(self.config.source_dir)
        ])
        
        return self._execute_command(cmd, "Einfache ISO erstellt")
    
    def create_bootable_iso(self) -> bool:
        """Erstellt eine bootfähige ISO mit BIOS/UEFI-Unterstützung"""
        self.logger.info("Erstelle bootfähige ISO-Datei...")
        
        if not self.config.isolinux_bin:
            self.logger.error("isolinux.bin nicht gefunden")
            return False
        
        # Findet syslinux MBR-Datei
        syslinux_path = DependencyChecker.get_syslinux_path()
        if syslinux_path:
            mbr_file = syslinux_path / 'isohdpfx.bin'
            if mbr_file.exists():
                self.config.mbr_file = mbr_file
        
        # Berechnet relative Pfade von der ISO-Wurzel
        isolinux_bin_rel = self._get_relative_path(self.config.isolinux_bin)
        isolinux_cat_rel = self._get_relative_path(self.config.isolinux_cat) if self.config.isolinux_cat else None
        efi_boot_rel = self._get_relative_path(self.config.efi_boot_image) if self.config.efi_boot_image else None
        
        cmd = [
            'xorriso',
            '-as', 'mkisofs',
            '-R',
            '-J',
            '-v',
            '-V', self.config.volume_label,
        ]
        
        # BIOS-Boot-Optionen
        if self.config.bios_support and isolinux_bin_rel:
            cmd.extend([
                '-b', isolinux_bin_rel,
                '-no-emul-boot',
                '-boot-info-table',
                '-boot-load-size', '4',
            ])
            
            if isolinux_cat_rel:
                cmd.extend(['-c', isolinux_cat_rel])
            
            # ISO-Hybrid MBR
            if self.config.mbr_file and self.config.mbr_file.exists():
                cmd.extend(['-isohybrid-mbr', str(self.config.mbr_file)])
        
        # UEFI-Boot-Optionen
        if self.config.uefi_support and efi_boot_rel:
            cmd.extend([
                '-eltorito-alt-boot',
                '-e', efi_boot_rel,
                '-no-emul-boot',
                '-isohybrid-gpt-basdat',
            ])
        elif self.config.uefi_support:
            self.logger.warning("UEFI-Support angefordert, aber kein EFI-Boot-Image gefunden")
        
        if self.config.udf:
            cmd.append('-udf')
        
        cmd.extend([
            '-o', str(self.config.output_iso),
            str(self.config.source_dir)
        ])
        
        return self._execute_command(cmd, "Bootfähige ISO erstellt")
    
    def _get_relative_path(self, file_path: Path) -> str:
        """Berechnet relativen Pfad von der ISO-Wurzel"""
        try:
            rel_path = file_path.relative_to(self.config.source_dir)
            return str(rel_path)
        except ValueError:
            return str(file_path.name)
    
    def _execute_command(self, cmd: List[str], success_msg: str) -> bool:
        """Führt ein Kommando aus und gibt Feedback"""
        try:
            self.logger.debug(f"Ausführen: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=False,
                text=True,
                check=True
            )
            
            self.logger.info(f"✓ {success_msg}")
            self.logger.info(f"ISO-Datei: {self.config.output_iso}")
            
            # Zeigt Dateigröße
            size_mb = self.config.output_iso.stat().st_size / (1024 * 1024)
            self.logger.info(f"Größe: {size_mb:.2f} MB")
            
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Fehler beim Erstellen der ISO: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unerwarteter Fehler: {e}")
            return False
    
    def create(self) -> bool:
        """Hauptmethode zur ISO-Erstellung"""
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"ISO Creator - {self.config.volume_label}")
        self.logger.info(f"{'='*60}\n")
        
        # Validierungen
        if not self.validate_source():
            return False
        
        if not self.prepare_output():
            return False
        
        if self.config.bootable:
            if not self.detect_boot_files():
                return False
            return self.create_bootable_iso()
        else:
            return self.create_simple_iso()


# ==================== BATCH-VERARBEITUNG ====================

class BatchISOCreator:
    """Erstellt mehrere ISOs aus verschiedenen Verzeichnissen"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def create_from_directory_structure(
        self,
        base_dir: Path,
        output_dir: Path,
        bootable: bool = False,
        pattern: str = "*"
    ) -> bool:
        """Erstellt ISOs aus Unterverzeichnissen"""
        
        base_dir = Path(base_dir)
        output_dir = Path(output_dir)
        
        if not base_dir.exists():
            self.logger.error(f"Basisverzeichnis existiert nicht: {base_dir}")
            return False
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Findet alle Unterverzeichnisse
        subdirs = sorted([d for d in base_dir.iterdir() if d.is_dir()])
        
        if not subdirs:
            self.logger.warning(f"Keine Unterverzeichnisse in {base_dir} gefunden")
            return False
        
        self.logger.info(f"Gefundene Verzeichnisse: {len(subdirs)}")
        
        success_count = 0
        failed_count = 0
        
        for subdir in subdirs:
            iso_name = f"{subdir.name}.iso"
            output_iso = output_dir / iso_name
            
            config = ISOConfig(
                source_dir=subdir,
                output_iso=output_iso,
                volume_label=subdir.name.upper()[:32],
                bootable=bootable,
                uefi_support=True,
                bios_support=True
            )
            
            creator = ISOCreator(config, self.logger)
            
            if creator.create():
                success_count += 1
            else:
                failed_count += 1
            
            self.logger.info("")
        
        # Zusammenfassung
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"Zusammenfassung:")
        self.logger.info(f"Erfolgreich: {success_count}")
        self.logger.info(f"Fehlgeschlagen: {failed_count}")
        self.logger.info(f"{'='*60}\n")
        
        return failed_count == 0


# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(
        description='ISO Creator - Erstellt bootfähige und normale ISO-Dateien',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Beispiele:

  # Einfache ISO erstellen
  python3 iso_creator.py -s /pfad/zum/verzeichnis -o output.iso -l "MYLABEL"

  # Bootfähige ISO mit UEFI
  python3 iso_creator.py -s /pfad/zum/verzeichnis -o output.iso -l "BOOTISO" -b

  # Mehrere ISOs aus Unterverzeichnissen
  python3 iso_creator.py -s /pfad/zur/basis -o /pfad/zum/output -b --batch

  # ArchLinux ISO
  python3 iso_creator.py -s /pfad/zum/archlinux -o archlinux.iso -l "ARCHLINUX" -b -d archlinux
        '''
    )
    
        parser.add_argument(
        '-s', '--source',
        type=Path,
        required=True,
        help='Quellverzeichnis für ISO-Erstellung'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=Path,
        required=True,
        help='Ausgabepfad für ISO-Datei'
    )
    
    parser.add_argument(
        '-l', '--label',
        type=str,
        default='CUSTOM_ISO',
        help='Volume Label (max. 32 Zeichen, Standard: CUSTOM_ISO)'
    )
    
    parser.add_argument(
        '-b', '--bootable',
        action='store_true',
        help='Erstellt bootfähige ISO'
    )
    
    parser.add_argument(
        '--no-uefi',
        action='store_true',
        help='Deaktiviert UEFI-Unterstützung'
    )
    
    parser.add_argument(
        '--no-bios',
        action='store_true',
        help='Deaktiviert BIOS-Unterstützung'
    )
    
    parser.add_argument(
        '-d', '--distribution',
        type=str,
        choices=['archlinux', 'debian', 'generic'],
        default='generic',
        help='Zieldistribution (Standard: generic)'
    )
    
    parser.add_argument(
        '--batch',
        action='store_true',
        help='Erstellt ISOs aus allen Unterverzeichnissen'
    )
    
    parser.add_argument(
        '--no-udf',
        action='store_true',
        help='Deaktiviert UDF-Dateisystem'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Ausführliches Logging'
    )
    
    parser.add_argument(
        '--check-deps',
        action='store_true',
        help='Überprüft nur Abhängigkeiten'
    )
    
    args = parser.parse_args()
    
    # Setup Logging
    log = setup_logging(args.verbose)
    
    # Überprüfe Abhängigkeiten
    if not DependencyChecker.check_all_dependencies():
        sys.exit(1)
    
    if args.check_deps:
        log.info("✓ Alle Abhängigkeiten vorhanden")
        sys.exit(0)
    
    # Validiere Label-Länge
    if len(args.label) > 32:
        log.error("Volume Label darf max. 32 Zeichen lang sein")
        sys.exit(1)
    
    # Batch-Verarbeitung
    if args.batch:
        batch_creator = BatchISOCreator(log)
        success = batch_creator.create_from_directory_structure(
            base_dir=args.source,
            output_dir=args.output,
            bootable=args.bootable
        )
        sys.exit(0 if success else 1)
    
    # Einzelne ISO-Erstellung
    config = ISOConfig(
        source_dir=args.source,
        output_iso=args.output,
        volume_label=args.label,
        bootable=args.bootable,
        uefi_support=not args.no_uefi,
        bios_support=not args.no_bios,
        distribution=DistributionType(args.distribution),
        udf=not args.no_udf
    )
    
    creator = ISOCreator(config, log)
    success = creator.create()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

