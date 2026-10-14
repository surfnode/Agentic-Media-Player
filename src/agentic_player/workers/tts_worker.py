import zmq
import sounddevice as sd
import torch
import re
import sys
from pathlib import Path
from kokoro import KPipeline

sys.path.append(str(Path(__file__).resolve().parents[2]))
from agentic_player.core.settings import load_settings

def start_tts_worker():
    context = zmq.Context()

    ui_socket = context.socket(zmq.SUB)
    ui_socket.connect("tcp://127.0.0.1:5557")
    ui_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    config_socket = context.socket(zmq.SUB)
    config_socket.connect("tcp://127.0.0.1:5561")
    config_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    poller = zmq.Poller()
    poller.register(ui_socket, zmq.POLLIN)
    poller.register(config_socket, zmq.POLLIN)

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"[*] Loading Kokoro TTS on {device.upper()}...")

    s = load_settings()
    current_voice = s.get("kokoro_voice", "af_bella")
    current_speed = float(s.get("kokoro_speed", 1.0))
    tts_enabled = s.get("tts_enabled", True)
    spk_device_id = s.get("spk_device_id", None)

    current_lang = 'b' if current_voice.startswith('b') else 'a'
    pipeline = KPipeline(lang_code=current_lang, device=device)
    sample_rate = 24000

    print(f"[*] TTS Worker ready. voice={current_voice} speed={current_speed:.2f} tts_enabled={tts_enabled} spk={spk_device_id}")

    while True:
        socks = dict(poller.poll(100))

        if config_socket in socks:
            msg = config_socket.recv_json()
            if msg.get("type") in ["llm_update", "hardware_update"]:
                config = msg.get("config", {})
                if "kokoro_voice" in config:
                    new_voice = config["kokoro_voice"]
                    if new_voice != current_voice:
                        current_voice = new_voice
                        new_lang = 'b' if current_voice.startswith('b') else 'a'
                        if new_lang != current_lang:
                            current_lang = new_lang
                            pipeline = KPipeline(lang_code=current_lang, device=device)
                        print(f"[*] Kokoro Voice swapped to: {current_voice}")
                if "kokoro_speed" in config:
                    current_speed = float(config["kokoro_speed"])
                if "spk_device_id" in config:
                    spk_device_id = config["spk_device_id"]
            elif msg.get("type") == "inference_toggle":
                tts_enabled = msg["config"].get("tts_enabled", True)

        if ui_socket in socks:
            message = ui_socket.recv_json()
            if message.get("type") == "chat_reply":
                # speak flag: status messages (download confirmations, etc.)
                # display in chat but are NOT narrated. Default: speak.
                if not message.get("speak", True):
                    continue
                if not tts_enabled:
                    continue
                text = message.get("value", "")
                clean_text = re.sub(r'<[^>]+>', '', text)
                if clean_text:
                    print(f"[Kokoro Synthesizing]: {clean_text[:50]}...")
                    try:
                        generator = pipeline(clean_text, voice=current_voice, speed=current_speed, split_pattern=r'\n+')
                        for _, _, audio in generator:
                            sd.play(audio, sample_rate, device=spk_device_id)
                            sd.wait()
                    except Exception as e:
                        print(f"[!] TTS Error: {e}")

if __name__ == "__main__":
    start_tts_worker()
