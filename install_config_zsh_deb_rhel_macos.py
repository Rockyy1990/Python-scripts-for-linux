#!/usr/bin/env python3
"""
Skript zum Installieren und Konfigurieren von zsh als Standard-Shell
Unterstützt: Ubuntu/Debian, Fedora/RHEL, macOS
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

class ZshInstaller:
    def __init__(self):
        self.system = platform.system()
        self.distro = self._detect_distro()
        self.username = os.getenv('SUDO_USER') or os.getenv('USER')
        self.home_dir = Path.home()
        
    def _detect_distro(self):
        """Erkennt das Betriebssystem und die Distribution"""
        if self.system == 'Darwin':
            return 'macos'
        elif self.system == 'Linux':
            try:
                with open('/etc/os-release', 'r') as f:
                    content = f.read().lower()
                    if 'ubuntu' in content or 'debian' in content:
                        return 'debian'
                    elif 'fedora' in content or 'rhel' in content or 'centos' in content:
                        return 'fedora'
            except FileNotFoundError:
                pass
        return 'unknown'
    
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
    
    def install_zsh(self):
        """Installiert zsh basierend auf der Distribution"""
        print("\n📦 Installiere zsh...")
        
        if self.distro == 'debian':
            success, output = self._run_command('apt-get update', sudo=True)
            if not success:
                return False
            success, output = self._run_command('apt-get install -y zsh', sudo=True)
        
        elif self.distro == 'fedora':
            success, output = self._run_command('dnf install -y zsh', sudo=True)
        
        elif self.distro == 'macos':
            success, output = self._run_command('brew install zsh', sudo=False)
        
        else:
            print("❌ Distribution wird nicht erkannt. Bitte zsh manuell installieren.")
            return False
        
        if success:
            print("✅ zsh erfolgreich installiert")
            return True
        return False
    
    def verify_zsh_installation(self):
        """Überprüft, ob zsh installiert ist"""
        success, output = self._run_command('which zsh', check=False)
        if success:
            zsh_path = output.strip()
            print(f"✅ zsh gefunden unter: {zsh_path}")
            return zsh_path
        print("❌ zsh konnte nicht gefunden werden")
        return None
    
    def set_zsh_as_default_shell(self, zsh_path):
        """Setzt zsh als Standard-Shell für den aktuellen Benutzer"""
        print(f"\n🔄 Setze zsh als Standard-Shell für Benutzer '{self.username}'...")
        
        # Für aktuellen Benutzer
        command = f'usermod -s {zsh_path} {self.username}'
        success, output = self._run_command(command, sudo=True)
        
        if success:
            print(f"✅ zsh als Standard-Shell gesetzt")
            return True
        return False
    
    def create_zshrc(self):
        """Erstellt eine Basis .zshrc Konfigurationsdatei"""
        print("\n📝 Erstelle .zshrc Konfiguration...")
        
        zshrc_path = self.home_dir / '.zshrc'
        
        # Basis-Konfiguration
        zshrc_content = """# zsh Konfiguration
# Automatisch erstellt durch Installationsskript

# Grundlegende Einstellungen
setopt PROMPT_SUBST
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_FIND_NO_DUPS
setopt HIST_SAVE_NO_DUPS
setopt SHARE_HISTORY
setopt INC_APPEND_HISTORY

# Verlauf-Einstellungen
HISTFILE=~/.zsh_history
HISTSIZE=10000
SAVEHIST=10000

# Basis Prompt (kann später angepasst werden)
PS1='%n@%m:%~%# '

# Aliase
alias ls='ls --color=auto'
alias ll='ls -lah'
alias la='ls -A'
alias l='ls -CF'
alias grep='grep --color=auto'

# Umgebungsvariablen
export LANG=de_DE.UTF-8
export LC_ALL=de_DE.UTF-8

# Pfad-Erweiterung (falls nötig)
# export PATH="$PATH:/usr/local/bin"

