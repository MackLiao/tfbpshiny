#!/bin/bash
# Cloud-init script for TFBPShiny EC2 instance (Amazon Linux 2023).
# Installs Docker, clones the repo, and prepares the deployment directory.
#
# The compose stack is NOT auto-started — secrets must be copied first:
#   scp -r .envs/ ec2-user@<public_ip>:/opt/tfbpshiny/
#   ssh ec2-user@<public_ip>
#   screen -S docker
#   cd /opt/tfbpshiny && docker compose -f production.yml up -d --build
set -euo pipefail

# Update all packages, then install Docker, git, and screen
dnf update -y
dnf install -y docker git screen
systemctl enable --now docker

# Add ec2-user to the docker group so it can run docker without sudo
usermod -aG docker ec2-user

# Install Docker Compose plugin (v2)
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL \
    "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Install Docker Buildx plugin (not bundled in Amazon Linux 2023 Docker package)
curl -SL \
    "https://github.com/docker/buildx/releases/download/v0.32.1/buildx-v0.32.1.linux-amd64" \
    -o /usr/local/lib/docker/cli-plugins/docker-buildx
chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx

# Clone the repo
git clone https://github.com/BrentLab/tfbpshiny.git /opt/tfbpshiny
chown -R ec2-user:ec2-user /opt/tfbpshiny

echo "=== tfbpshiny deployment ready ==="
echo "Next steps:"
echo "  1. scp -r .envs/ ec2-user@$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):/opt/tfbpshiny/"
echo "  2. ssh ec2-user@<public_ip>"
echo "  3. cd /opt/tfbpshiny && docker compose -f production.yml up -d --build"
