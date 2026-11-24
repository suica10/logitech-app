# HID++ probe #2 — focused transport debug.
# Opens col01 (0x10 short) and col02 (0x11 long) of mi_02 simultaneously,
# logs ALL incoming reports on both with timestamps, sends pings both ways.
import time
from pywinusb import hid

VID = 0x046D

def hexs(b):
    return " ".join(f"{x:02x}" for x in b)

devices = hid.HidDeviceFilter(vendor_id=VID).get_devices()
by_col = {}
for d in devices:
    p = d.device_path.lower()
    if "mi_02&col01" in p:
        by_col["short"] = d
    elif "mi_02&col02" in p:
        by_col["long"] = d
    elif "mi_02&col03" in p:
        by_col["dj"] = d

print("collections:", list(by_col.keys()))
t0 = time.time()
def stamp():
    return f"{time.time()-t0:6.2f}s"

opened = {}
for name, d in by_col.items():
    def make_handler(n):
        def handler(data):
            print(f"{stamp()} [{n}] <- {hexs(bytes(data))}", flush=True)
        return handler
    try:
        d.open()
        d.set_raw_data_handler(make_handler(name))
        opened[name] = d
        print(f"opened {name}: {d.device_path}", flush=True)
    except Exception as e:
        print(f"open {name} failed: {e}", flush=True)

time.sleep(1.0)

def send_long(dev_idx, feature, function, swid, params):
    d = opened.get("long")
    if not d:
        return
    for r in d.find_output_reports():
        if r.report_id == 0x11:
            b = bytearray(19)
            b[0] = dev_idx; b[1] = feature; b[2] = (function << 4) | swid
            for j, p in enumerate(params):
                b[3 + j] = p
            raw = [0x11] + list(b)
            print(f"{stamp()} [long] -> {hexs(bytes(raw))}", flush=True)
            r.set_raw_data(raw)
            r.send()
            return

def send_short(dev_idx, feature, function, swid, params):
    d = opened.get("short")
    if not d:
        return
    for r in d.find_output_reports():
        if r.report_id == 0x10:
            b = bytearray(6)
            b[0] = dev_idx; b[1] = feature; b[2] = (function << 4) | swid
            for j, p in enumerate(params[:3]):
                b[3 + j] = p
            raw = [0x10] + list(b)
            print(f"{stamp()} [short] -> {hexs(bytes(raw))}", flush=True)
            r.set_raw_data(raw)
            r.send()
            return

# long pings: receiver + slot 1
for dev in (0xFF, 1):
    send_long(dev, 0x00, 0x01, 0x0A, [0x5A, 0xA5, 0x3C])
    time.sleep(2.0)
# short pings: receiver + slot 1
for dev in (0xFF, 1):
    send_short(dev, 0x00, 0x01, 0x0A, [0x5A, 0xA5, 0x3C])
    time.sleep(2.0)
# idle listen (DJ / notifications may flow)
print(f"{stamp()} idle listen 4s...", flush=True)
time.sleep(4.0)
for d in opened.values():
    try:
        d.close()
    except Exception:
        pass
print("probe2 done", flush=True)
