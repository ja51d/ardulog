#!/bin/bash
# Double-click this file to launch UAV Log Viewer.
# It cd's into the script's own folder so it works no matter where you put it.
cd "$(dirname "$0")"
exec python3 app.py
