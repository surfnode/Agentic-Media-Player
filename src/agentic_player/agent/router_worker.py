import zmq
import instructor
from litellm import completion
import sys
import os
import sqlite3
from pathlib import Path

try:
    from ddgs import DDGS
    has_ddgs = True
except ImportError:
    has_ddgs = False

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from agentic_player.agent.schemas import AgentResponse, Command
from agentic_player.core.settings import load_settings

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

    # Boot config from settings.json (live updates still arrive on 5561)
    s = load_settings()
    llm_model = s.get("llm_model", "ollama/granite4.2:8b-q8_0")
    api_base = s.get("llm_api", "http://localhost:11434")
    web_search_enabled = s.get("web_search_enabled", True)
    print(f"[*] Router config: model={llm_model} | api={api_base} | web_search={web_search_enabled}")

    system_prompt = (
        "You are the conversational intelligence layer of a local media player.\n"
        "CRITICAL RULES:\n"
        "1. DOWNLOADS: If the user asks to download a song, verify if they stated 'audio' or 'video'. "
        "If they didn't, leave media_type null and ask them.\n"
        "2. PLAYBACK: If the user asks to play music (e.g., 'play Bob Marley', 'play a dope lemon song'), "
        "DO NOT ask them which specific song they want. Issue the 'play' action WITH the artist's name in the query field immediately. The system will auto-select a matching local file.\n"
        "3. SHOWS: If they ask about concerts or live music, trigger 'search_shows'.\n\n"
        "EXAMPLES:\n"
        "- User: 'Play a Dope Lemon song'\n"
        "  Thought: Wants to play an artist.\n"
        "  Action: play (query: 'Dope Lemon') | Reply: 'Playing Dope Lemon from your library.'\n"
    )

    conversation_history = [{"role": "system", "content": system_prompt}]

    while True:
        socks = dict(poller.poll(100))
        
        if config_socket in socks:
            msg = config_socket.recv_json()
            if msg.get("type") == "llm_update":
                new_model = msg["config"].get("llm_model", llm_model)
                new_api = msg["config"].get("llm_api", api_base)
                web_search_enabled = msg["config"].get("web_search_enabled", True)
                
                if new_model != llm_model or new_api != api_base:
                    llm_model = new_model
                    api_base = new_api
                    print(f"\n[*] Hot-Swapped LLM -> Model: {llm_model}")

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
                err_str = str(e)
                print(f"[!] LLM failed: {err_str}")
                cmds = []
                
                if "not found" in err_str.lower():
                    model_clean = llm_model.replace("ollama/", "")
                    spoken = f"I cannot connect to {model_clean}. Please open your terminal and run: ollama pull {model_clean}"
                else:
                    spoken = "I encountered an error connecting to the AI model. Please check the logs."
                    
                response = AgentResponse(spoken_reply=spoken, commands=cmds)

            conversation_history.append({"role": "assistant", "content": response.spoken_reply})
            ui_pub_socket.send_json({"type": "chat_reply", "value": response.spoken_reply})

            for cmd in response.commands:
                if cmd.action == "search_shows" and cmd.query:
                    if not web_search_enabled:
                        ui_pub_socket.send_json({"type": "chat_reply", "value": "<i>Web search disabled in settings.</i>"})
                    elif not has_ddgs:
                        ui_pub_socket.send_json({"type": "chat_reply", "value": "<i>The ddgs package is missing.</i>"})
                    else:
                        ui_pub_socket.send_json({"type": "chat_reply", "value": f"🔍 <i>Searching for: {cmd.query}...</i>"})
                        try:
                            with DDGS() as ddgs:
                                results = list(ddgs.text(f"{cmd.query} live music concert tour tickets", max_results=3))
                            if results:
                                reply = f"<b>Found these events for {cmd.query}:</b><br><br>"
                                for r in results:
                                    reply += f"• <a href='{r['href']}' style='color:#89b4fa;'>{r['title']}</a><br><br>"
                                ui_pub_socket.send_json({"type": "chat_reply", "value": reply})
                            else:
                                ui_pub_socket.send_json({"type": "chat_reply", "value": f"No recent concert listings for {cmd.query}."})
                        except Exception as e:
                            ui_pub_socket.send_json({"type": "chat_reply", "value": f"Search failed: {e}"})
                            
                elif cmd.action == "download" and cmd.query:
                    media_type = getattr(cmd, "media_type", None)
                    if media_type in ["audio", "video"]:
                        print(f"[Agent -> Fetcher]: Downloading '{cmd.query}' as {media_type.upper()}")
                        fetch_socket.send_json({"action": "download", "query": cmd.query, "media_type": media_type})
                        
                elif cmd.action == "play":
                    if cmd.query:
                        db_path = "agentic_player.db"
                        found_file = None
                        if os.path.exists(db_path):
                            try:
                                with sqlite3.connect(db_path) as conn:
                                    cursor = conn.cursor()
                                    cursor.execute("SELECT file_path FROM tracks WHERE title LIKE ? OR file_path LIKE ? LIMIT 1", (f"%{cmd.query}%", f"%{cmd.query}%"))
                                    row = cursor.fetchone()
                                    if row:
                                        found_file = row[0]
                            except Exception as e:
                                pass
                        
                        if found_file:
                            print(f"[Agent -> Player]: Found matching file: {os.path.basename(found_file)}")
                            play_socket.send_json({"action": "play", "file_path": found_file})
                        else:
                            ui_pub_socket.send_json({"type": "chat_reply", "value": f"<i>I couldn't find '{cmd.query}' locally. Should I download it?</i>"})
                    else:
                        play_socket.send_json({"action": "play"})

                elif cmd.action in ["pause", "stop"]:
                    play_socket.send_json({"action": cmd.action})

if __name__ == "__main__":
    start_router()
