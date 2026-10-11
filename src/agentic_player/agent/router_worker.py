import zmq
import instructor
from litellm import completion
import sys
import os
import re
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

# Two instructor clients: JSON mode (native response_format - OpenAI,
# Ollama, most OpenAI-compatible servers) and TOOLS mode (function calling -
# the portable path for Anthropic, which has no response_format).
client_json = instructor.from_litellm(completion, mode=instructor.Mode.JSON)
client_tools = instructor.from_litellm(completion, mode=instructor.Mode.TOOLS)

PROVIDER_NAMES = {"ollama": "Ollama (local)", "openai": "OpenAI",
                  "anthropic": "Anthropic (Claude)", "custom": "Custom endpoint"}

# Filler words that must never reach yt-dlp as part of a search query.
# Deliberately excludes 'song' (song titles contain it, e.g. "Song 2").
_QUERY_FILLER = {"playlist", "playlists", "songs", "album", "albums"}


def sanitize_query(q):
    """Belt-and-suspenders cleanup on top of the LLM's own discipline:
    drop filler words the model was told to leave out anyway."""
    words = [w for w in (q or "").split()
             if w.lower().strip(".,!?\"'()") not in _QUERY_FILLER]
    out = " ".join(words).strip()
    return out or (q or "").strip()


def build_llm_call(s):
    """Turn the settings dict into litellm create() kwargs for the active provider."""
    provider = s.get("llm_provider", "ollama")
    if provider == "ollama":
        return {
            "model": f"ollama/{(s.get('llm_model_ollama') or 'granite4.2:8b-q8_0').strip()}",
            "api_base": (s.get("llm_api_ollama") or "http://localhost:11434").strip(),
        }
    if provider == "openai":
        return {
            "model": f"openai/{(s.get('llm_model_openai') or 'gpt-4o-mini').strip()}",
            "api_key": (s.get("llm_api_key_openai") or "").strip(),
        }
    if provider == "anthropic":
        return {
            "model": f"anthropic/{(s.get('llm_model_anthropic') or 'claude-sonnet-4').strip()}",
            "api_key": (s.get("llm_api_key_anthropic") or "").strip(),
        }
    # custom: any OpenAI-compatible endpoint (ALEPH Cloud, OpenRouter, Groq, LM Studio...)
    model = (s.get("llm_model_custom") or "").strip()
    if "/" not in model:
        model = f"openai/{model}"
    out = {"model": model}
    base = (s.get("llm_api_base_custom") or "").strip()
    if base:
        out["api_base"] = base.rstrip("/")
    key = (s.get("llm_api_key_custom") or "").strip()
    if key:
        out["api_key"] = key
    return out


