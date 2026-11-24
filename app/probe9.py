# Probe 9 - FIRST restore DPI X to the original 2650 and confirm the raw dump
# matches the pre-probe original byte for byte. Then: test whether dpiY is
# settable at all, and try the 5-byte SetCidReporting form
# [cid(2), flags(1), mappedCid(2)].
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hidpp import HIDPPDevice  # noqa: E402


def hexs(b):
    return " ".join(f"{x:02x}" for x in b)


ORIGINAL_DPI_RAW = bytes([0x00, 0x0A, 0x5A, 0x03, 0xE8] + [0x00] * 11)

dev = HIDPPDevice(device_index=1)
try:
    dpi_idx = dev.feature_index(0x2201)
    rc_idx = dev.feature_index(0x1B04)

    def dpi_raw():
        return dev.request(dpi_idx, 2, bytes([0]))

    def dpi_set(x, y):
        return dev.request(dpi_idx, 3, bytes([0]) + struct.pack(">HH", x, y))

    # --- 1) restore DPI X=2650 (original), Y param 1200 as a settability test
    dpi_set(2650, 1200)
    r = dpi_raw()
    print(f"dpi after set(2650,1200): {hexs(r)}", flush=True)
    print(f"  -> dpiX={int.from_bytes(r[1:3], 'big')} dpiY={int.from_bytes(r[3:5], 'big')}", flush=True)

    # --- 2) restore exactly: X=2650, Y=1000
    dpi_set(2650, 1000)
    r = dpi_raw()
    print(f"dpi after set(2650,1000): {hexs(r)}", flush=True)
    print(f"  -> raw == ORIGINAL: {r == ORIGINAL_DPI_RAW}", flush=True)

    # --- 3) CID info dump (find capability flags for our CIDs)
    count = dev.request(rc_idx, 0)[0]
    print(f"control count: {count}", flush=True)
    for i in range(count):
        info = dev.request(rc_idx, 1, bytes([i]))
        cid = int.from_bytes(info[0:2], "big")
        if cid in (0x0053, 0x0056, 0x00C3, 0x00C4):
            print(f"  cidInfo idx{i} cid=0x{cid:04x} raw: {hexs(info)}", flush=True)

    def get_flags(cid):
        return dev.request(rc_idx, 2, struct.pack(">H", cid))[2]

    orig = get_flags(0x0053)
    print(f"cid 0x53 flags original: 0x{orig:02x}", flush=True)

    # --- 4) 5-byte set: [cid, flags, mappedCid=cid]
    dev.request(rc_idx, 3, struct.pack(">HBH", 0x0053, orig & ~0x01, 0x0053))
    mid = get_flags(0x0053)
    print(f"cid 0x53 flags after 5-byte set divert OFF: 0x{mid:02x}", flush=True)
    dev.request(rc_idx, 3, struct.pack(">HBH", 0x0053, orig, 0x0053))
    back = get_flags(0x0053)
    print(f"cid 0x53 flags after 5-byte restore: 0x{back:02x} (ok={back == orig})", flush=True)
finally:
    dev.close()
print("probe9 done", flush=True)
