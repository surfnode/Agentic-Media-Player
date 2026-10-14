#!/bin/bash
# diag_ladder.sh - verbose download test; shows every error live
cd "$(dirname "$0")"
venv/bin/python - << 'PYEOF'
import os, glob, shutil, json, yt_dlp
s = json.load(open("settings.json"))
browser = (s.get("yt_cookies_from_browser") or "").lower()
ladder = [c.strip() for c in (s.get("yt_player_clients") or "tv,web_safari,mweb").split(",") if c.strip()]
print(f"cookies: {browser or 'NONE'} | ladder: {ladder} | yt-dlp {yt_dlp.version.__version__}\n")
BASE = "downloads/_diag"
shutil.rmtree(BASE, ignore_errors=True)
for c in ladder:
    d = os.path.join(BASE, c)
    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(d, "%(title)s.%(ext)s"),
        "quiet": False,
        "verbose": True,
        "extractor_args": {"youtube": [f"player_client={c}"]},
    }
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    print(f"\n{'='*50}")
    print(f"CLIENT: {c}")
    print(f"{'='*50}")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download(["ytsearch1:Kavinsky Nightcall"])
        files = glob.glob(os.path.join(d, "*"))
        if files:
            print(f"\n*** {c}: DOWNLOADED: {os.path.basename(files[0])} ***\n")
        else:
            print(f"\n*** {c}: no file ***\n")
    except Exception as e:
        print(f"\n*** {c}: FAILED: {str(e)[:200]} ***\n")
PYEOF
