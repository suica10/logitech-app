import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as m

cfg = m.load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
for exe in ("Lightroom.exe", "chrome.exe", None):
    for action in ("back", "forward", "mode_shift", "gesture_tap", "gesture_up"):
        print(f"{exe} / {action} -> {m.lookup(cfg, exe, action)!r}", flush=True)
print("check done", flush=True)
