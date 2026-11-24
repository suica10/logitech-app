# Probe 8 - DPI set/get round trip (find the real byte layout) + CID set
# verified through GET read-back. Restores everything it touches.
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hidpp import HIDPPDevice  # noqa: E402


def hexs(b):
    return " ".join(f"{x:02x}" for x in b)


dev = HIDPPDevice(device_index=1)
try:
    dpi_idx = dev.feature_index(0x2201)
    rc_idx = dev.feature_index(0x1B04)

    r0 = dev.request(dpi_idx, 2, bytes([0]))
    print(f"dpi fn2 BEFORE: {hexs(r0)}", flush=True)

    # Solaar layout for setSensorDPI: [sensor, dpiX(2 BE), dpiY(2 BE)]
    try:
        rs = dev.request(dpi_idx, 3, bytes([0]) + struct.pack(">HH", 800, 800))
        print(f"dpi fn3 set(800,800) reply: {hexs(rs)}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"dpi fn3 set raised: {e}", flush=True)
    r1 = dev.request(dpi_idx, 2, bytes([0]))
    print(f"dpi fn2 AFTER SET 800: {hexs(r1)}", flush=True)

    # Restore: bytes [3:5] looked like 0x03e8=1000 in r0; set (1000,1000) if
    # the set worked, using the same positions the 800 landed in. We simply
    # set 1000/1000 with the same layout and compare the full raw dump.
    try:
        rs = dev.request(dpi_idx, 3, bytes([0]) + struct.pack(">HH", 1000, 1000))
        print(f"dpi fn3 restore(1000,1000) reply: {hexs(rs)}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"dpi fn3 restore raised: {e}", flush=True)
    r2 = dev.request(dpi_idx, 2, bytes([0]))
    print(f"dpi fn2 AFTER RESTORE: {hexs(r2)}", flush=True)
    print(f"dpi raw restored == original: {r2 == r0}", flush=True)

    # CID round trip proven through GET read-back (set reply is all zeros).
    def get_flags(cid):
        return dev.request(rc_idx, 2, struct.pack(">H", cid))[2]

    orig = get_flags(0x0053)
    print(f"cid 0x53 flags original: 0x{orig:02x}", flush=True)
    dev.request(rc_idx, 3, struct.pack(">HB", 0x0053, orig & ~0x01))
    print(f"cid 0x53 flags after divert OFF: 0x{get_flags(0x0053):02x}", flush=True)
    dev.request(rc_idx, 3, struct.pack(">HB", 0x0053, orig))
    back = get_flags(0x0053)
    print(f"cid 0x53 flags after restore: 0x{back:02x} (ok={back == orig})", flush=True)
finally:
    dev.close()
print("probe8 done", flush=True)
