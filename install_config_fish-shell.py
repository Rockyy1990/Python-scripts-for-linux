#!/usr/bin/env python3
"""
Skript zum Installieren und Konfigurieren von fish shell als Standard-Shell für Arch Linux
Verwendet pacman als Paketmanager
"""

import os
import sys
import subprocess
from pathlib import Path

class FishInstallerArchLinux:
    def __init__(self):
        self.username = os.getenv('SUDO_USER') or os.getenv('USER')
        self.home_dir = Path.home()
        self.fish_path = None
        
    def _run_command(self, command, sudo=False, check=True):
        """Führt einen Shell-Befehl aus"""
        try:
            if sudo and os.geteuid() != 0:
                command = f'sudo {command}'
            
            print(f"🔧 Führe aus: {command}")
            result = subprocess.run(
                command,
                shell=True,
                check=check,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"✅ Erfolgreich ausgeführt")
                return True, result.stdout
            else:
                print(f"❌ Fehler: {result.stderr}")
                return False, result.stderr
                
        except Exception as e:
            print(f"❌ Fehler beim Ausführen: {e}")
            return False, str(e)
    
    def install_fish(self):
        """Installiert fish shell mit pacman"""
        print("\n📦 Installiere fish shell mit pacman...")
        
        success, output = self._run_command('pacman -Sy', sudo=True)
        if not success:
            return False
        
        success, output = self._run_command('pacman -S --noconfirm fish', sudo=True)
        
        if success:
            print("✅ fish shell erfolgreich installiert")
            return True
        
        print("❌ fish shell konnte nicht installiert werden")
        return False
    
    def verify_fish_installation(self):
        """Überprüft, ob fish installiert ist und gibt den Pfad zurück"""
        success, output = self._run_command('which fish', check=False)
        if success:
            self.fish_path = output.strip()
            print(f"✅ fish shell gefunden unter: {self.fish_path}")
            return self.fish_path
        
        print("❌ fish shell konnte nicht gefunden werden")
        return None
    
    def register_fish_in_shells(self):
        """Registriert fish in /etc/shells"""
        print("\n🔧 Registriere fish in /etc/shells...")
        
        try:
            with open('/etc/shells', 'r') as f:
                shells_content = f.read()
            
            if self.fish_path in shells_content:
                print("✅ fish shell bereits in /etc/shells registriert")
                return True
            
            print("⚠️  fish shell nicht in /etc/shells. Registriere es...")
            command = f'echo {self.fish_path} | sudo tee -a /etc/shells > /dev/null'
            success, output = self._run_command(command, sudo=False)
            
            if success:
                print("✅ fish shell zu /etc/shells hinzugefügt")
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Fehler beim Registrieren: {e}")
            return False
    
    def set_fish_as_default_shell(self):
        """Setzt fish als Standard-Shell für den aktuellen Benutzer"""
        print(f"\n🔄 Setze fish shell als Standard-Shell für Benutzer '{self.username}'...")
        
        command = f'usermod -s {self.fish_path} {self.username}'
        success, output = self._run_command(command, sudo=True)
        
        if success:
            print(f"✅ fish shell als Standard-Shell gesetzt")
            return True
        
        print("❌ Fehler beim Setzen der Standard-Shell")
        return False
    
    def create_fish_config(self):
        """Erstellt eine Basis fish Konfigurationsdatei"""
        print("\n📝 Erstelle fish Konfiguration...")
        
        fish_config_dir = self.home_dir / '.config' / 'fish'
        fish_config_file = fish_config_dir / 'config.fish'
        
        # Stelle sicher, dass das Verzeichnis existiert
        fish_config_dir.mkdir(parents=True, exist_ok=True)
        
        # Basis-Konfiguration für fish shell
        fish_config_content = """# fish shell Konfiguration für Arch Linux
# Automatisch erstellt durch Installationsskript

# Grundlegende Einstellungen
set -x LANG de_DE.UTF-8
set -x LC_ALL de_DE.UTF-8

# Editor-Einstellungen
set -x EDITOR nano
set -x VISUAL nano

# Verlauf-Einstellungen
set -x fish_history bash

# Farben für ls
set -x LS_COLORS 'di=38;5;33:ex=38;5;149:*.tar=38;5;208'

# Aliase
alias ls='ls --color=auto'
alias ll='ls -lah'
alias la='ls -A'
alias l='ls -CF'
alias grep='grep --color=auto'
alias pacman='pacman --color=auto'
alias yay='yay --color=auto'
alias makepkg='makepkg -si'

# Funktionen
function mkcd
    mkdir -p $argv
    cd $argv
end

function extract
    switch $argv[1]
        case '*.tar.gz'
            tar xzf $argv[1]
        case '*.tar.bz2'
            tar xjf $argv[1]
        case '*.tar.xz'
            tar xJf $argv[1]
        case '*.zip'
            unzip $argv[1]
        case '*.rar'
            unrar x $argv[1]
        case '*'
            echo "Unbekanntes Archiv-Format: $argv[1]"
    end
end

# Git Aliase
alias ga='git add'
alias gc='git commit'
alias gp='git push'
alias gl='git log'
alias gs='git status'

# Prompt-Anpassung (optional)
function fish_prompt
    set_color brgreen
    echo -n (whoami)
    set_color normal
    echo -n '@'
    set_color bryellow
    echo -n (hostname)
    set_color normal
    echo -n ':'
    set_color brblue
    echo -n (pwd)
    set_color normal
    echo -n '> '
end

# Zusätzliche Konfigurationen können hier hinzugefügt werden
"""
        
        try:
            # Sichern der existierenden config.fish
            if fish_config_file.exists():
                backup_path = fish_config_dir / 'config.fish.backup'
                fish_config_file.rename(backup_path)
                print(f"💾 Alte config.fish gesichert unter: {backup_path}")
            
            # Neue config.fish schreiben
            fish_config_file.write_text(fish_config_content)
            fish_config_file.chmod(0o644)
            
            # Stelle sicher, dass der Benutzer Eigentümer ist
            os.chown(fish_config_file, os.getuid(), os.getgid())
            os.chown(fish_config_dir, os.getuid(), os.getgid())
            
            print(f"✅ config.fish erstellt unter: {fish_config_file}")
            return True
            
        except Exception as e:
            print(f"❌ Fehler beim Erstellen von config.fish: {e}")
            return False
    
    def verify_setup(self):
        """Überprüft die Konfiguration"""
        print("\n✔️  Überprüfe Konfiguration...")
        
        # Überprüfe Standardshell
        try:
            with open('/etc/passwd', 'r') as f:
                for line in f:
                    if line.startswith(self.username + ':'):
                        shell = line.strip().split(':')[-1]
                        if 'fish' in shell:
                            print(f"✅ fish shell ist Standard-Shell für '{self.username}'")
                            print(f"   Shell: {shell}")
                        else:
                            print(f"⚠️  Standard-Shell ist nicht fish: {shell}")
                        break
        except Exception as e:
            print(f"⚠️  Konnte Shell nicht überprüfen: {e}")
        
        # Überprüfe config.fish
        fish_config_file = self.home_dir / '.config' / 'fish' / 'config.fish'
        if fish_config_file.exists():
            print(f"✅ config.fish existiert unter: {fish_config_file}")
        else:
            print(f"⚠️  config.fish nicht gefunden unter: {fish_config_file}")
        
        # Überprüfe /etc/shells
        try:
            with open('/etc/shells', 'r') as f:
                if self.fish_path in f.read():
                    print(f"✅ fish shell ist in /etc/shells registriert")
                else:
                    print(f"⚠️  fish shell ist nicht in /etc/shells registriert")
        except Exception as e:
            print(f"⚠️  Konnte /etc/shells nicht überprüfen: {e}")
    
    def run(self):
        """Führt den vollständigen Installationsprozess aus"""
        print("=" * 70)
        print("🚀 fish shell Installations- und Konfigurationsskript für Arch Linux")
        print("=" * 70)
        print(f"Benutzer: {self.username}")
        print(f"Home-Verzeichnis: {self.home_dir}")
        print("=" * 70)
        
        # Überprüfe Root-Rechte
        if os.geteuid() != 0:
            print("❌ Dieses Skript benötigt sudo-Rechte.")
            print("   Bitte mit sudo ausführen:")
            print("   sudo python3 install_fish.py")
            sys.exit(1)
        
        # Schritt 1: fish installieren
        if not self.install_fish():
            print("❌ Installation abgebrochen: fish shell konnte nicht installiert werden")
            sys.exit(1)
        
        # Schritt 2: fish-Pfad überprüfen
        if not self.verify_fish_installation():
            print("❌ Installation abgebrochen: fish-Pfad konnte nicht ermittelt werden")
            sys.exit(1)
        
        # Schritt 3: fish in /etc/shells registrieren
        if not self.register_fish_in_shells():
            print("⚠️  Warnung: fish shell konnte nicht in /etc/shells registriert werden")
        
        # Schritt 4: fish als Standard-Shell setzen
        if not self.set_fish_as_default_shell():
            print("❌ Fehler beim Setzen der Standard-Shell")
            sys.exit(1)
        
        # Schritt 5: config.fish erstellen
        if not self.create_fish_config():
            print("⚠️  Warnung: config.fish konnte nicht erstellt werden")
        
        # Schritt 6: Konfiguration überprüfen
        self.verify_setup()
        
        print("\n" + "=" * 70)
        print("✅ Installation abgeschlossen!")
        print("=" * 70)
        print("\n💡 Nächste Schritte:")
        print("   1. Melden Sie sich ab und wieder an")
        print("   2. Oder führen Sie in einem neuen Terminal 'exec fish' aus")
        print("   3. Passen Sie ~/.config/fish/config.fish nach Bedarf an")
        print("\n📚 Tipps für Arch Linux mit fish:")
        print("   - Installieren Sie 'fish-completions' für bessere Autocompletion")
        print("   - Nutzen Sie 'oh-my-fish' für erweiterte Funktionen")
        print("   - fish hat eingebaute Syntax-Highlighting und Autocompletion")
        print("   - Verwenden Sie 'fish_config' für die grafische Konfiguration")
        print("=" * 70)

if __name__ == '__main__':
    installer = FishInstallerArchLinux()
    installer.run()
