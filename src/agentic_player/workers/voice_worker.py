import zmq
import sounddevice as sd
import numpy as np
import whisper
import scipy.io.wavfile as wav
import tempfile
import os

def start_voice_worker():
    context = zmq.Context()
    
    # Port 5560: PTT Commands
    ui_socket = context.socket(zmq.PULL)
    ui_socket.bind("tcp://127.0.0.1:5560")
    
    # Port 5561: Hardware Settings Broadcasts
    config_socket = context.socket(zmq.SUB)
    config_socket.connect("tcp://127.0.0.1:5561")
    config_socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    # Port 5555: Route text to AI
    router_socket = context.socket(zmq.PUSH)
    router_socket.connect("tcp://127.0.0.1:5555")

    # The Poller allows us to listen to UI and Config simultaneously
    poller = zmq.Poller()
    poller.register(ui_socket, zmq.POLLIN)
    poller.register(config_socket, zmq.POLLIN)

    print("[*] Loading Whisper model (multilingual base)...")
    model = whisper.load_model("base")
    print("[*] Voice Worker started. Listening for commands and config updates...")

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
            stream.close()  # Close the old hardware stream
        try:
            stream = sd.InputStream(samplerate=sample_rate, channels=1, 
                                    device=device_id, callback=audio_callback)
            stream.start()
            dev_name = device_id if device_id is not None else "System Default"
            print(f"[*] Microphone stream active on Device ID: {dev_name}")
        except Exception as e:
            print(f"[!] Failed to open microphone: {e}")

    # Start the initial stream with the OS default
    start_audio_stream(current_mic_id)

    while True:
        socks = dict(poller.poll())

        # --- 1. HANDLE HARDWARE UPDATES ---
        if config_socket in socks:
            msg = config_socket.recv_json()
            if msg.get("type") == "hardware_update":
                new_mic_id = msg["config"].get("mic_device_id")
                if new_mic_id != current_mic_id:
                    print(f"\n[*] Hardware Update: Swapping Microphone to ID {new_mic_id}")
                    current_mic_id = new_mic_id
                    start_audio_stream(current_mic_id)

        # --- 2. HANDLE PUSH-TO-TALK ---
        if ui_socket in socks:
            message = ui_socket.recv_json()
            action = message.get("action")

            if action == "start":
                print("\n[🎤] Recording started...")
                audio_data.clear()
                is_recording = True

            elif action == "stop":
                is_recording = False
                print("[🎤] Recording stopped. Transcribing...")
                
                if len(audio_data) > 0:
                    recording = np.concatenate(audio_data, axis=0)
                    volume_level = np.max(np.abs(recording))
                    print(f"[*] Max volume level: {volume_level:.4f}")
                    
                    if volume_level < 0.001:
                        print("[!] WARNING: Audio is silent. Try changing your mic in the UI Settings.")
                    else:
                        temp_wav = os.path.join(tempfile.gettempdir(), "ptt_command.wav")
                        wav.write(temp_wav, sample_rate, recording)
                        
                        result = model.transcribe(temp_wav, fp16=False)
                        text = result["text"].strip()
                        
                        print(f"[Whisper heard]: {text}")
                        if text:
                            router_socket.send_json({"type": "chat", "text": text})

if __name__ == "__main__":
    start_voice_worker()
