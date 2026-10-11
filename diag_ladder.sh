#!/bin/bash
# diag_ladder.sh - real-download test across the client ladder; reorders
# settings.json so the winning client is tried first.
cd "$(dirname "$0")"
venv/bin/python - << 'PYEOF'
import os, glob, shutil, json, yt_dlp
s = json.load(open("settings.json"))
browser = (s.get("yt_cookies_from_browser") or "").lower()
ladder = [c.strip() for c in (s.get("yt_player_clients") or "tv,web_safari,mweb,android_vr,web_embedded").split(",") if c.strip()]
print(f"cookies: browser:{browser or 'NONE'} | ladder: {ladder} | yt-dlp {yt_dlp.version.__version__}\n")
BASE = "downloads/_diag"
shutil.rmtree(BASE, ignore_errors=True)
winner = None
for c in ladder:
    d = os.path.join(BASE, c)
    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(d, "%(title)s.%(ext)s"),
        "quiet": True, "no_warnings": True, "ignoreerrors": False,
        "extractor_args": {"youtube": [f"player_client={c}"]},
    }
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download(["ytsearch1:Kavinsky Nightcall"])
        files = glob.glob(os.path.join(d, "*"))
        if files:
            if not winner: winner = c
            print(f"  {c:12s} DOWNLOADED: {os.path.basename(files[0])}")
        else:
            print(f"  {c:12s} no file, no error")
    except Exception as e:
        print(f"  {c:12s} BLOCKED: {str(e)[:110]}")
print()
if winner:
    order = [winner] + [c for c in ladder if c != winner]
    s["yt_player_clients"] = ",".join(order)
    json.dump(s, open("settings.json", "w"), indent=2)
    print(f"WINNER: {winner} ladder saved: {s['yt_player_clients']}")
else:
    print("NO CLIENT GOT THROUGH")
PYEOF
