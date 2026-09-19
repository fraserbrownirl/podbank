#!/bin/bash
# Vast on-start for Dolphin Network. Replace __LINK__ with a fresh Worker Link
# from https://v2.dphn.ai (Worker Link button). Do not commit real links.
# No set -e (crash-loop during pull is normal). No sudo (image is root).
mkdir -p /workspace && cd /workspace
export HF_HOME=/root/.cache/dolphinpod-worker/cache
export HF_HUB_CACHE=/root/.cache/dolphinpod-worker/cache/hub
export HF_HUB_OFFLINE=0
curl -fL --progress-bar "https://updates.dphn.ai/dolphinpod-worker-v2_linux_amd64" -o dolphinpod-worker
chmod +x dolphinpod-worker
code=$(curl -4 -s --max-time 8 -o /dev/null -w '%{http_code}' https://huggingface.co || true)
case "$code" in
  200|301|302|307|308) ;;
  *) echo "EGRESS FAIL http=$code" > /workspace/selfboot.log; exit 0 ;;
esac
while true; do
  echo "$(date -u +%FT%TZ) bootstrap start" >> /workspace/selfboot.log
  ./dolphinpod-worker bootstrap "__LINK__" >> /workspace/selfboot.log 2>&1
  echo "$(date -u +%FT%TZ) bootstrap exited $?" >> /workspace/selfboot.log
  sleep 8
done
