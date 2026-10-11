import zmq
import instructor
from litellm import completion
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from agentic_player.agent.schemas import AgentResponse, Command

client = instructor.from_litellm(completion, mode=instructor.Mode.JSON)

def start_router():
    context = zmq.Context()
    
    in_socket = context.socket(zmq.PULL)
    in_socket.bind("tcp://127.0.0.1:5555")
    
    config_socket = context.socket(zmq.SUB)
    config_socket.connect("tcp://127.0.0.1:5561")
    config_socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    fetch_socket = context.socket(zmq.PUSH)
    fetch_socket.connect("tcp://127.0.0.1:5556")
    
    play_socket = context.socket(zmq.PUSH)
    play_socket.connect("tcp://127.0.0.1:5559")

    ui_pub_socket = context.socket(zmq.PUB)
    ui_pub_socket.bind("tcp://127.0.0.1:5557")

    poller = zmq.Poller()
    poller.register(in_socket, zmq.POLLIN)
    poller.register(config_socket, zmq.POLLIN)

    print("[*] Agent Router started. Listening on Port 5555...")

    llm_model = "ollama/granite4.2:8b-q8_0"
    api_base = "http://localhost:11434"

    conversation_history = [
        {
            "role": "system", 
            "content": (
                "You are a conversational AI media player assistant. "
                "CRITICAL RULE: If a user asks to download music, you MUST know if they want 'audio' or 'video'. "
                "If they didn't specify in their request, DO NOT issue a download command. Instead, use your spoken_reply to ask: 'Would you like the audio or the video format?'. "
                "Once they clarify, issue the download command with the correct media_type."
            )
        }
    ]

    while True:
        socks = dict(poller.poll(100))
        
        if config_socket in socks:
            msg = config_socket.recv_json()
            if msg.get("type") == "llm_update":
                new_model = msg["config"].get("llm_model", llm_model)
                new_api = msg["config"].get("llm_api", api_base)
                
                if new_model != llm_model or new_api != api_base:
                    llm_model = new_model
                    api_base = new_api
                    print(f"\n[*] Hot-Swapped LLM -> Model: {llm_model} | API: {api_base}")

        if in_socket in socks:
            message = in_socket.recv_json()
            user_text = message.get("text", "")
            print(f"\n[User Says]: {user_text}")

            conversation_history.append({"role": "user", "content": user_text})
            
            if len(conversation_history) > 13:
                conversation_history = [conversation_history[0]] + conversation_history[-12:]

            try:
                response = client.chat.completions.create(
                    model=llm_model, 
                    response_model=AgentResponse,
                    messages=conversation_history,
                    api_base=api_base
                )
            except Exception as e:
                print(f"[!] LLM failed: {e}. Falling back to regex.")
                cmds = []
                lower_text = user_text.lower()
                if any(k in lower_text for k in ["download", "get"]):
                    query = user_text.lower().replace("download", "").replace("get", "").strip()
                    mt = "audio" if "audio" in lower_text or "mp3" in lower_text else "video"
                    cmds.append(Command(action="download", query=query if query else user_text, media_type=mt))
                
                response = AgentResponse(
                    spoken_reply=f"Executing fallback command.",
                    commands=cmds
                )

            conversation_history.append({"role": "assistant", "content": response.spoken_reply})
            ui_pub_socket.send_json({"type": "chat_reply", "value": response.spoken_reply})

            for cmd in response.commands:
                if cmd.action == "download" and cmd.query:
                    media_type = getattr(cmd, "media_type", "video") or "video" 
                    print(f"[Agent -> Fetcher]: Downloading '{cmd.query}' as {media_type.upper()}")
                    fetch_socket.send_json({"action": "download", "query": cmd.query, "media_type": media_type})
                elif cmd.action in ["play", "pause", "stop"]:
                    print(f"[Agent -> Player]: Executing '{cmd.action}'")
                    play_socket.send_json({"action": cmd.action})

if __name__ == "__main__":
    start_router()
