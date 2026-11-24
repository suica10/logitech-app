# HID++ probe #4 — protocol matrix.
# A: HID++1.0 register reads on the receiver (short interface)
# B: long GetFeature(0x0001) to slots 1..3
# C: long GetFeature to receiver 0xFF (0x0002)
# Everything logged with timestamps.
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

for name, d in (("short", short), ("long", long_)):
    if d is None:
        continue
    def make_handler(n):
        def handler(data):
            print(f"{stamp()} [{n}] <- {hexs(bytes(data))}", flush=True)
        return handler
    d.open()
    d.set_raw_data_handler(make_handler(name))
    print(f"opened {name}", flush=True)

def send_long(dev_idx, feature, function, swid, params, tag):
    for r in long_.find_output_reports():
        if r.report_id == 0x11:
            b = bytearray(19)
            b[0] = dev_idx; b[1] = feature; b[2] = (function << 4) | swid
            for j, p in enumerate(params):
                b[3 + j] = p
            raw = [0x11] + list(b)
            print(f"{stamp()} [long] -> ({tag}) {hexs(bytes(raw))}", flush=True)
            r.set_raw_data(raw)
            r.send()
            return

def send_short_raw(raw, tag):
    for r in short.find_output_reports():
        if r.report_id == 0x10:
            print(f"{stamp()} [short] -> ({tag}) {hexs(bytes(raw))}", flush=True)
            r.set_raw_data(list(raw))
            r.send()
            return

time.sleep(0.5)
# A: 1.0 register reads on receiver: [10 FF 81 reg 00 00 00] read register
send_short_raw([0x10, 0xFF, 0x81, 0x02, 0x00, 0x00, 0x00], "reg02 connection")
time.sleep(1.2)
send_short_raw([0x10, 0xFF, 0x81, 0x01, 0x00, 0x00, 0x00], "reg01 receiver info")
time.sleep(1.2)
# B: slots 1..3 GetFeature(0x0001 FeatureSet)
for dev in (1, 2, 3):
    send_long(dev, 0x00, 0x00, 0x0A, [0x00, 0x01, 0x00], f"slot{dev} getFeature 0x0001")
    time.sleep(1.2)
# C: receiver long GetFeature(0x0002)
send_long(0xFF, 0x00, 0x00, 0x0A, [0x00, 0x02, 0x00], "receiver getFeature 0x0002")
time.sleep(1.2)
# D: dev1 ping again but swid 0x01
send_long(1, 0x00, 0x01, 0x01, [0x5A, 0xA5, 0x3C], "slot1 ping swid1")
time.sleep(1.5)

for d in (short, long_):
    try:
        d.close()
    except Exception:
        pass
print("probe4 done", flush=True)
