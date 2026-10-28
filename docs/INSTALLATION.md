# Installation des outils prérequis

Ce document décrit l'installation des outils qui ne s'installent pas avec le projet.
Suivez uniquement la section de l'option choisie dans le [README](../README.md#3-prérequis).

| Outil | Option A (Docker Compose) | Option B (VM Vagrant) |
|---|---|---|
| Git | requis | requis |
| Docker Engine + Compose v2 | requis | installé automatiquement dans la VM |
| Python ≥ 3.10, `jq`, bash | pour les tests | installés automatiquement dans la VM |
| VirtualBox 7 | — | requis |
| Vagrant ≥ 2.3 | — | requis |

---

## 1. Git

- **Windows** : `winget install --id Git.Git -e` dans PowerShell, ou l'installeur de <https://git-scm.com/download/win>.
- **macOS** : `xcode-select --install` (ou `brew install git`).
- **Ubuntu / Debian** : `sudo apt-get update && sudo apt-get install -y git`.

Vérification : `git --version`.

---

## 2. Option A — Docker

### Ubuntu / Debian

```bash
curl -fsSL https://get.docker.com | sh          # Docker Engine + plugin Compose v2
sudo usermod -aG docker $USER                    # utiliser docker sans sudo
newgrp docker                                    # ou se déconnecter / reconnecter
sudo apt-get install -y python3-pip jq           # pour les tests
```

### Windows et macOS

Installer **Docker Desktop** depuis <https://www.docker.com/products/docker-desktop/>
(Windows : `winget install --id Docker.DockerDesktop -e`). Sous Windows, Docker Desktop
utilise WSL 2 ; lancer les tests de bout en bout (`tests/e2e_kong.sh`, qui nécessite bash
et `jq`) depuis un terminal WSL Ubuntu.

### Vérification

```bash
docker --version
docker compose version        # doit afficher v2.x
docker run --rm hello-world
```

---

## 3. Option B — VirtualBox et Vagrant

### Windows

```powershell
winget install --id Oracle.VirtualBox -e
winget install --id Hashicorp.Vagrant -e
```

Redémarrer Windows après l'installation de Vagrant. Sinon, installeurs officiels :
<https://www.virtualbox.org/wiki/Downloads> et <https://developer.hashicorp.com/vagrant/install>.

### macOS (processeur Intel)

```bash
brew install --cask virtualbox vagrant
```

Sur Mac à processeur Apple (M1 à M4), la box `ubuntu/jammy64` n'est pas compatible :
utiliser l'option A avec Docker Desktop.

### Ubuntu / Debian

```bash
sudo apt-get install -y virtualbox
# Vagrant depuis le dépôt officiel HashiCorp :
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt-get update && sudo apt-get install -y vagrant
```

### Vérification

```bash
VBoxManage --version
vagrant --version
```

### Problèmes fréquents

| Symptôme | Correction |
|---|---|
| `VT-x is not available` ou la VM ne démarre pas | Activer la virtualisation (Intel VT-x / AMD-V) dans le BIOS/UEFI |
| VM très lente sous Windows | Hyper-V ou WSL 2 actif en même temps que VirtualBox ; c'est supporté mais plus lent |
| `port 8000 is already in use` | Libérer le port, ou changer `host:` dans le `Vagrantfile` |
| Fichiers `.sh` en erreur `\r: command not found` | Recloner après `git config --global core.autocrlf input` (le dépôt impose déjà les fins de ligne Unix via `.gitattributes`) |

---

## 4. Installation du projet

Une fois les outils installés, reprendre le [README, section 4](../README.md#4-installation).
