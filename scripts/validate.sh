#!/bin/bash
set -e
echo "[validate] Checking /health endpoint..."
sleep 5

for i in {1..10}; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/health)
  if [ "$STATUS" = "200" ]; then
    echo "[validate] Health check passed (HTTP 200)."
    exit 0
  fi
  echo "[validate] Attempt $i — got HTTP $STATUS, retrying in 5s..."
  sleep 5
done

echo "[validate] FAILED — /health did not return 200 after 10 attempts."
exit 1
