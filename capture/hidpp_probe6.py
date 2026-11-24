# HID++ probe #6 — full feature table via FeatureSet (index found = 1), device name, key feature indices.
import time, threading, queue
import hid

VID = 0x046D

def hexs(b):
    return " ".join(f"{x:02x}" for x in b)

long_path = short_path = None
for d in hid.enumerate(VID, 0):
    if d['usage_page'] == 0xFF00 and d['usage'] == 2:
        long_path = d['path']
    if d['usage_page'] == 0xFF00 and d['usage'] == 1:
        short_path = d['path']

h = hid.device()
h.open_path(long_path)
h.set_nonblocking(False)

q = queue.Queue()
stop = False
def reader():
    while not stop:
        try:
            data = h.read(64, 300)
        except Exception:
            return
        if data:
            q.put(bytes(data))
t = threading.Thread(target=reader, daemon=True)
t.start()

_swid = [0x08]
def request(dev, feature, function, params, timeout=2.0):
    swid = _swid[0]
    _swid[0] = 0x08 + ((_swid[0] - 0x08 + 1) % 8)
    b = bytearray(20)
    b[0] = 0x11; b[1] = dev; b[2] = feature; b[3] = (function << 4) | swid
    for j, p in enumerate(params):
        b[4 + j] = p
    # drain stale
    while not q.empty():
        q.get()
    h.write(bytes(b))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = q.get(timeout=max(0.1, deadline - time.time()))
        except queue.Empty:
            break
        if len(r) >= 4 and r[1] == dev and r[2] == feature and (r[3] & 0x0F) == swid:
            return r
        if len(r) >= 3 and r[2] == 0x8F:
            return r  # error
        print(f"  (other) {hexs(r)}", flush=True)
    return None

DEV = 1
print("=== FeatureSet getCount (feature idx 1, fn0) ===", flush=True)
r = request(DEV, 1, 0, [])
print("reply:", hexs(r) if r else None, flush=True)
count = r[4] if r and len(r) > 4 else 0
print(f"feature count = {count}", flush=True)

table = {}
for i in range(count):
    r = request(DEV, 1, 1, [i])
    if r and len(r) >= 7:
        fid = (r[4] << 8) | r[5]
        table[i] = (fid, r[6])
        print(f"  idx {i:2d}: feature 0x{fid:04x} version {r[6]}", flush=True)
    else:
        print(f"  idx {i:2d}: no reply {hexs(r) if r else None}", flush=True)

# Device name via feature 0x0005 -> find its index in table
name_idx = None
for i, (fid, v) in table.items():
    if fid == 0x0005:
        name_idx = i
if name_idx is not None:
    r = request(DEV, name_idx, 0, [])  # getDeviceNameCount
    n = r[4] if r else 0
    print(f"=== device name length {n} (feature idx {name_idx}) ===", flush=True)
    name = ""
    off = 0
    while off < n:
        r = request(DEV, name_idx, 1, [off])
        if not r:
            break
        chunk = bytes(r[4:20])
        take = chunk[: n - off]
        name += take.decode("utf-8", "replace")
        off += len(take)
        if len(take) == 0:
            break
    print(f"DEVICE NAME: {name}", flush=True)

stop = True
h.close()
print("probe6 done", flush=True)
