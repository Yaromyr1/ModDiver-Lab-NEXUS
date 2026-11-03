#!/bin/sh
set -eu
APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
MODDIVER_INSTALL_VARIANT=ModDiverLab
if [ -f "$APP_DIR/source/nexus-build.json" ]; then MODDIVER_INSTALL_VARIANT=ModDiverLabNexus; fi
DISTROBOX_NAME=""
case "${1:-}" in
    --distrobox) DISTROBOX_NAME=${2:?Missing Distrobox name} ;;
    --check|--print-dependencies|'') ;;
    *) echo "Usage: sh install-linux.sh [--check | --print-dependencies | --distrobox NAME]" >&2; exit 2 ;;
esac

# ID_LIKE covers derivatives such as Mint, Pop!_OS, Zorin, PikaOS and Manjaro.
ID=unknown
ID_LIKE=""
VERSION_ID=""
if [ -r "${MODDIVER_OS_RELEASE:-/etc/os-release}" ]; then
    . "${MODDIVER_OS_RELEASE:-/etc/os-release}"
fi
family=unknown
case " $ID $ID_LIKE " in
    *' debian '*|*' ubuntu '*) family=debian ;;
    *' fedora '*) family=fedora ;;
    *' arch '*|*' archlinux '*) family=arch ;;
    *' opensuse '*|*' opensuse-tumbleweed '*|*' opensuse-leap '*|*' suse '*) family=suse ;;
    *' alpine '*) family=alpine ;;
esac
# Fall back for distributions that omit ID_LIKE.
if [ "$family" = unknown ]; then
    if command -v apt-get >/dev/null 2>&1; then family=debian
    elif command -v dnf >/dev/null 2>&1; then family=fedora
    elif command -v pacman >/dev/null 2>&1; then family=arch
    elif command -v zypper >/dev/null 2>&1; then family=suse
    elif command -v apk >/dev/null 2>&1; then family=alpine
    fi
fi
case "$family" in
    debian) packages='python3 python3-tk libsodium23 luajit libarchive-tools xdg-utils' ;;
    fedora) packages='python3 python3-tkinter libsodium luajit bsdtar xdg-utils' ;;
    arch) packages='python tk libsodium luajit libarchive xdg-utils' ;;
    suse) packages='python3 python3-tk libsodium23 luajit bsdtar xdg-utils' ;;
    alpine) packages='python3 python3-tkinter libsodium luajit libarchive-tools xdg-utils' ;;
    *) packages='' ;;
esac
if [ "${1:-}" = --print-dependencies ]; then
    printf '%s: %s\n' "$family" "$packages"
    exit 0
fi
check_dependencies() {
    python3 -c 'import sys, tkinter, ctypes.util; assert sys.version_info >= (3,10); assert ctypes.util.find_library("sodium")' >/dev/null 2>&1 &&
    command -v luajit >/dev/null 2>&1 && command -v bsdtar >/dev/null 2>&1 && command -v xdg-open >/dev/null 2>&1
}
if [ "${1:-}" = --check ]; then
    if check_dependencies; then echo 'All Linux dependencies are available.'; exit 0; fi
    echo "Missing dependencies. Required packages ($family): $packages" >&2
    exit 1
fi
if [ "$(id -u)" = 0 ]; then
    echo 'Run this installer as your normal desktop user, not root.' >&2
    exit 1
fi
# Never use pacman/dnf to modify the base image on immutable gaming desktops.
if [ -z "$DISTROBOX_NAME" ]; then
    case "$ID" in
        steamos|bazzite|silverblue|kinoite|aurora|bluefin|aeon|kalpa) echo 'Use: sh install-linux-distrobox.sh (requires Distrobox and a container runtime).' >&2; exit 1 ;;
    esac
    if [ -e /run/ostree-booted ]; then
        echo 'Use: sh install-linux-distrobox.sh on this Atomic desktop.' >&2
        exit 1
    fi
fi
if ! check_dependencies; then
    echo 'Installing system dependencies. Your administrator password may be requested.'
    command -v sudo >/dev/null 2>&1 || { echo 'Install sudo or ask your administrator to install the listed dependencies.' >&2; exit 1; }
    case "$family" in
        debian) sudo apt-get update; sudo apt-get install -y $packages ;;
        fedora) sudo dnf install -y $packages ;;
        arch) sudo pacman -S --needed --noconfirm $packages ;;
        suse) sudo zypper --non-interactive install $packages ;;
        alpine) sudo apk add $packages ;;
        *) echo 'Install Python 3.10+, Tkinter, libsodium, LuaJIT, bsdtar and xdg-utils, then rerun.' >&2; exit 1 ;;
    esac
fi
check_dependencies || { echo 'Dependencies are still missing or Python is older than 3.10. See README-Linux.md.' >&2; exit 1; }
export YAO_FORGE_DISTROBOX="$DISTROBOX_NAME"
python3 - "$APP_DIR" <<'PY'
from pathlib import Path
import os, shutil, sys
source = Path(sys.argv[1])
data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))
nexus = (source/'source/nexus-build.json').is_file()
target = data/('ModDiverLabNexus' if nexus else 'ModDiverLab')/'bootstrap'
target.mkdir(parents=True, exist_ok=True)
if source.resolve() != target.resolve():
    shutil.copytree(source/'source', target/'source', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', 'tests', '_work'))
    shutil.copy2(source/'run-linux.sh', target/'run-linux.sh')
(target/'run-linux.sh').chmod(0o755)
# Desktop Exec has its own quoting rules, independent of shell quoting.
def quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'
applications = data/'applications'
applications.mkdir(parents=True, exist_ok=True)
launcher = applications/('moddiver-laboratory-nexus.desktop' if nexus else 'moddiver-laboratory.desktop')
launcher.write_text('[Desktop Entry]\nType=Application\nName=' + ('ModDiver Laboratory Nexus' if nexus else 'ModDiver Laboratory')+'\n'
                    'Comment=Helldivers 2 mod manager and editor\n'
                    'Exec=' + ('distrobox enter --name ' + quote(os.environ['YAO_FORGE_DISTROBOX']) + ' -- env ' + quote('YAO_FORGE_DISTROBOX=' + os.environ['YAO_FORGE_DISTROBOX']) + ' sh ' if os.environ.get('YAO_FORGE_DISTROBOX') else 'sh ') + quote(target/'run-linux.sh') + '\n'
                    'Icon=' + str(target/'source/branding/icon_256.png') + '\nTerminal=false\nCategories=Game;Utility;\n', encoding='utf-8')
launcher.chmod(0o755)
print('Installed. Open ModDiver Laboratory from your application menu.')
PY
if command -v update-desktop-database >/dev/null; then
    update-desktop-database "${XDG_DATA_HOME:-$HOME/.local/share}/applications" || true
fi
exec sh "${XDG_DATA_HOME:-$HOME/.local/share}/$MODDIVER_INSTALL_VARIANT/bootstrap/run-linux.sh"
