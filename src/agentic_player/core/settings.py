"""
Persistent application settings - single source of truth.

- The UI writes settings.json on every change (settings dialog + inference toggles).
- Workers read settings.json at startup, so a restarted worker always boots
  with current values. The 5561 PUB bus remains for live updates only.
- API keys live here in plaintext. settings.json is gitignored; keys are only
  ever sent to the provider they belong to.
"""
import json
import os
import tempfile
from pathlib import Path

# src/agentic_player/core/settings.py -> repo root is 3 parents up
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SETTINGS_PATH = PROJECT_ROOT / "settings.json"

DEFAULTS = {
    # Hardware
    "mic_device_id": None,
    "mic_name": "Auto-Detect (System Default)",
    "spk_device_id": None,
    "spk_name": "Auto-Detect (System Default)",
    # LLM provider: ollama | openai | anthropic | custom (OpenAI-compatible)
    "llm_provider": "ollama",
    "llm_model_ollama": "granite4.2:8b-q8_0",
    "llm_api_ollama": "http://localhost:11434",
    "llm_model_openai": "gpt-4o-mini",
    "llm_api_key_openai": "",
    "llm_model_anthropic": "claude-sonnet-4",
    "llm_api_key_anthropic": "",
    "llm_model_custom": "",
    "llm_api_base_custom": "",
    "llm_api_key_custom": "",
    # Web search
    "web_search_enabled": True,
    # Downloads: YouTube cookies (bot-check workaround). Pick ONE:
    #   yt_cookies_from_browser: "firefox" / "chrome" / "chromium" / "brave"...
    #     (you must be logged into youtube.com in that browser)
    #   yt_cookies_file: path to an exported cookies.txt ("cookies.txt" works
    #     if the file sits in the project root)
    # Both empty = no cookies (YouTube may block downloads with "Sign in to
    # confirm you're not a bot"). Fetcher reads these at BOOT - restart after
    # changing them.
    "yt_cookies_from_browser": "",
    "yt_cookies_file": "",
    # TTS (Kokoro)
    "kokoro_voice": "af_bella",
    "kokoro_speed": 1.0,
    # Playback
    "volume": 100,
    "muted": False,
    # Inference toggles (right panel)
    "stt_enabled": True,
    "tts_enabled": True,
    "stt_engine": "Qwen3-ASR (1.7B)",
    "tts_engine": "Kokoro-82M (Fast)",
}


def _migrate_legacy_llm(stored):
    """One-time: settings.json from before multi-provider had flat
    llm_model/llm_api keys. Map them onto the per-provider keys."""
    if not isinstance(stored, dict) or stored.get("llm_provider"):
        return stored
    legacy_model = str(stored.get("llm_model") or "")
    legacy_api = str(stored.get("llm_api") or "")
    if legacy_model.startswith("ollama/") and not stored.get("llm_model_ollama"):
        stored["llm_model_ollama"] = legacy_model.split("/", 1)[1]
    if legacy_api and not stored.get("llm_api_ollama"):
        stored["llm_api_ollama"] = legacy_api
    stored["llm_provider"] = "ollama"
    return stored


def load_settings():
    """Complete settings dict: file values merged over DEFAULTS.
    Unknown keys are dropped, missing keys fall back to defaults."""
    merged = dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            stored = _migrate_legacy_llm(stored)
            merged.update({k: v for k, v in stored.items() if k in DEFAULTS})
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError) as e:
        print(f"[!] Could not read settings.json ({e}); using defaults.")
    return merged


def save_settings(updates):
    """Merge `updates` into current settings and persist atomically.
    Partial dicts are fine - untouched keys keep their stored value."""
    merged = load_settings()
    merged.update({k: v for k, v in updates.items() if k in DEFAULTS})
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(SETTINGS_PATH.parent),
            prefix=".settings-", suffix=".tmp", delete=False,
        ) as tmp:
            json.dump(merged, tmp, indent=2)
            tmp_path = tmp.name
        os.replace(tmp_path, SETTINGS_PATH)
    except OSError as e:
        print(f"[!] Could not save settings.json: {e}")
