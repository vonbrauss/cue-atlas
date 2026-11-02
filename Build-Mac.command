#!/bin/bash
set -e
cd "$(dirname "$0")"
python3 -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11 or newer is required. Install Python 3.12, then try again."'
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt pyinstaller
APP_VERSION=$(.venv/bin/python -c 'from cueatlas import __version__; print(__version__)')
mkdir -p dist
BUILD_OUTPUT=$(mktemp -d "$PWD/dist/CueAtlas-$APP_VERSION-XXXXXX")
.venv/bin/python -m PyInstaller --noconfirm --clean --distpath "$BUILD_OUTPUT" "Cue Atlas.spec"
printf '\nBuilt Cue Atlas %s:\n%s/Cue Atlas.app\n' "$APP_VERSION" "$BUILD_OUTPUT"
open "$BUILD_OUTPUT"
