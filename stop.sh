#!/bin/bash
# stop.sh - kill every Agentic Media Player process, including ones started
# outside run.sh. Safe to run at any time, even if nothing is running.

echo "[*] Stopping Agentic Media Player..."

# 1) Anything holding our ports (UI, router, fetcher, player, voice)
fuser -k 5555/tcp 5556/tcp 5557/tcp 5559/tcp 5560/tcp 5561/tcp 5562/tcp 5563/tcp 5564/tcp 2>/dev/null

# 2) TTS binds no port, and fuser can miss others - catch-all by command line.
#    Patterns require "python ... <script>" so editors (vim/nano) never match.
pkill -f "python.*agentic_player/workers/tts_worker\.py" 2>/dev/null
pkill -f "python.*agentic_player/workers/player_worker\.py" 2>/dev/null
pkill -f "python.*agentic_player/workers/fetcher_worker\.py" 2>/dev/null
pkill -f "python.*agentic_player/workers/voice_worker\.py" 2>/dev/null
pkill -f "python.*agentic_player/agent/router_worker\.py" 2>/dev/null
pkill -f "python.*agentic_player/main\.py" 2>/dev/null

echo "[*] All services stopped."
