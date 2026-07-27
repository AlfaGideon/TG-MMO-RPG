#!/bin/bash
set -e

# Activate venv
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Create data dir
mkdir -p data

# Run bot in background
echo "Starting bot..."
python -m bot.main &
BOT_PID=$!

# Run admin panel in background
echo "Starting admin panel on http://localhost:8000 ..."
python -m admin.main &
ADMIN_PID=$!

echo "Bot PID: $BOT_PID"
echo "Admin PID: $ADMIN_PID"
echo "Press Ctrl+C to stop both"

trap "kill $BOT_PID $ADMIN_PID; exit" INT TERM
wait
