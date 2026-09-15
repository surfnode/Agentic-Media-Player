import os
os.environ["SUNO_USE_SMALL_MODELS"] = "True"

import zmq
import sounddevice as sd
import torch
from transformers import AutoProcessor, BarkModel
import warnings

warnings.filterwarnings("ignore")

def start_tts_worker():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[*] Loading Suno Bark model on {device.upper()} (VRAM Optimized)...")
    
    processor = AutoProcessor.from_pretrained("suno/bark-small")
    model = BarkModel.from_pretrained("suno/bark-small").to(device)
    voice_preset = "v2/en_speaker_6" 

    context = zmq.Context()
    
    chat_socket = context.socket(zmq.SUB)
    chat_socket.connect("tcp://127.0.0.1:5557")
    chat_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    config_socket = context.socket(zmq.SUB)
    config_socket.connect("tcp://127.0.0.1:5561")
    config_socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    poller = zmq.Poller()
    poller.register(chat_socket, zmq.POLLIN)
    poller.register(config_socket, zmq.POLLIN)

    current_spk_id = None
    tts_enabled = True
    print("[*] TTS Worker ready.")

    while True:
        try:
            socks = dict(poller.poll(100))
            
            if config_socket in socks:
                msg = config_socket.recv_json()
                msg_type = msg.get("type")
                if msg_type == "hardware_update":
                    new_spk_id = msg["config"].get("spk_device_id")
                    if new_spk_id != current_spk_id:
                        print(f"[*] Routing audio to Speaker ID {new_spk_id}")
                        current_spk_id = new_spk_id
                        sd.default.device = (None, current_spk_id)
                elif msg_type == "inference_toggle":
                    tts_enabled = msg["config"].get("tts_enabled", True)
                    print(f"[*] TTS Voice Enabled State: {tts_enabled}")

            if chat_socket in socks:
                message = chat_socket.recv_json()
                if message.get("type") == "chat_reply":
                    text_to_speak = message.get("value", "")
                    if text_to_speak and tts_enabled:
                        print(f"[TTS Synthesizing]: {text_to_speak}")
                        inputs = processor(text_to_speak, voice_preset=voice_preset).to(device)
                        with torch.no_grad():
                            speech_output = model.generate(**inputs)
                        audio_data = speech_output[0].cpu().numpy()
                        sd.play(audio_data, samplerate=model.generation_config.sample_rate)
                        sd.wait()
                    elif not tts_enabled:
                        print("[TTS Muted]: Skipping audio playback.")
                        
        except Exception as e:
            print(f"[!] TTS Error: {e}")

if __name__ == "__main__":
    start_tts_worker()
