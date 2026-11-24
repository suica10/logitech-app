# HID++ probe for MX Master 2S — run on the desktop (Python 3.12 venv or system python with hidapi installed)
# Step 1: enumerate HID interfaces with vendor 0x046D, print usage page / product.
# Step 2: on the HID++ interface (usage page 0xFF00, usage 1 or 2), send a ping to device 0x01..0x06 (receiver slots)
#         and 0xFF (receiver), then IRD / device name / feature table (x0000 IRD, x0005 device name).
import sys, struct, time

try:
    import hid
except ImportError:
    print("hidapi not installed: pip install hidapi")
    sys.exit(1)

VID = 0x046D

def hexs(b):
    return " ".join(f"{x:02x}" for x in b)

print("=== HID devices VID_046D ===")
targets = []
for d in hid.enumerate(VID, 0):
    print(f"path={d['path']} product={d.get('product_string')} manufacturer={d.get('manufacturer_string')} "
          f"usage_page=0x{d['usage_page']:04x} usage=0x{d['usage']:02x} pid=0x{d['product_id']:04x} iface={d['interface_number']}")
    if d['usage_page'] == 0xFF00:
        targets.append(d)

if not targets:
    print("No HID++ interface (usage page 0xFF00) found.")
    sys.exit(0)

def open_path(path):
    h = hid.device()
    h.open_path(path)
    h.set_nonblocking(0)
    return h

def send_recv(h, msg, timeout_ms=1500):
    h.write(msg)
    deadline = time.time() + timeout_ms / 1000.0
    out = []
    while time.time() < deadline:
        r = h.read(64, 300)
        if r:
            out.append(bytes(r))
            # stop when we see a reply whose bytes 2.. match request fn/swid or an error (0x8f / 0xff)
            if r[0] in (0x10, 0x11) and len(r) >= 4 and (r[2] == msg[2] or r[2] in (0x8F,)):
                break
    return out

def hidpp_long(dev_index, feature_index, function, *params):
    # report 0x11, 20 bytes: [0x11, dev, feature, fn|swid<<4? ] we use swid=0x0A in low nibble packing: byte3 = (function<<4)|swid
    swid = 0x0A
    b = bytearray(20)
    b[0] = 0x11
    b[1] = dev_index
    b[2] = feature_index
    b[3] = (function << 4) | swid
    for i, p in enumerate(params):
        b[4 + i] = p
    return bytes(b)

for t in targets:
    print(f"\n=== probing {t.get('product_string')} pid=0x{t['product_id']:04x} usage=0x{t['usage']:02x} ===")
    try:
        h = open_path(t['path'])
    except Exception as e:
        print(f"open failed: {e}")
        continue
    # ping: feature 0 (IRD is index 0), function 1? IRD ping is feature x0000 function 1 with 3 random bytes echoed.
    for dev in (0xFF, 1, 2, 3, 4, 5, 6):
        ping = hidpp_long(dev, 0x00, 0x01, 0xAA, 0xBB, 0xCC)
        try:
            reps = send_recv(h, ping, 800)
        except Exception as e:
            print(f"dev {dev}: io error {e}")
            break
        for r in reps:
            print(f"dev {dev}: <- {hexs(r[:20])}")
    h.close()
print("\nDone.")
