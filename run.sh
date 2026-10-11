#!/bin/bash

# Move to the directory where this script lives
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Set PYTHONPATH so absolute imports work
export PYTHONPATH="$DIR/src:$PYTHONPATH"

# Unbuffered Python output -> log lines appear immediately, not in chunks
export PYTHONUNBUFFERED=1

# Explicitly activate the project's virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "[!] Virtual environment 'venv' not found in $DIR"
    exit 1
fi

# Timestamp every log line (no changes needed inside the workers)
stamp() {
  while IFS= read -r line; do
    printf '%s %s\n' "$(date '+%F %T')" "$line"
  done
}

mkdir -p logs

# bgutil POT server (YouTube PO tokens) - start once, skip if already up
if ! ss -ltn 2>/dev/null | grep -q ':4416'; then
  echo "[*] Starting bgutil POT server (YouTube PO tokens)..."
  (cd bgutil-ytdlp-pot-provider/node && npm start) >> logs/pot.log 2>&1 &
fi

echo "[*] Cleaning up existing ports..."
# All bound ports + the TTS worker (binds no port, so fuser can't see it)
fuser -k 5555/tcp 5556/tcp 5557/tcp 5559/tcp 5560/tcp 5561/tcp 5562/tcp 5563/tcp 5564/tcp 2>/dev/null
pkill -f "python.*agentic_player/workers/tts_worker\.py" 2>/dev/null

# Cleanup child processes when the UI closes
trap "kill 0" EXIT

echo "[*] Starting Agentic Media Player Services..."
echo "[*] Worker logs: logs/*.log   (view live: ./logs.sh)"

# Each worker logs to its own file; the main terminal stays clean for the UI
python src/agentic_player/workers/player_worker.py  2>&1 | stamp >> logs/player.log &
python src/agentic_player/workers/fetcher_worker.py 2>&1 | stamp >> logs/fetcher.log &
python src/agentic_player/workers/voice_worker.py   2>&1 | stamp >> logs/voice.log &
python src/agentic_player/agent/router_worker.py    2>&1 | stamp >> logs/router.log &
python src/agentic_player/workers/tts_worker.py     2>&1 | stamp >> logs/tts.log &

# UI runs in the foreground: visible here AND logged
python src/agentic_player/main.py 2>&1 | tee logs/ui.log
