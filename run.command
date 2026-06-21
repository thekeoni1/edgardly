#!/bin/bash
cd "$(dirname "$0")/app"
python3 app.py
echo ""
echo "App exited. Press Enter to close this window."
read
