# Probe 7 - raw payload dumps: battery, DPI fns, CID reporting get/set variants.
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hidpp import HIDPPDevice  # noqa: E402


def hexs(b):
    return " ".join(f"{x:02x}" for x in b)


dev = HIDPPDevice(device_index=1)
try:
    bat_idx = dev.feature_index(0x1000)
    print(f"battery idx={bat_idx} raw fn0: {hexs(dev.request(bat_idx, 0))}", flush=True)

    dpi_idx = dev.feature_index(0x2201)
    print(f"dpi idx={dpi_idx} raw fn0 (count): {hexs(dev.request(dpi_idx, 0))}", flush=True)
    print(f"dpi raw fn1 (list, sensor0): {hexs(dev.request(dpi_idx, 1, bytes([0])))}", flush=True)
    print(f"dpi raw fn2 (get, sensor0): {hexs(dev.request(dpi_idx, 2, bytes([0])))}", flush=True)

    rc_idx = dev.feature_index(0x1B04)
    for cid in (0x0053, 0x0056, 0x00C3, 0x00C4):
        r = dev.request(rc_idx, 2, struct.pack(">H", cid))
        print(f"getCidReporting 0x{cid:04x} raw: {hexs(r)}", flush=True)

    # no-op set: same flags as current (0x01 for 0x53), dump raw reply
    try:
        r = dev.request(rc_idx, 3, struct.pack(">HB", 0x0053, 0x01))
        print(f"setCidReporting(0x53, 0x01) raw reply: {hexs(r)}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"setCidReporting(0x53, 0x01) raised: {e}", flush=True)
    r = dev.request(rc_idx, 2, struct.pack(">H", 0x0053))
    print(f"getCidReporting 0x53 after no-op set: {hexs(r)}", flush=True)

    # set with trailing zero byte
    try:
        r = dev.request(rc_idx, 3, struct.pack(">HB", 0x0053, 0x01) + b"\x00")
        print(f"setCidReporting+trailing0 raw reply: {hexs(r)}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"setCidReporting+trailing0 raised: {e}", flush=True)
    r = dev.request(rc_idx, 2, struct.pack(">H", 0x0053))
    print(f"getCidReporting 0x53 final: {hexs(r)}", flush=True)
finally:
    dev.close()
print("probe7 done", flush=True)
