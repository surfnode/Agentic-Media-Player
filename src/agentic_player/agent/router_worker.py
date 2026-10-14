import zmq
import instructor
from litellm import completion
import sys
import os
import re
import html
import sqlite3
import requests
from pathlib import Path

try:
    from ddgs import DDGS
    has_ddgs = True
except ImportError:
    has_ddgs = False

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from agentic_player.agent.schemas import AgentResponse, Command
from agentic_player.core.settings import load_settings

# Two instructor clients: JSON mode (OpenAI, Ollama, most OpenAI-compatible
# servers) and TOOLS mode (the portable path for Anthropic).
client_json = instructor.from_litellm(completion, mode=instructor.Mode.JSON)
client_tools = instructor.from_litellm(completion, mode=instructor.Mode.TOOLS)

PROVIDER_NAMES = {"ollama": "Ollama (local)", "openai": "OpenAI",
                  "anthropic": "Anthropic (Claude)", "custom": "Custom endpoint"}

# Filler words that must never reach yt-dlp as part of a search query.
_QUERY_FILLER = {"playlist", "playlists", "songs", "album", "albums"}


def sanitize_query(q):
    """Belt-and-suspenders cleanup on top of the LLM's own discipline."""
    words = [w for w in (q or "").split()
             if w.lower().strip(".,!?\"'()") not in _QUERY_FILLER]
    out = " ".join(words).strip()
    return out or (q or "").strip()


# ---------------- Lyrics (LRCLIB - free, no API key) ----------------

LRCLIB_HEADERS = {"User-Agent": "AgenticMediaPlayer/1.0 (github.com/surfnode/Agentic-Media-Player)"}

_LYRICS_NOISE = r"(?:official|video|audio|vivo|live|hd|lyrics?|remaster(?:ed)?|4k|sub\s?español)"


def clean_for_lyrics(s):
    """Strip YouTube-title noise so 'Song (Official Audio [HD])' matches."""
    if not s:
        return ""
    s = re.sub(r"\(" + _LYRICS_NOISE + r"[^)]*\)", "", s, flags=re.I)
    s = re.sub(r"\[" + _LYRICS_NOISE + r"[^\]]*\]", "", s, flags=re.I)
    return s.strip()


def fetch_lyrics(artist, title):
    """Lyrics from lrclib.net. Exact lookup first (needs artist), then fuzzy
    search. Returns plain lyrics text or None."""
    title_c = clean_for_lyrics(title)
    artist_c = clean_for_lyrics(artist) if artist else ""
    try:
        if artist_c and title_c:
            r = requests.get("https://lrclib.net/api/get",
                             params={"artist_name": artist_c, "track_name": title_c},
                             headers=LRCLIB_HEADERS, timeout=10)
            if r.ok:
                data = r.json()
                if data.get("plainLyrics"):
                    return data["plainLyrics"].strip()
        if title_c:
            r = requests.get("https://lrclib.net/api/search",
                             params={"q": f"{title_c} {artist_c}".strip()},
                             headers=LRCLIB_HEADERS, timeout=10)
            if r.ok:
                for item in r.json()[:5]:
                    if item.get("plainLyrics"):
                        return item["plainLyrics"].strip()
    except Exception as e:
        print(f"[!] Lyrics fetch error: {e}")
    return None


