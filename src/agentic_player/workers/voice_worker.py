import zmq
import sounddevice as sd
import numpy as np
import whisper
from faster_whisper import WhisperModel
import scipy.io.wavfile as wav
import tempfile
import os
import torch

def start_voice_worker():
    context = zmq.Context()
    
    ui_socket = context.socket(zmq.PULL)
    ui_socket.bind("tcp://127.0.0.1:5560")
    
    config_socket = context.socket(zmq.SUB)
    config_socket.connect("tcp://127.0.0.1:5561")
    config_socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    router_socket = context.socket(zmq.PUSH)
    router_socket.connect("tcp://127.0.0.1:5555")

    poller = zmq.Poller()
    poller.register(ui_socket, zmq.POLLIN)
    poller.register(config_socket, zmq.POLLIN)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[*] Loading STT Models on {device.upper()}...")
    
    model_whisper = whisper.load_model("base")
    compute_type = "float16" if device == "cuda" else "int8"
    model_faster = WhisperModel("small", device=device, compute_type=compute_type)
    
    current_engine = "Whisper (Base)"
    print("[*] Voice Worker ready.")

    is_recording = False
    audio_data = []
    sample_rate = 16000 
    current_mic_id = None
    stream = None

    def audio_callback(indata, frames, time, status):
        if is_recording:
            audio_data.append(indata.copy())

    def start_audio_stream(device_id):
        nonlocal stream
        if stream is not None:
            stream.close()
        try:
            stream = sd.InputStream(samplerate=sample_rate, channels=1, 
                                    device=device_id, callback=audio_callback)
            stream.start()
        except Exception as e:
            print(f"[!] Failed to open microphone: {e}")

    start_audio_stream(current_mic_id)

    while True:
        socks = dict(poller.poll(100))

        if config_socket in socks:
            msg = config_socket.recv_json()
            if msg.get("type") == "hardware_update":
                new_mic_id = msg["config"].get("mic_device_id")
                if new_mic_id != current_mic_id:
                    current_mic_id = new_mic_id
                    start_audio_stream(current_mic_id)
            elif msg.get("type") == "inference_toggle":
                engine = msg["config"].get("stt_engine")
                if engine and engine != current_engine:
                    print(f"\n[*] Swapping STT Engine to: {engine}")
                    current_engine = engine

        if ui_socket in socks:
            message = ui_socket.recv_json()
            action = message.get("action")

            if action == "start":
                print("\n[🎤] Recording started...")
                audio_data.clear()
                is_recording = True

            elif action == "stop":
                is_recording = False
                print(f"[🎤] Transcribing with {current_engine}...")
                
                if len(audio_data) > 0:
                    recording = np.concatenate(audio_data, axis=0)
                    volume_level = np.max(np.abs(recording))
                    
                    if volume_level < 0.001:
                        print("[!] WARNING: Audio is silent.")
                    else:
                        temp_wav = os.path.join(tempfile.gettempdir(), "ptt_command.wav")
                        wav.write(temp_wav, sample_rate, recording)
                        
                        text = ""
                        if current_engine == "Faster-Whisper (Small)":
                            segments, _ = model_faster.transcribe(temp_wav, beam_size=5)
                            text = " ".join([s.text for s in segments]).strip()
                        else:
                            result = model_whisper.transcribe(temp_wav, fp16=False)
                            text = result["text"].strip()
                            
                        print(f"[{current_engine} heard]: {text}")
                        if text:
                            router_socket.send_json({"type": "chat", "text": text})

if __name__ == "__main__":
    start_voice_worker()
