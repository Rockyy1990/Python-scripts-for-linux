#!/usr/bin/env python3
"""
Skript zum Installieren und Konfigurieren von zsh als Standard-Shell für Arch Linux
Verwendet pacman als Paketmanager
"""

import os
import sys
import subprocess
from pathlib import Path

class ZshInstallerArchLinux:
    def __init__(self):
        self.username = os.getenv('SUDO_USER') or os.getenv('USER')
        self.home_dir = Path.home()
        self.zsh_path = None
        
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
        """Installiert zsh mit pacman"""
        print("\n📦 Installiere zsh mit pacman...")
        
        success, output = self._run_command('pacman -Sy', sudo=True)
        if not success:
            return False
        
        success, output = self._run_command('pacman -S --noconfirm zsh', sudo=True)
        
        if success:
            print("✅ zsh erfolgreich installiert")
            return True
        
        print("❌ zsh konnte nicht installiert werden")
        return False
    
    def verify_zsh_installation(self):
        """Überprüft, ob zsh installiert ist und gibt den Pfad zurück"""
        success, output = self._run_command('which zsh', check=False)
        if success:
            self.zsh_path = output.strip()
            print(f"✅ zsh gefunden unter: {self.zsh_path}")
            return self.zsh_path
        
        print("❌ zsh konnte nicht gefunden werden")
        return None
    
    def register_zsh_in_shells(self):
        """Registriert zsh in /etc/shells"""
        print("\n🔧 Registriere zsh in /etc/shells...")
        
        try:
            with open('/etc/shells', 'r') as f:
                shells_content = f.read()
            
            if self.zsh_path in shells_content:
                print("✅ zsh bereits in /etc/shells registriert")
                return True
            
            print("⚠️  zsh nicht in /etc/shells. Registriere es...")
            command = f'echo {self.zsh_path} | sudo tee -a /etc/shells > /dev/null'
            success, output = self._run_command(command, sudo=False)
            
            if success:
                print("✅ zsh zu /etc/shells hinzugefügt")
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Fehler beim Registrieren: {e}")
            return False
    
    def set_zsh_as_default_shell(self):
        """Setzt zsh als Standard-Shell für den aktuellen Benutzer"""
        print(f"\n🔄 Setze zsh als Standard-Shell für Benutzer '{self.username}'...")
        
        command = f'usermod -s {self.zsh_path} {self.username}'
        success, output = self._run_command(command, sudo=True)
        
        if success:
            print(f"✅ zsh als Standard-Shell gesetzt")
            return True
        
        print("❌ Fehler beim Setzen der Standard-Shell")
        return False
    
    def create_zshrc(self):
        """Erstellt eine Basis .zshrc Konfigurationsdatei"""
        print("\n📝 Erstelle .zshrc Konfiguration...")
        
        zshrc_path = self.home_dir / '.zshrc'
        
        # Basis-Konfiguration für Arch Linux
        zshrc_content = """# zsh Konfiguration für Arch Linux
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

# Basis Prompt
PS1='%n@%m:%~%# '

# Aliase
alias ls='ls --color=auto'
alias ll='ls -lah'
alias la='ls -A'
alias l='ls -CF'
alias grep='grep --color=auto'
alias pacman='pacman --color=auto'

# Umgebungsvariablen
export LANG=de_DE.UTF-8
export LC_ALL=de_DE.UTF-8

# Arch Linux spezifische Einstellungen
export EDITOR=nano
export VISUAL=nano

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
            
            # Stelle sicher, dass der Benutzer Eigentümer ist
            os.chown(zshrc_path, os.getuid(), os.getgid())
            
            print(f"✅ .zshrc erstellt unter: {zshrc_path}")
            return True
            
        except Exception as e:
            print(f"❌ Fehler beim Erstellen von .zshrc: {e}")
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
        
        # Überprüfe /etc/shells
        try:
            with open('/etc/shells', 'r') as f:
                if self.zsh_path in f.read():
                    print(f"✅ zsh ist in /etc/shells registriert")
                else:
                    print(f"⚠️  zsh ist nicht in /etc/shells registriert")
        except Exception as e:
            print(f"⚠️  Konnte /etc/shells nicht überprüfen: {e}")
    
    def run(self):
        """Führt den vollständigen Installationsprozess aus"""
        print("=" * 70)
        print("🚀 zsh Installations- und Konfigurationsskript für Arch Linux")
        print("=" * 70)
        print(f"Benutzer: {self.username}")
        print(f"Home-Verzeichnis: {self.home_dir}")
        print("=" * 70)
        
        # Überprüfe Root-Rechte
        if os.geteuid() != 0:
            print("❌ Dieses Skript benötigt sudo-Rechte.")
            print("   Bitte mit sudo ausführen:")
            print("   sudo python3 install_zsh.py")
            sys.exit(1)
        
        # Schritt 1: zsh installieren
        if not self.install_zsh():
            print("❌ Installation abgebrochen: zsh konnte nicht installiert werden")
            sys.exit(1)
        
        # Schritt 2: zsh-Pfad überprüfen
        if not self.verify_zsh_installation():
            print("❌ Installation abgebrochen: zsh-Pfad konnte nicht ermittelt werden")
            sys.exit(1)
        
        # Schritt 3: zsh in /etc/shells registrieren
        if not self.register_zsh_in_shells():
            print("⚠️  Warnung: zsh konnte nicht in /etc/shells registriert werden")
        
        # Schritt 4: zsh als Standard-Shell setzen
        if not self.set_zsh_as_default_shell():
            print("❌ Fehler beim Setzen der Standard-Shell")
            sys.exit(1)
        
        # Schritt 5: .zshrc erstellen
        if not self.create_zshrc():
            print("⚠️  Warnung: .zshrc konnte nicht erstellt werden")
        
        # Schritt 6: Konfiguration überprüfen
        self.verify_setup()
        
        print("\n" + "=" * 70)
        print("✅ Installation abgeschlossen!")
        print("=" * 70)
        print("\n💡 Nächste Schritte:")
        print("   1. Melden Sie sich ab und wieder an")
        print("   2. Oder führen Sie in einem neuen Terminal 'exec zsh' aus")
        print("   3. Passen Sie ~/.zshrc nach Bedarf an")
        print("\n📚 Tipps für Arch Linux:")
        print("   - Installieren Sie 'oh-my-zsh' für erweiterte Funktionen")
        print("   - Nutzen Sie 'pacman -S zsh-completions' für bessere Autocompletion")
        print("=" * 70)

if __name__ == '__main__':
    installer = ZshInstallerArchLinux()
    installer.run()
