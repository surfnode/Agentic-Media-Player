"""
Persistent application settings - single source of truth.

- The UI writes settings.json on every change (settings dialog + inference toggles).
- Workers read settings.json at startup, so a restarted worker always boots
  with current values. The 5561 PUB bus remains for live updates only.
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
    # LLM
    "llm_model": "ollama/granite4.2:8b-q8_0",
    "llm_api": "http://localhost:11434",
    "web_search_enabled": True,
    # TTS (Kokoro)
    "kokoro_voice": "af_bella",
    "kokoro_speed": 1.0,
    # Inference toggles (right panel)
    "stt_enabled": True,
    "tts_enabled": True,
    "stt_engine": "Qwen3-ASR (1.7B)",
    "tts_engine": "Kokoro-82M (Fast)",
}


def load_settings():
    """Complete settings dict: file values merged over DEFAULTS.
    Unknown keys are dropped, missing keys fall back to defaults."""
    merged = dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            stored = json.load(f)
        if isinstance(stored, dict):
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
