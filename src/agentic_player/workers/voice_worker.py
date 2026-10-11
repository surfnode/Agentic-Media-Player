import zmq
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import tempfile
import os
import torch
import collections
from qwen_asr import Qwen3ASRModel

def start_voice_worker():
    context = zmq.Context()
    ui_socket = context.socket(zmq.PULL)
    ui_socket.bind("tcp://127.0.0.1:5560")
    
    config_socket = context.socket(zmq.SUB)
    config_socket.connect("tcp://127.0.0.1:5561")
    config_socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    router_socket = context.socket(zmq.PUSH)
    router_socket.connect("tcp://127.0.0.1:5555")

    volume_pub = context.socket(zmq.PUB)
    volume_pub.bind("tcp://127.0.0.1:5564")

    poller = zmq.Poller()
    poller.register(ui_socket, zmq.POLLIN)
    poller.register(config_socket, zmq.POLLIN)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[*] Loading Qwen3-ASR on {device.upper()}...")
    
    try:
        asr_model = Qwen3ASRModel.from_pretrained("Qwen/Qwen3-ASR-1.7B", device_map=device)
        print("[*] Qwen3-ASR Voice Worker ready.")
    except Exception as e:
        print(f"[!] Failed to load Qwen3-ASR: {e}. Audio processing is paused.")
        asr_model = None

    sample_rate = 16000 
    current_mic_id = None
    stream = None
    current_volume = 0.0
    
    capture_audio = False
    is_always_on = False
    stt_enabled = True
    audio_data = []
    ring_buffer = collections.deque(maxlen=15) 
    vad_silence_counter = 0
    VAD_THRESHOLD = 0.03

    def audio_callback(indata, frames, time, status):
        nonlocal current_volume
        current_volume = float(np.max(np.abs(indata)))
        
        if capture_audio:
            audio_data.append(indata.copy())
        elif is_always_on:
            ring_buffer.append(indata.copy())

    def start_audio_stream(device_id):
        nonlocal stream
        if stream is not None:
            stream.close()
        try:
            stream = sd.InputStream(samplerate=sample_rate, channels=1, 
                                    device=device_id, callback=audio_callback)
            stream.start()
            print(f"[*] Mic initialized: {device_id if device_id is not None else 'System Default'}")
        except Exception as e:
            print(f"[!] Failed to open microphone: {e}")

    def process_captured_audio():
        nonlocal audio_data
        if len(audio_data) == 0: return
        
        if not stt_enabled or not asr_model:
            audio_data.clear()
            return

        print(f"[🎤] Transcribing with Qwen3-ASR...")
        recording = np.concatenate(audio_data, axis=0)
        volume_level = np.max(np.abs(recording))
        
        if volume_level < 0.01:
            print("[!] Audio too quiet. Dropped.")
        else:
            temp_wav = os.path.join(tempfile.gettempdir(), "qwen_command.wav")
            wav.write(temp_wav, sample_rate, recording)
            
            try:
                results = asr_model.transcribe([temp_wav])
                text = results[0].get("text", "").strip() if results else ""
            except Exception as e:
                print(f"[!] Qwen-ASR Transcription error: {e}")
                text = ""
            
            if text and len(text) > 2:
                print(f"[Qwen-ASR heard]: {text}")
                router_socket.send_json({"type": "chat", "text": text})
            else:
                print(f"[!] Ignored empty or silent audio snippet.")
                
        audio_data.clear()

    start_audio_stream(current_mic_id)

    while True:
        socks = dict(poller.poll(50))

        if stream and stream.active:
            volume_pub.send_json({"type": "mic_volume", "value": current_volume})
            
            if is_always_on and stt_enabled:
                if current_volume > VAD_THRESHOLD:
                    if not capture_audio:
                        print("\n[🎤] Auto-Voice Detected! Listening...")
                        capture_audio = True
                        audio_data.clear()
                        audio_data.extend(ring_buffer)
                    vad_silence_counter = 0
                else:
                    if capture_audio:
                        vad_silence_counter += 1
                        if vad_silence_counter > 30: 
                            capture_audio = False
                            process_captured_audio()

        if config_socket in socks:
            msg = config_socket.recv_json()
            if msg.get("type") == "hardware_update":
                new_mic_id = msg["config"].get("mic_device_id")
                if new_mic_id != current_mic_id:
                    current_mic_id = new_mic_id
                    start_audio_stream(current_mic_id)
            elif msg.get("type") == "inference_toggle":
                stt_enabled = msg["config"].get("stt_enabled", True)
                if not stt_enabled:
                    capture_audio = False
                    is_always_on = False

        if ui_socket in socks:
            message = ui_socket.recv_json()
            action = message.get("action")

            if action == "toggle_always_on":
                is_always_on = message.get("value", False)
                if is_always_on:
                    print("[*] Always-On Voice Activation ENABLED")
                    ring_buffer.clear()
                else:
                    print("[*] Always-On Voice Activation DISABLED")
                    capture_audio = False

            elif action == "start" and not is_always_on and stt_enabled:
                print("\n[🎤] Manual PTT Recording started...")
                audio_data.clear()
                capture_audio = True

            elif action == "stop" and not is_always_on and stt_enabled:
                capture_audio = False
                process_captured_audio()

if __name__ == "__main__":
    start_voice_worker()