# Zusätzliche Konfigurationen können hier hinzugefügt werden
"""
        
        try:
            # Sichern der existierenden .zshrc
            if zshrc_path.exists():
                backup_path = self.home_dir / '.zshrc.backup'
                zshrc_path.rename(backup_path)
                print(f"💾 Alte .zshrc gesichert unter: {backup_path}")
            
            # Neue .zshrc schreiben
            zshrc_path.write_text(zshrc_content)
            zshrc_path.chmod(0o644)
            
            print(f"✅ .zshrc erstellt unter: {zshrc_path}")
            return True
            
        except Exception as e:
            print(f"❌ Fehler beim Erstellen von .zshrc: {e}")
            return False
    
    def setup_system_variables(self):
        """Richtet Systemvariablen ein"""
        print("\n🔧 Richte Systemvariablen ein...")
        
        try:
            # Überprüfe ob /etc/shells zsh enthält
            with open('/etc/shells', 'r') as f:
                shells_content = f.read()
            
            zsh_path = self.verify_zsh_installation()
            if zsh_path and zsh_path not in shells_content:
                print("⚠️  zsh nicht in /etc/shells registriert. Registriere es...")
                command = f'echo {zsh_path} | sudo tee -a /etc/shells'
                success, output = self._run_command(command, sudo=False)
                if success:
                    print("✅ zsh zu /etc/shells hinzugefügt")
            else:
                print("✅ zsh bereits in /etc/shells registriert")
            
            return True
            
        except Exception as e:
            print(f"⚠️  Warnung beim Einrichten der Systemvariablen: {e}")
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
                        if 'zsh' in shell:
                            print(f"✅ zsh ist Standard-Shell für '{self.username}'")
                            print(f"   Shell: {shell}")
                        else:
                            print(f"⚠️  Standard-Shell ist nicht zsh: {shell}")
                        break
        except Exception as e:
            print(f"⚠️  Konnte Shell nicht überprüfen: {e}")
        
        # Überprüfe .zshrc
        zshrc_path = self.home_dir / '.zshrc'
        if zshrc_path.exists():
            print(f"✅ .zshrc existiert unter: {zshrc_path}")
        else:
            print(f"⚠️  .zshrc nicht gefunden unter: {zshrc_path}")
    
    def run(self):
        """Führt den vollständigen Installationsprozess aus"""
        print("=" * 60)
        print("🚀 zsh Installations- und Konfigurationsskript")
        print("=" * 60)
        print(f"System: {self.system}")
        print(f"Distribution: {self.distro}")
        print(f"Benutzer: {self.username}")
        print(f"Home-Verzeichnis: {self.home_dir}")
        print("=" * 60)
        
        # Überprüfe Root-Rechte
        if os.geteuid() != 0 and self.distro != 'unknown':
            print("⚠️  Dieses Skript benötigt sudo-Rechte. Bitte mit sudo ausführen.")
            print("   Beispiel: sudo python3 install_zsh.py")
            sys.exit(1)
        
        # Schritt 1: zsh installieren
        if not self.install_zsh():
            print("❌ Installation abgebrochen: zsh konnte nicht installiert werden")
            sys.exit(1)
        
        # Schritt 2: zsh-Pfad überprüfen
        zsh_path = self.verify_zsh_installation()
        if not zsh_path:
            print("❌ Installation abgebrochen: zsh-Pfad konnte nicht ermittelt werden")
            sys.exit(1)
        
        # Schritt 3: Systemvariablen einrichten
        self.setup_system_variables()
        
        # Schritt 4: zsh als Standard-Shell setzen
        if not self.set_zsh_as_default_shell(zsh_path):
            print("❌ Fehler beim Setzen der Standard-Shell")
            sys.exit(1)
        
        # Schritt 5: .zshrc erstellen
        if not self.create_zshrc():
            print("⚠️  Warnung: .zshrc konnte nicht erstellt werden")
        
        # Schritt 6: Konfiguration überprüfen
        self.verify_setup()
        
        print("\n" + "=" * 60)
        print("✅ Installation abgeschlossen!")
        print("=" * 60)
        print("\n💡 Nächste Schritte:")
        print("   1. Melden Sie sich ab und wieder an")
        print("   2. Oder führen Sie 'exec zsh' aus")
        print("   3. Passen Sie ~/.zshrc nach Bedarf an")
        print("=" * 60)

if __name__ == '__main__':
    installer = ZshInstaller()
    installer.run()
