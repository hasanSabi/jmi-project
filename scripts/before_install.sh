#!/bin/bash
set -e
echo "[before_install] Stopping app if running..."
systemctl stop cloudstack 2>/dev/null || true

echo "[before_install] Installing system deps..."
dnf install -y python3.11 python3.11-pip python3.11-devel gcc mysql-devel 2>/dev/null \
  || yum install -y python3 python3-pip gcc mysql-devel 2>/dev/null || true

mkdir -p /opt/app
chown ec2-user:ec2-user /opt/app
echo "[before_install] Done."
