<img width="1919" height="1117" alt="image" src="https://github.com/user-attachments/assets/4a4c6b4e-5f4e-4c05-9b00-172948dfd559" />

# Agentic Media Player

A local-AI-first media player and library manager built with Python, PySide6, and ZeroMQ. It integrates voice commands, conversational AI, and automated media fetching into a single unified desktop interface.

## Features
* **Local AI Agent**: Hot-swappable LLM integration (defaulting to Granite/Ollama via LiteLLM) to parse commands and answer queries.
* **Voice Control**: Push-to-Talk functionality using Whisper/Faster-Whisper for local Speech-to-Text with a live UI audio visualizer.
* **Agent Voice**: Text-to-Speech responses powered by Kokoro-82M (Fast) and Suno Bark (Heavy).
* **Automated Fetching**: Built-in `yt-dlp` worker for downloading, metadata tagging, and auto-categorizing audio and video files.
* **Native Playback**: VLC engine embedded directly into the PySide6 X11 window with a custom transport dock and progress scrubber.
* **Multi-Process Architecture**: ZeroMQ handles IPC between the UI, player, fetcher, and AI workers to guarantee a freeze-free GUI.

## Prerequisites
* Python 3.10+
* `libvlc` (VLC Media Player installed on the system)
* Ollama (running locally for LLM inference)

## ZMQ Socket Architecture
The application runs on a distributed background worker model over `localhost` TCP sockets:
* `5555`: Agent Router (LLM parsing)
* `5556`: Fetcher Worker (Downloads & DB Sync)
* `5557`: UI Chat Publisher
* `5559`: VLC Player Worker
* `5560`: Voice Worker (STT & Mic Capture)
* `5561`: Live UI Config/Hardware Updates
* `5562`: Fetcher Completion Status
* `5563`: Playback Progress & Scrubber Sync
* `5564`: Live Mic Volume Broadcast
