#!/bin/bash
# keep_alive.sh - Watchdog to ensure the bot keeps running

BOT_DIR="/home/carnage/Downloads/volume-bot-main"
PYTHON_BIN="$BOT_DIR/.venv/bin/python3"
BOT_SCRIPT="bot.py"
LOG_FILE="$BOT_DIR/bot_output.log"

cd "$BOT_DIR"

while true; do
    echo "[$(date)] Starting bot..." >> "$LOG_FILE"
    $PYTHON_BIN $BOT_SCRIPT >> "$LOG_FILE" 2>&1
    echo "[$(date)] Bot crashed or stopped with exit code $?. Restarting in 5 seconds..." >> "$LOG_FILE"
    sleep 5
done
