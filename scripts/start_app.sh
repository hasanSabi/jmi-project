#!/bin/bash
set -e
echo "[start_app] Starting cloudstack service..."
systemctl start cloudstack
echo "[start_app] Done."
