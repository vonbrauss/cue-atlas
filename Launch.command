#!/bin/bash
set -e
cd "$(dirname "$0")"
python3 -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11 or newer is required. Install Python 3.12, then try again."'
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
exec .venv/bin/python main.py
