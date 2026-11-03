#!/bin/sh
set -eu
APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
NAME=moddiver-laboratory
if [ "$(id -u)" = 0 ]; then
    echo 'Run this installer as your normal desktop user.' >&2
    exit 1
fi
if ! command -v distrobox >/dev/null 2>&1; then
    echo 'Install Distrobox and Podman (or Docker) using your OS documentation, then rerun.' >&2
    echo 'See README-Linux.md for SteamOS and Bazzite instructions.' >&2
    exit 1
fi
# Distrobox shares your home directory, display and game files with the container.
# Its user-level container survives base OS updates.
if ! distrobox list --no-color | awk -F '|' '{gsub(/ /,"",$2); print $2}' | grep -Fx "$NAME" >/dev/null; then
    distrobox create --yes --name "$NAME" --image docker.io/library/ubuntu:24.04
fi
exec distrobox enter --name "$NAME" -- sh "$APP_DIR/install-linux.sh" --distrobox "$NAME"
