# Probe 10 - SetCidReporting semantics for CID 0x53.
# After each set variant, poll GET rapidly (20 x 100ms) to catch transient
# states (in case Options+ re-asserts). Always ends restored to 0x01.
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hidpp import HIDPPDevice  # noqa: E402

dev = HIDPPDevice(device_index=1)
try:
    rc_idx = dev.feature_index(0x1B04)

    def get_flags(cid=0x0053):
        return dev.request(rc_idx, 2, struct.pack(">H", cid))[2]

    def set_flags(flags, cid=0x0053):
        dev.request(rc_idx, 3, struct.pack(">HB", cid, flags))

    def poll(label, seconds=2.0):
        seen = []
        t0 = time.time()
        while time.time() - t0 < seconds:
            seen.append(get_flags())
            time.sleep(0.1)
        uniq = sorted(set(seen))
        print(f"  {label}: reads={len(seen)} unique={[hex(u) for u in uniq]} "
              f"first={hex(seen[0])} last={hex(seen[-1])}", flush=True)
        return seen

    orig = get_flags()
    print(f"original flags: 0x{orig:02x}", flush=True)

    print("set 0x00 (divert off, 3-byte):", flush=True)
    set_flags(0x00)
    poll("after set 0x00")

    print("set 0x02:", flush=True)
    set_flags(0x02)
    poll("after set 0x02", 1.0)

    print("set 0x04:", flush=True)
    set_flags(0x04)
    poll("after set 0x04", 1.0)

    print("set 0x05:", flush=True)
    set_flags(0x05)
    poll("after set 0x05", 1.0)

    print("restore 0x01:", flush=True)
    set_flags(orig)
    poll("after restore", 1.0)
    print(f"final flags: 0x{get_flags():02x} (orig 0x{orig:02x})", flush=True)
finally:
    dev.close()
print("probe10 done", flush=True)