# ---------------- LLM provider plumbing (unchanged) ----------------

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
            "api_key": (s.get('llm_api_key_openai') or "").strip(),
        }
    if provider == "anthropic":
        return {
            "model": f"anthropic/{(s.get('llm_model_anthropic') or 'claude-sonnet-4').strip()}",
            "api_key": (s.get('llm_api_key_anthropic') or "").strip(),
        }
    # custom: any OpenAI-compatible endpoint
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

    # Live player events (port 5563) - we only care about track_changed,
    # which tells us what's currently playing.
    progress_sub = context.socket(zmq.SUB)
    progress_sub.connect("tcp://127.0.0.1:5563")
    progress_sub.setsockopt_string(zmq.SUBSCRIBE, "")

    fetch_socket = context.socket(zmq.PUSH)
    fetch_socket.connect("tcp://127.0.0.1:5556")

    play_socket = context.socket(zmq.PUSH)
    play_socket.connect("tcp://127.0.0.1:5559")

    ui_pub_socket = context.socket(zmq.PUB)
    ui_pub_socket.bind("tcp://127.0.0.1:5557")

    poller = zmq.Poller()
    poller.register(in_socket, zmq.POLLIN)
    poller.register(config_socket, zmq.POLLIN)
    poller.register(progress_sub, zmq.POLLIN)

    print("[*] Agent Router started. Listening on Port 5555...")

    llm_cfg = load_settings()
    call = build_llm_call(llm_cfg)
    print(f"[*] Router LLM: {PROVIDER_NAMES.get(llm_cfg.get('llm_provider'), '?')} | {call.get('model')}"
          f" | web_search={llm_cfg.get('web_search_enabled', True)}")

    # ---------- Personality ----------
    system_prompt = (
        "You are the soul of a local media player - a warm, music-obsessed friend who "
        "happens to control the stereo. You chat naturally, know a lot about artists, "
        "albums, songs and scenes, and you have opinions. You are NOT a command parser: "
        "many turns are pure conversation and should produce NO commands at all.\n\n"
        "WHAT YOU CAN DO (issue as commands only when clearly asked):\n"
        "- play / pause / stop / next / prev / shuffle - playback control. 'play' with a "
        "query plays from the local library.\n"
        "- download - fetch music from YouTube. If the user didn't say 'audio' or 'video', "
        "ask. If they want multiple tracks (playlist, 'some songs') but gave no number, ask "
        "how many. The query must be ONLY the artist or song name - never 'playlist'/'songs'/"
        "numbers (numbers go in count).\n"
        "- lyrics - fetch song lyrics. No query = the currently playing track. A query can "
        "be 'artist - song' or just a song title. When you use it, keep your spoken reply "
        "short ('Let me pull those up.').\n"
        "- search_shows - concert and tour listings for an artist.\n\n"
        "HOW TO TALK:\n"
        "- Warm, conversational, a little personality. Short paragraphs, not robot-speak.\n"
        "- Asked about an artist, song, genre or era? Just talk about it - no command. "
        "Share eras, collaborations, what makes them interesting. If you don't know "
        "something, say so honestly.\n"
        "- Confirm commands naturally ('On it - queuing Juan Gabriel.').\n"
        "- Spoken replies are read aloud by TTS - keep them reasonably short.\n\n"
        "EXAMPLES:\n"
        "- 'who is Dope Lemon?' -> conversation about Angus Stone's side project, no commands.\n"
        "- 'what do you think of Residente?' -> your honest take on his wordplay and Calle 13 "
        "roots, no commands.\n"
        "- 'play residente' -> play (query 'Residente') | 'On it.'\n"
        "- 'download 5 residente songs as audio' -> download (query 'Residente', media_type "
        "'audio', count 5).\n"        "- 'download Volver Volver by Vicente Fernandez' -> download (query 'Vicente Fernandez Volver Volver', media_type 'audio').\n"
        "- 'what are the lyrics to this song?' -> lyrics (no query) | 'Let me pull those up.'\n"
        "- 'lyrics to Bohemian Rhapsody' -> lyrics (query 'Bohemian Rhapsody') | 'Fetching those now.'\n"
        "- 'skip this' -> next | 'Skipping.'\n"
    )

    conversation_history = [{"role": "system", "content": system_prompt}]

    # ---------- Live state: what's playing ----------
    now_playing = {"title": None, "artist": None, "file_path": None}
    lyrics_cache = {}

    def update_now_playing(file_path):
        now_playing["file_path"] = file_path
        title = os.path.basename(file_path)
        artist = None
        if os.path.exists("agentic_player.db"):
            try:
                with sqlite3.connect("agentic_player.db") as conn:
                    row = conn.execute(
                        "SELECT title, artist FROM tracks WHERE file_path=?",
                        (file_path,)).fetchone()
                    if row:
                        title = row[0] or title
                        artist = row[1] or None
            except Exception:
                pass
        now_playing["title"] = title
        now_playing["artist"] = artist

    def build_messages():
        """Swap in a system prompt that knows what's currently playing, so
        'what's playing' / 'lyrics to this' / 'who sings this' just work."""
        content = system_prompt
        if now_playing.get("title"):
            line = f"\n\nCURRENT CONTEXT (live):\n- Now playing: \"{now_playing['title']}\""
            if now_playing.get("artist"):
                line += f" by {now_playing['artist']}"
            line += ("\n- 'this song' / 'the current track' refers to it; questions like "
                     "'what's playing' or 'lyrics to this' need no query.")
            content += line
        return [{"role": "system", "content": content}] + conversation_history[1:]

    def show_lyrics(title, artist):
        key = (artist or "", title or "")
        if key in lyrics_cache:
            lyrics = lyrics_cache[key]
        else:
            lyrics = fetch_lyrics(artist, title)
            lyrics_cache[key] = lyrics
        header = f"🎤 <b>{html.escape(title or '?')}</b>"
        if artist:
            header += f" — {html.escape(artist)}"
        if lyrics:
            body = html.escape(lyrics).replace("\n", "<br>")
            ui_pub_socket.send_json({"type": "chat_reply",
                                     "value": f"{header}<br><br>{body}",
                                     "speak": False})
            print(f"[*] Lyrics shown: {title}")
        else:
            ui_pub_socket.send_json({"type": "chat_reply",
                                     "value": f"{header}<br><i>Couldn't find lyrics for this one - "
                                              f"LRCLIB has no match.</i>",
                                     "speak": False})

    while True:
        socks = dict(poller.poll(100))

        # Player events - keep current-track state fresh
        if progress_sub in socks:
            try:
                message = progress_sub.recv_json(flags=zmq.NOBLOCK)
                if message.get("type") == "track_changed":
                    fp = message.get("file_path")
                    if fp:
                        update_now_playing(fp)
            except zmq.Again:
                pass

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
                        messages=build_messages(),
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

                elif cmd.action == "lyrics":
                    if cmd.query:
                        q = cmd.query.strip()
                        if " - " in q:
                            artist_q, title_q = [p.strip() for p in q.split(" - ", 1)]
                            show_lyrics(title_q, artist_q)
                        else:
                            show_lyrics(q, None)
                    elif now_playing.get("title"):
                        show_lyrics(now_playing["title"], now_playing["artist"])
                    else:
                        ui_pub_socket.send_json({"type": "chat_reply",
                                                 "value": "Nothing is playing right now - name a song and I'll find its lyrics.",
                                                 "speak": False})

                elif cmd.action == "play":
                    if cmd.query:
                        db_path = "agentic_player.db"
                        found_file = None
                        if os.path.exists(db_path):
                            try:
                                with sqlite3.connect(db_path) as conn:
                                    cursor = conn.cursor()
                                    cursor.execute("SELECT file_path FROM tracks WHERE title LIKE ? OR file_path LIKE ? LIMIT 1",
                                                   (f"%{cmd.query}%", f"%{cmd.query}%"))
                                    row = cursor.fetchone()
                                    if row:
                                        found_file = row[0]
                            except Exception as e:
                                pass
                        if found_file:
                            print(f"[Agent -> Player]: Found matching file: {os.path.basename(found_file)}")
                            play_socket.send_json({"action": "play", "file_path": found_file})
                        else:
                            ui_pub_socket.send_json({"type": "chat_reply",
                                                     "value": f"<i>I couldn't find '{cmd.query}' locally. Should I download it?</i>"})
                    else:
                        play_socket.send_json({"action": "play"})

                elif cmd.action in ["pause", "stop", "next", "prev", "shuffle"]:
                    player_action = "toggle_shuffle" if cmd.action == "shuffle" else cmd.action
                    print(f"[Agent -> Player]: {player_action}")
                    play_socket.send_json({"action": player_action})

if __name__ == "__main__":
    start_router()
