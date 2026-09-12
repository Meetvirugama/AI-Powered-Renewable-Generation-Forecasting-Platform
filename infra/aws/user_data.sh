#!/usr/bin/env bash
#
# EC2 bootstrap, run once at first boot by cloud-init.
#
# Keep this short. Anything complicated belongs in the image or in a deploy step,
# because user-data failures are invisible until you go looking in
# /var/log/cloud-init-output.log, usually at the worst possible moment.
set -euxo pipefail

dnf update -y
dnf install -y docker git postgresql15 jq

# The SSM agent is preinstalled on AL2023 but not always enabled. Without it
# there is no way into this box at all -- there is no key pair and no port 22.
systemctl enable --now amazon-ssm-agent

systemctl enable --now docker
usermod -aG docker ec2-user

# Compose v2 as a Docker CLI plugin.
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL \
    "https://github.com/docker/compose/releases/download/v2.32.1/docker-compose-linux-x86_64" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

mkdir -p /opt/renewable
cd /opt/renewable

# Only the deploy assets are needed on the host; the application itself ships as
# an image. A sparse checkout keeps this to a few kB.
git clone --depth 1 --filter=blob:none --sparse \
    https://github.com/Meetvirugama/AI-Powered-Renewable-Generation-Forecasting-Platform.git .
git sparse-checkout set docker-compose.prod.yml infra/docker config

chown -R ec2-user:ec2-user /opt/renewable

# Render .env from SSM. Runs again on every deploy so rotated keys are picked up.
bash infra/docker/fetch_secrets.sh || echo "fetch_secrets failed; run it by hand after seeding SSM"

# Log rotation. A t3.large root volume fills with container logs in about a week
# of a chatty service, and a full disk looks exactly like an application crash.
cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "50m", "max-file": "3" }
}
JSON
systemctl restart docker

echo "bootstrap complete: $(date -Is)"
