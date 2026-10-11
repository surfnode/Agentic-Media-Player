#!/bin/bash
# logs.sh            -> live-follow all logs (Ctrl+C to exit)
# logs.sh <pattern>  -> search all logs for a pattern (e.g. ./logs.sh error)

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

if [ ! -d logs ] || [ -z "$(ls -A logs 2>/dev/null)" ]; then
    echo "[!] No logs yet - start the app first: ./run.sh"
    exit 1
fi

if [ $# -gt 0 ]; then
    echo "[*] Searching all logs for: $*"
    echo "=========================================="
    grep -nE "$*" logs/*.log
else
    echo "[*] Following logs/*.log (Ctrl+C to stop)"
    echo "[*] Search mode instead: ./logs.sh 'pattern'"
    echo "=========================================="
    tail -n 15 -F logs/*.log
fi
