import os
os.environ["SUNO_USE_SMALL_MODELS"] = "True"
import logging
import transformers
transformers.logging.set_verbosity_error()

import zmq
import sounddevice as sd
import torch
from transformers import AutoProcessor, BarkModel
import warnings
from kokoro import KPipeline

warnings.filterwarnings("ignore")

def start_tts_worker():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[*] Loading TTS Models on {device.upper()}...")
    
    processor = AutoProcessor.from_pretrained("suno/bark-small")
    model_bark = BarkModel.from_pretrained("suno/bark-small").to(device)
    bark_voice = "v2/en_speaker_6" 
    
    pipeline_kokoro = KPipeline(lang_code='a') 
    kokoro_voice = "af_bella" 
    
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
    current_engine = "Bark (Heavy)"
    
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
                        current_spk_id = new_spk_id
                        sd.default.device = (None, current_spk_id)
                elif msg_type == "inference_toggle":
                    tts_enabled = msg["config"].get("tts_enabled", True)
                    engine = msg["config"].get("tts_engine")
                    if engine and engine != current_engine:
                        print(f"\n[*] Swapping TTS Engine to: {engine}")
                        current_engine = engine

            if chat_socket in socks:
                message = chat_socket.recv_json()
                if message.get("type") == "chat_reply":
                    text_to_speak = message.get("value", "")
                    if text_to_speak and tts_enabled:
                        print(f"[{current_engine} Synthesizing]: {text_to_speak}")
                        
                        if current_engine == "Kokoro-82M (Fast)":
                            generator = pipeline_kokoro(text_to_speak, voice=kokoro_voice, speed=1)
                            for i, (gs, ps, audio) in enumerate(generator):
                                sd.play(audio, samplerate=24000) 
                                sd.wait()
                        else:
                            inputs = processor(text_to_speak, voice_preset=bark_voice).to(device)
                            with torch.no_grad():
                                speech_output = model_bark.generate(**inputs)
                            audio_data = speech_output[0].cpu().numpy()
                            sd.play(audio_data, samplerate=model_bark.generation_config.sample_rate)
                            sd.wait()
                            
                    elif not tts_enabled:
                        print("[TTS Muted]: Skipping audio playback.")
                        
        except Exception as e:
            print(f"[!] TTS Error: {e}")

if __name__ == "__main__":
    start_tts_worker()
