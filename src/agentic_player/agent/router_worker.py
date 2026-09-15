import zmq
import instructor
from litellm import completion
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from agentic_player.agent.schemas import AgentResponse

# FIXED: Force Instructor into pure JSON mode for better local LLM compatibility
client = instructor.from_litellm(completion, mode=instructor.Mode.JSON)

def start_router():
    context = zmq.Context()
    
    in_socket = context.socket(zmq.PULL)
    in_socket.bind("tcp://127.0.0.1:5555")
    
    fetch_socket = context.socket(zmq.PUSH)
    fetch_socket.connect("tcp://127.0.0.1:5556")
    
    play_socket = context.socket(zmq.PUSH)
    play_socket.connect("tcp://127.0.0.1:5559")

    ui_pub_socket = context.socket(zmq.PUB)
    ui_pub_socket.bind("tcp://127.0.0.1:5557")

    print("[*] Agent Router started. Listening on Port 5555...")
    print("[*] Active LLM: granite4.2:8b-q8_0 (JSON Mode)")

    while True:
        message = in_socket.recv_json()
        user_text = message.get("text", "")
        print(f"\n[User Says]: {user_text}")

        try:
            response = client.chat.completions.create(
                model="ollama/granite4.2:8b-q8_0", 
                response_model=AgentResponse,
                messages=[
                    {"role": "system", "content": "You are an AI media player assistant. Parse the user's intent, reply concisely, and trigger the appropriate tools. Return valid JSON."},
                    {"role": "user", "content": user_text}
                ],
                api_base="http://localhost:11434"
            )
        except Exception as e:
            print(f"[!] LLM failed: {e}. Falling back to basic routing.")
            from agentic_player.agent.schemas import Command
            cmds = []
            if "download" in user_text.lower():
                query = user_text.lower().replace("download", "").strip()
                cmds.append(Command(action="download", query=query))
            elif "pause" in user_text.lower():
                cmds.append(Command(action="pause"))
            
            response = AgentResponse(
                spoken_reply="I'm running in offline fallback mode, but executing your command now.",
                commands=cmds
            )

        ui_pub_socket.send_json({"type": "chat_reply", "value": response.spoken_reply})

        # FIXED: Updated routing logic for the new single Command schema
        for cmd in response.commands:
            if cmd.action == "download" and cmd.query:
                print(f"[Agent -> Fetcher]: Downloading '{cmd.query}'")
                fetch_socket.send_json({"action": "download", "query": cmd.query})
            elif cmd.action in ["play", "pause", "stop"]:
                print(f"[Agent -> Player]: Executing '{cmd.action}'")
                play_socket.send_json({"action": cmd.action})

if __name__ == "__main__":
    start_router()
