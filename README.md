# Agentic Media Player

Local-first media player with a voice-driven AI agent. Qt UI, VLC playback,
yt-dlp downloads, Ollama LLM routing, local STT/TTS (Qwen3-ASR + Kokoro).
Everything runs on this machine - no cloud calls except optional web search.

## Run / stop

    ./run.sh     # starts all workers + UI; close the window or Ctrl+C to stop all
    ./stop.sh    # kills any leftover processes (safe to run any time)

## Prerequisites

- Python venv at `./venv` (packages in `requirements.txt`)
- Ollama running with a model pulled (default: `granite4.2:8b-q8_0`)
- `ffmpeg` on PATH (yt-dlp audio extraction)
- VLC installed (python-vlc wraps libvlc)

## Message flows

- You (typed or spoken) -> Router (5555) -> spoken reply (5557) -> UI chat + TTS voice
- Router -> Fetcher (5556) -> download -> DB -> "done" (5562) -> UI library refresh
- Router / UI -> Player (5559) -> progress + track changes (5563) -> UI transport bar
- UI -> Voice (5560) PTT control; Voice -> mic level (5564) -> UI meter
- UI -> 5561 config PUB -> all workers (live hot-swap of model/voice/devices)

## Port map

| Port | Bound by | Type | Purpose |
|------|----------|------|---------|
| 5555 | Router | PULL | Chat/commands in (UI + voice worker) |
| 5556 | Fetcher | PULL | Download commands |
| 5557 | Router | PUB | chat_reply -> UI chat + TTS |
| 5559 | Player | PULL | Transport commands (play/seek/volume) |
| 5560 | Voice | PULL | PTT / always-on control from UI |
| 5561 | UI | PUB | Config bus (all workers subscribe) |
| 5562 | Fetcher | PUB | download_complete -> UI |
| 5563 | Player | PUB | progress / track_changed -> UI |
| 5564 | Voice | PUB | mic volume -> UI meter |

## Data on disk (all auto-created, all gitignored)

- `agentic_player.db` - track library
- `downloads/audio/`, `downloads/video/` - media + thumbnails
- `settings.json` - persisted settings; single source of truth is
  `DEFAULTS` in `src/agentic_player/core/settings.py`

## CLI shortcut

    python trigger_download.py "Artist - Title"   # defaults to video

## Downloads blocked by YouTube? ("Sign in to confirm you're not a bot")

YouTube bot-checks unauthenticated downloaders. Two fixes, configured in
`settings.json` (fetcher reads them at BOOT - restart the app after editing):

1. **Browser cookies** - log into youtube.com in your browser, then set:
       "yt_cookies_from_browser": "firefox"
   (also works: chrome, chromium, brave, edge)

2. **cookies.txt** - install a browser extension like "Get cookies.txt
   LOCALLY", export youtube.com cookies, save as `cookies.txt` in the project
   root, then set:
       "yt_cookies_file": "cookies.txt"

Also keep yt-dlp current - YouTube changes break old versions:
       ~/agentic-music-player/venv/bin/pip install -U yt-dlp

Failed downloads now appear in the chat panel; full details in
`logs/fetcher.log`.

## Downloader requirements (2026+)

YouTube requires yt-dlp to solve a JavaScript challenge. Two dependencies,
both already installed on this machine:

1. **yt-dlp with EJS scripts** - always install/upgrade with the extra:
       venv/bin/pip install -U "yt-dlp[default]"
   (plain `yt-dlp` is missing the challenge-solver scripts)

2. **Deno JS runtime** - https://deno.com (installed at ~/.deno/bin, and
   run.sh injects it into PATH automatically). The fetcher prints its
   status at every boot: look for "[*] JS runtime (deno): ..." in
   logs/fetcher.log.

If downloads fail again: first run `./diag_ladder.sh`, then check the boot
line for deno. The most common breakage is a yt-dlp update that outgrew
the installed yt-dlp-ejs - the fix is the pip command above.
