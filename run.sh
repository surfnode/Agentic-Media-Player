#!/bin/bash

# Move to the directory where this script lives
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Set PYTHONPATH so absolute imports work
export PYTHONPATH="$DIR/src:$PYTHONPATH"

# Explicitly activate the project's virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "[!] Virtual environment 'venv' not found in $DIR"
    exit 1
fi

echo "[*] Cleaning up existing ports..."
# Kill any lingering worker processes on your app's ports
# (5563 player-progress and 5564 voice-meter were missing before)
fuser -k 5555/tcp 5556/tcp 5557/tcp 5559/tcp 5560/tcp 5561/tcp 5562/tcp 5563/tcp 5564/tcp 2>/dev/null

# The TTS worker binds no port (it only connects), so fuser cannot see it.
# A stale TTS process would double-speak - kill it by command line instead.
pkill -f "python.*agentic_player/workers/tts_worker\.py" 2>/dev/null

# Cleanup child processes when the UI closes
trap "kill 0" EXIT

echo "[*] Starting Agentic Media Player Services..."

# Start background workers using the activated venv python
python src/agentic_player/workers/player_worker.py &
python src/agentic_player/workers/fetcher_worker.py &
python src/agentic_player/workers/voice_worker.py &
python src/agentic_player/agent/router_worker.py &
python src/agentic_player/workers/tts_worker.py &

# Launch the primary UI in the foreground
python src/agentic_player/main.py
