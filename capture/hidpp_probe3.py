# HID++ probe #3 — feature enumeration on the mouse (dev 1) via Root GetFeature (long).
# Logs every reply on short+long with the request that preceded it.
import time
from pywinusb import hid

VID = 0x046D

def hexs(b):
    return " ".join(f"{x:02x}" for x in b)

devices = hid.HidDeviceFilter(vendor_id=VID).get_devices()
short = long_ = None
for d in devices:
    p = d.device_path.lower()
    if "mi_02&col01" in p:
        short = d
    elif "mi_02&col02" in p:
        long_ = d

t0 = time.time()
def stamp():
    return f"{time.time()-t0:6.2f}s"

inbox = []
for name, d in (("short", short), ("long", long_)):
    if d is None:
        continue
    def make_handler(n):
        def handler(data):
            inbox.append((n, bytes(data)))
            print(f"{stamp()} [{n}] <- {hexs(bytes(data))}", flush=True)
        return handler
    d.open()
    d.set_raw_data_handler(make_handler(name))
    print(f"opened {name}", flush=True)

def send_long(dev_idx, feature, function, swid, params):
    for r in long_.find_output_reports():
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

time.sleep(0.5)
DEV = 1
candidates = [0x0001, 0x0003, 0x0005, 0x1000, 0x1B04, 0x2110, 0x2111, 0x2121, 0x2201, 0x2205, 0x2250, 0x6500, 0x8100]
swid = 0x08
for feat in candidates:
    inbox.clear()
    send_long(DEV, 0x00, 0x00, swid, [feat >> 8, feat & 0xFF, 0x00])
    time.sleep(1.2)
    swid = 0x08 + ((swid - 0x08 + 1) % 8)

# If FeatureSet (0x0001) answered with an index, enumerate the full table:
# (index is parsed manually from the log; this block tries index 1..4 blindly with getCount)
for idx in (1, 2, 3, 4, 5, 6):
    inbox.clear()
    send_long(DEV, idx, 0x00, 0x0B, [])  # FeatureSet getCount at candidate index
    time.sleep(0.8)

time.sleep(1.0)
for d in (short, long_):
    try:
        d.close()
    except Exception:
        pass
print("probe3 done", flush=True)
