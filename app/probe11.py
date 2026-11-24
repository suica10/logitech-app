# Probe 11 - test the "value bit + valid bit" theory for SetCidReporting:
# write 0x02 = valid(1) + diverted(0) -> OFF; write 0x03 = valid(1) +
# diverted(1) -> ON. Verify on CID 0x53 (ends ON = original) and on
# CID 0xC3 (flags 0x11: check bit4 survives an off/on cycle).
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hidpp import HIDPPDevice  # noqa: E402

dev = HIDPPDevice(device_index=1)
try:
    rc_idx = dev.feature_index(0x1B04)

    def get_flags(cid):
        return dev.request(rc_idx, 2, struct.pack(">H", cid))[2]

    def set_raw(cid, byte):
        dev.request(rc_idx, 3, struct.pack(">HB", cid, byte))

    def wait_flags(cid, want, timeout=3.0):
        t0 = time.time()
        last = None
        while time.time() - t0 < timeout:
            last = get_flags(cid)
            if last == want:
                return last, time.time() - t0
            time.sleep(0.1)
        return last, timeout

    for cid in (0x0053, 0x00C3):
        orig = get_flags(cid)
        print(f"cid 0x{cid:04x} start flags: 0x{orig:02x}", flush=True)
        set_raw(cid, 0x02)  # valid + diverted=0
        got, dt = wait_flags(cid, orig & ~0x01)
        print(f"  after set 0x02: flags=0x{got:02x} (waited {dt:.1f}s, "
              f"expect 0x{orig & ~0x01:02x})", flush=True)
        set_raw(cid, 0x03)  # valid + diverted=1
        got, dt = wait_flags(cid, orig | 0x01)
        print(f"  after set 0x03: flags=0x{got:02x} (waited {dt:.1f}s, "
              f"expect 0x{orig | 0x01:02x})", flush=True)
        final = get_flags(cid)
        print(f"  final: 0x{final:02x} restored={final == orig}", flush=True)
finally:
    dev.close()
print("probe11 done", flush=True)
