#!/usr/bin/env bash
# Keep a self-hosted SiteScore API in step with main. Run it from cron every few minutes:
#
#   */5 * * * * SITESCORE_CORS_ORIGINS=https://ar13x3.github.io /path/to/SiteScore/deploy/self-host/update.sh >> ~/sitescore-update.log 2>&1
#
# When main has moved (or the container isn't running) it pulls, rebuilds the image and
# swaps the container. The new image is built before the old container stops, so a
# deploy costs a few seconds of downtime. The container listens on 127.0.0.1 only; put
# Tailscale Funnel, a tunnel or a reverse proxy in front to make it public.
#
#   SITESCORE_CORS_ORIGINS  sites allowed to call the API from a browser (the Pages site)
#   SITESCORE_PORT          local port (default 7860)
#   SITESCORE_CPUS / SITESCORE_MEMORY  container limits (default 2 CPUs, 1536m)
set -euo pipefail
cd "$(dirname "$0")/../.."

exec 9>/tmp/sitescore-update.lock
flock -n 9 || exit 0                       # a slow build is still running

git fetch -q origin main
running=$(docker ps -q --filter "name=^sitescore$")
if [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] && [ -n "$running" ]; then
  exit 0                                   # up to date and up
fi

git reset -q --hard origin/main
docker build -q -t sitescore:latest . > /dev/null
docker rm -f sitescore > /dev/null 2>&1 || true
docker run -d --name sitescore --restart unless-stopped \
  -p "127.0.0.1:${SITESCORE_PORT:-7860}:7860" \
  --cpus "${SITESCORE_CPUS:-2}" --memory "${SITESCORE_MEMORY:-1536m}" \
  -e SITESCORE_CORS_ORIGINS="${SITESCORE_CORS_ORIGINS:-}" \
  sitescore:latest > /dev/null
docker image prune -f > /dev/null
echo "$(date -Is) deployed $(git rev-parse --short HEAD)"
