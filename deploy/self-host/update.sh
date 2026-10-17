#!/usr/bin/env bash
# Keep a self-hosted SiteScore API in step with main.
#
# Copy this script OUT of the repo and run the copy from cron. If cron ran this file in
# place, whoever can push to main could change what runs on your machine; a copy you
# update by hand (after reading the diff) means main can only change what runs inside
# Docker (the image build and the locked-down container):
#
#   install -D -m 755 deploy/self-host/update.sh ~/bin/sitescore-update
#   */5 * * * * REPO=/path/to/SiteScore SITESCORE_CORS_ORIGINS=https://ar13x3.github.io ~/bin/sitescore-update >> ~/sitescore-update.log 2>&1
#
# When main has moved (or the container isn't running) it pulls, rebuilds the image and
# swaps the container. The new image is built before the old container stops, so a
# deploy costs a few seconds of downtime. The container listens on 127.0.0.1 only; put
# Tailscale Funnel, a tunnel or a reverse proxy in front to make it public.
#
# The container runs locked down: a read-only root filesystem (tmpfs where the app
# writes), no capabilities, no privilege escalation and a process cap. It sits on its own
# bridge (br-sitescore) with public DNS, so sitescore-fence can cut it off from the LAN.
#
#   REPO                    the SiteScore checkout (default: the one this script is in)
#   SITESCORE_CORS_ORIGINS  sites allowed to call the API from a browser (the Pages site)
#   SITESCORE_PORT          local port (default 7860)
#   SITESCORE_CPUS / SITESCORE_MEMORY  container limits (default 2 CPUs, 1536m)
set -euo pipefail
REPO=${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}
NET=sitescore-net
[ -f "$REPO/Dockerfile" ] || { echo "REPO=$REPO is not a SiteScore checkout; set REPO" >&2; exit 1; }
cd "$REPO"

exec 9>/tmp/sitescore-update.lock
flock -n 9 || exit 0                       # a slow build is still running

docker network inspect "$NET" > /dev/null 2>&1 ||
  docker network create --driver bridge --subnet 172.31.255.0/24 \
    -o com.docker.network.bridge.name=br-sitescore "$NET" > /dev/null

git fetch -q origin main
running=$(docker ps -q --filter "name=^sitescore$" --filter "network=$NET")
if [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] && [ -n "$running" ]; then
  exit 0                                   # up to date and up
fi

git reset -q --hard origin/main
docker build -q -t sitescore:latest . > /dev/null
docker rm -f sitescore > /dev/null 2>&1 || true
# The app writes only its data store (demo pack restore, catalog), its cache, /tmp and
# $HOME. The Demo container CI job runs the image with these same flags.
docker run -d --name sitescore --restart unless-stopped \
  -p "127.0.0.1:${SITESCORE_PORT:-7860}:7860" \
  --cpus "${SITESCORE_CPUS:-2}" --memory "${SITESCORE_MEMORY:-1536m}" \
  --network "$NET" --dns 1.1.1.1 --dns 9.9.9.9 \
  --read-only \
  --tmpfs /tmp:rw,size=64m \
  --tmpfs /app/data/processed:rw,uid=1000,gid=1000,size=512m \
  --tmpfs /app/.local:rw,uid=1000,gid=1000,size=128m \
  --tmpfs /home/app:rw,uid=1000,gid=1000,size=32m \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 \
  -e SITESCORE_CORS_ORIGINS="${SITESCORE_CORS_ORIGINS:-}" \
  sitescore:latest > /dev/null
docker image prune -f > /dev/null
echo "$(date -Is) deployed $(git rev-parse --short HEAD)"
