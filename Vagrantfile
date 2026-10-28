# VM Ubuntu 22.04 qui héberge toute la pile (Docker + Kong + 4 services).
#   vagrant up          -> crée la VM, installe Docker, lance la pile
#   vagrant ssh         -> se connecter ; le projet est dans /vagrant
#   http://localhost:8000/api/v1/dashboard/structures/1  depuis la machine hôte
Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/jammy64"
  config.vm.hostname = "gateway-sante"

  # Ports accessibles depuis la machine hôte (navigateur, Postman, curl)
  config.vm.network "forwarded_port", guest: 8000, host: 8000, host_ip: "127.0.0.1" # Kong proxy
  config.vm.network "forwarded_port", guest: 8001, host: 8001, host_ip: "127.0.0.1" # Kong admin
  config.vm.network "forwarded_port", guest: 9000, host: 9000, host_ip: "127.0.0.1" # Swagger de l'agrégateur (/docs)

  config.vm.provider "virtualbox" do |vb|
    vb.name = "gateway-sante"
    vb.memory = 3072
    vb.cpus = 2
  end

  config.vm.provision "shell", inline: <<-SHELL
    set -e
    export DEBIAN_FRONTEND=noninteractive
    if ! command -v docker >/dev/null; then
      apt-get update -y
      apt-get install -y ca-certificates curl jq python3-pip
      curl -fsSL https://get.docker.com | sh       # Docker Engine + plugin compose
      usermod -aG docker vagrant
    fi
    pip3 install -q -r /vagrant/requirements-dev.txt
    cd /vagrant
    python3 scripts/init_data.py --check            # bases de test présentes et cohérentes
    docker compose up -d --build --wait             # attend que les 5 conteneurs soient "healthy"
    echo "Pile démarrée : curl http://localhost:8000/api/v1/dashboard/structures/1"
  SHELL
end
