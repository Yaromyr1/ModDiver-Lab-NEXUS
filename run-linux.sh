#!/bin/sh
set -eu

APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SOURCE_DIR="$APP_DIR/source"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ModDiver Laboratory needs Python 3.10 or newer." >&2
    exit 1
fi

if ! python3 -c 'import sys; assert sys.version_info >= (3,10); import tkinter; import ctypes.util; assert ctypes.util.find_library("sodium")' >/dev/null 2>&1; then
    echo "ModDiver Laboratory needs Python 3.10+, Tkinter and libsodium." >&2
    echo "Run sh install-linux.sh to install dependencies for your distribution." >&2
    echo "See README-Linux.md in this folder for the complete guide." >&2
    exit 1
fi

exec python3 "$SOURCE_DIR/linux_launcher.py" "$@"
