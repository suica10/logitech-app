# HID++ probe #5 — same requests via hidapi (interrupt WriteFile path).
import time
import hid

VID = 0x046D

def hexs(b):
    return " ".join(f"{x:02x}" for x in b)

print("=== hidapi enumerate VID_046D ===", flush=True)
paths = {}
for d in hid.enumerate(VID, 0):
    print(f"path={d['path']} product={d.get('product_string')} usage_page=0x{d['usage_page']:04x} usage=0x{d['usage']:02x} pid=0x{d['product_id']:04x}", flush=True)
    if d['usage_page'] == 0xFF00 and d['usage'] == 2:
        paths['long'] = d['path']
    if d['usage_page'] == 0xFF00 and d['usage'] == 1:
        paths['short'] = d['path']
print("chosen:", {k: v for k, v in paths.items()}, flush=True)

t0 = time.time()
def stamp():
    return f"{time.time()-t0:6.2f}s"

handles = {}
for name, path in paths.items():
    h = hid.device()
    h.open_path(path)
    h.set_nonblocking(False)
    handles[name] = h
    print(f"opened {name}", flush=True)

import threading
stop = False
def reader(name, h):
    while not stop:
        try:
            data = h.read(64, 300)
        except Exception as e:
            print(f"[{name}] read error {e}", flush=True)
            return
        if data:
            print(f"{stamp()} [{name}] <- {hexs(bytes(data))}", flush=True)

threads = []
for name, h in handles.items():
    t = threading.Thread(target=reader, args=(name, h), daemon=True)
    t.start()
    threads.append(t)

def write_long(dev_idx, feature, function, swid, params, tag):
    b = bytearray(20)
    b[0] = 0x11; b[1] = dev_idx; b[2] = feature; b[3] = (function << 4) | swid
    for j, p in enumerate(params):
        b[4 + j] = p
    print(f"{stamp()} [long] -> ({tag}) {hexs(bytes(b))}", flush=True)
    n = handles['long'].write(bytes(b))
    print(f"{stamp()} [long] write returned {n}", flush=True)

def write_short(raw, tag):
    print(f"{stamp()} [short] -> ({tag}) {hexs(bytes(raw))}", flush=True)
    n = handles['short'].write(bytes(raw))
    print(f"{stamp()} [short] write returned {n}", flush=True)

time.sleep(0.5)
write_long(1, 0x00, 0x01, 0x0A, [0x5A, 0xA5, 0x3C], "slot1 ping")
time.sleep(1.5)
write_long(1, 0x00, 0x00, 0x0A, [0x00, 0x01, 0x00], "slot1 getFeature 0x0001")
time.sleep(1.5)
write_short([0x10, 0xFF, 0x81, 0x02, 0x00, 0x00, 0x00], "receiver reg02 read")
time.sleep(1.5)
write_long(0xFF, 0x00, 0x01, 0x0A, [0x5A, 0xA5, 0x3C], "receiver ping")
time.sleep(2.0)

stop = True
for h in handles.values():
    try:
        h.close()
    except Exception:
        pass
print("probe5 done", flush=True)