def preflight_error(s):
    """Friendly, spoken errors for missing credentials - caught BEFORE
    burning a network request."""
    provider = s.get("llm_provider", "ollama")
    if provider in ("openai", "anthropic") and not (s.get(f"llm_api_key_{provider}") or "").strip():
        return (f"You've selected {PROVIDER_NAMES.get(provider)} but no API key is saved. "
                "Open Settings, the AI Models tab, and paste your key.")
    if provider == "custom":
        if not (s.get("llm_api_base_custom") or "").strip():
            return ("The custom endpoint has no base URL set. Open Settings, the AI Models tab, "
                    "and paste your provider's URL, for example https://your-provider/v1.")
        if not (s.get("llm_model_custom") or "").strip():
            return ("The custom endpoint has no model name set. Open Settings and enter the "
                    "model name your provider serves.")
    return None


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

    llm_cfg = load_settings()
    call = build_llm_call(llm_cfg)
    print(f"[*] Router LLM: {PROVIDER_NAMES.get(llm_cfg.get('llm_provider'), '?')} | {call.get('model')}"
          f" | web_search={llm_cfg.get('web_search_enabled', True)}")

    system_prompt = (
        "You are the conversational intelligence layer of a local media player.\n"
        "CRITICAL RULES:\n"
        "1. DOWNLOADS: Three clarifications, in this order of importance:\n"
        "   a) FORMAT: if the user did not state 'audio' or 'video', leave media_type null and ask.\n"
        "   b) COUNT: if the request implies multiple tracks (playlist, 'some songs', 'top 5', an "
        "album, an artist's music) but they gave NO number, leave count null and ask how many "
        "songs they want. A clearly single-song request gets no count question.\n"
        "   c) CLEAN QUERY: when issuing the download command, put ONLY the artist or song name "
        "in query - never words like 'playlist', 'songs', 'album', and never numbers (numbers "
        "belong in count).\n"
        "2. PLAYBACK: If the user asks to play music (e.g., 'play Bob Marley'), DO NOT ask which "
        "specific song. Issue the 'play' action WITH the artist's name in the query field immediately. "
        "The system will auto-select a matching local file.\n"
        "3. SHOWS: If they ask about concerts or live music, trigger 'search_shows'.\n"
        "4. TRANSPORT: 'next'/'prev' skip tracks, 'shuffle' toggles shuffle, 'pause'/'stop' control "
        "playback. These need no query.\n\n"
        "EXAMPLES:\n"
        "- User: 'download 10 songs from Residente as audio'\n"
        "  Action: download (query: 'Residente', media_type: 'audio', count: 10) | "
        "Reply: 'Downloading 10 Residente songs as audio.'\n"
        "- User: 'download the Juan Gabriel playlist'\n"
        "  Reply: 'Audio or video, and how many songs?' (both null until they answer)\n"
        "- User: 'download Bohemian Rhapsody as audio'\n"
        "  Action: download (query: 'Bohemian Rhapsody', media_type: 'audio', no count)\n"
        "- User: 'skip this song' -> Action: next | Reply: 'Skipping.'\n"
        "- User: 'turn on shuffle' -> Action: shuffle | Reply: 'Shuffle mode on.'\n"
    )

    conversation_history = [{"role": "system", "content": system_prompt}]

    while True:
        socks = dict(poller.poll(100))

        if config_socket in socks:
            msg = config_socket.recv_json()
            if msg.get("type") == "llm_update":
                cfg = msg.get("config", {})
                changed = {k: v for k, v in cfg.items()
                           if k in llm_cfg and llm_cfg[k] != v}
                if changed:
                    llm_cfg.update(changed)
                    if any(k.startswith("llm_") for k in changed):
                        new_call = build_llm_call(llm_cfg)
                        print(f"[*] Hot-Swapped LLM -> "
                              f"{PROVIDER_NAMES.get(llm_cfg.get('llm_provider'), '?')} | {new_call.get('model')}")

        if in_socket in socks:
            message = in_socket.recv_json()
            user_text = message.get("text", "")
            print(f"\n[User Says]: {user_text}")

            conversation_history.append({"role": "user", "content": user_text})

            if len(conversation_history) > 13:
                conversation_history = [conversation_history[0]] + conversation_history[-12:]

            friendly = preflight_error(llm_cfg)
            if friendly:
                print(f"[!] Config incomplete: {friendly}")
                response = AgentResponse(spoken_reply=friendly, commands=[])
            else:
                call = build_llm_call(llm_cfg)
                client = client_tools if llm_cfg.get("llm_provider") == "anthropic" else client_json
                try:
                    response = client.chat.completions.create(
                        model=call["model"],
                        response_model=AgentResponse,
                        messages=conversation_history,
                        **{k: v for k, v in call.items() if k != "model" and v},
                    )
                except Exception as e:
                    err_str = str(e)
                    print(f"[!] LLM failed: {err_str}")
                    if "not found" in err_str.lower():
                        model_clean = call["model"].split("/", 1)[-1]
                        spoken = f"I cannot connect to {model_clean}. Please open your terminal and run: ollama pull {model_clean}"
                    elif "api key" in err_str.lower() or "auth" in err_str.lower() or "401" in err_str:
                        spoken = "The provider rejected the API key. Check it in Settings, AI Models tab."
                    else:
                        spoken = "I encountered an error connecting to the AI model. Please check the logs."
                    response = AgentResponse(spoken_reply=spoken, commands=[])

            conversation_history.append({"role": "assistant", "content": response.spoken_reply})
            ui_pub_socket.send_json({"type": "chat_reply", "value": response.spoken_reply})

            for cmd in response.commands:
                if cmd.action == "search_shows" and cmd.query:
                    if not llm_cfg.get("web_search_enabled", True):
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
                    count = getattr(cmd, "count", None)
                    if media_type in ["audio", "video"]:
                        clean = sanitize_query(cmd.query)
                        count = max(1, min(50, int(count))) if count else None
                        payload = {"action": "download", "query": clean, "media_type": media_type}
                        if count and count > 1:
                            payload["count"] = count
                        print(f"[Agent -> Fetcher]: {payload}")
                        fetch_socket.send_json(payload)

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

                elif cmd.action in ["pause", "stop", "next", "prev", "shuffle"]:
                    player_action = "toggle_shuffle" if cmd.action == "shuffle" else cmd.action
                    print(f"[Agent -> Player]: {player_action}")
                    play_socket.send_json({"action": player_action})

if __name__ == "__main__":
    start_router()
