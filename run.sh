#!/bin/bash
# run.sh - Boots the Agentic Media Player Stack

echo "[*] Cleaning up existing ports..."
fuser -k 5555/tcp 5556/tcp 5557/tcp 5559/tcp 5560/tcp 5561/tcp 2>/dev/null

echo "[*] Starting Agentic Media Player Services..."

export PYTHONPATH=$(pwd)/src:$PYTHONPATH

cleanup() {
    echo ""
    echo "[*] Caught exit signal. Shutting down all services gracefully..."
    kill $ROUTER_PID $FETCHER_PID $PLAYER_PID $TTS_PID $VOICE_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

python3 src/agentic_player/agent/router_worker.py &
ROUTER_PID=$!

python3 src/agentic_player/workers/fetcher_worker.py &
FETCHER_PID=$!

python3 src/agentic_player/workers/player_worker.py &
PLAYER_PID=$!

python3 src/agentic_player/workers/tts_worker.py &
TTS_PID=$!

python3 src/agentic_player/workers/voice_worker.py &
VOICE_PID=$!

sleep 2 

python3 src/agentic_player/main.py
