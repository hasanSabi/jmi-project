#!/bin/bash
set -e
echo "[after_install] Setting up virtualenv and installing deps..."

cd /opt/app

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

venv/bin/pip install --upgrade pip --quiet
venv/bin/pip install -r requirements.txt --quiet

# Copy systemd unit (may overwrite)
cp /opt/app/cloudstack.service /etc/systemd/system/cloudstack.service
systemctl daemon-reload
systemctl enable cloudstack

chown -R ec2-user:ec2-user /opt/app
echo "[after_install] Done."
