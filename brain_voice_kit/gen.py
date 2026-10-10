"""Generate voice lines with Fish Audio TTS. Usage: gen.py OUT_DIR LINE_NUMS... (or 'all')"""
import os, sys, re, json, time, subprocess, requests
HERE = os.path.dirname(os.path.abspath(__file__))
# Key comes from FISH_API_KEY, or is added by the environment's network secret for api.fish.audio
KEY = os.environ.get("FISH_API_KEY")
# s2.1-pro-free costs $0; set FISH_MODEL=s2.1-pro to use the paid model
MODEL = os.environ.get("FISH_MODEL", "s2.1-pro-free")
out_dir = sys.argv[1]; os.makedirs(out_dir, exist_ok=True)
voices = json.load(open(os.path.join(HERE, "voices.json")))
lines = []
for raw in open(os.path.join(HERE, "lines.txt"), encoding="utf-8"):
    m = re.match(r"(\d+) ([A-Z ]+?): (.+)", raw.strip())
    lines.append((int(m[1]), m[2], m[3]))
want = None if sys.argv[2:] == ["all"] else {int(x) for x in sys.argv[2:]}

class Fatal(Exception): pass

def fname(n, spk): return f"{n:03d}_{spk.replace(' ', '_')}.mp3"

def tts(text, ref):
    r = requests.post("https://api.fish.audio/v1/tts",
        headers={**({"Authorization": f"Bearer {KEY}"} if KEY else {}), "Content-Type": "application/json", "model": MODEL},
        json={"text": text, "reference_id": ref, "format": "mp3", "mp3_bitrate": 192,
              "latency": "normal", "normalize": True}, timeout=180)
    if r.status_code in (401, 402, 403):
        raise Fatal(f"HTTP {r.status_code}: {r.text[:300]}")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    if len(r.content) < 1000:
        raise RuntimeError(f"suspiciously small response ({len(r.content)} bytes)")
    return r.content

def duration(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).strip())

todo = [l for l in lines if want is None or l[0] in want]
failed = []
for attempt in (1, 2):
    failed = []
    for n, spk, text in todo:
        path = os.path.join(out_dir, fname(n, spk))
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            continue
        if not voices.get(spk):
            failed.append((n, spk, text, "no voice chosen")); continue
        try:
            data = tts(text, voices[spk])
            with open(path, "wb") as f: f.write(data)
            print(f"ok   {fname(n, spk)}  {duration(path):.2f}s", flush=True)
        except Fatal as e:
            print(f"FATAL on line {n}: {e}"); sys.exit(2)
        except Exception as e:
            print(f"fail {fname(n, spk)} (attempt {attempt}): {e}", flush=True)
            failed.append((n, spk, text, str(e)))
    if not failed: break
    todo = [(n, s, t) for n, s, t, _ in failed if _ != "no voice chosen"]
    if not todo: break
    print(f"retrying {len(todo)} failed line(s)...")
    time.sleep(3)
print("STILL FAILED:" if failed else "ALL DONE")
for n, s, t, e in failed: print(f"  {n} {s}: {e}")
