# Button capture — listen on the HID++ long interface for 90 s, log everything with timestamps.
import time
import hid

VID = 0x046D

def hexs(b):
    return " ".join(f"{x:02x}" for x in b)

long_path = None
for d in hid.enumerate(VID, 0):
    if d['usage_page'] == 0xFF00 and d['usage'] == 2:
        long_path = d['path']

h = hid.device()
h.open_path(long_path)
h.set_nonblocking(False)
print("capture start - listening 90s", flush=True)
t0 = time.time()
while time.time() - t0 < 90:
    try:
        data = h.read(64, 500)
    except Exception as e:
        print(f"read error {e}", flush=True)
        break
    if data:
        print(f"{time.time()-t0:7.2f}s {hexs(bytes(data))}", flush=True)
h.close()
print("capture done", flush=True)
