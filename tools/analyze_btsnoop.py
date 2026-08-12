"""
BLE traffic decoder for the official iPrint Android app.

Purpose: capture what the Android app ACTUALLY writes to the thermal printer
over GATT, so we can match its image pipeline exactly (row width, opcodes,
energy values, 1-bit vs grayscale).

Input:  Android "Bluetooth HCI snoop log" (btsnoop_hci.log), which is the
        btsnoop binary format. Wireshark can also save these as pcap — pass
        that file instead if preferred.

Usage:
    python tools/analyze_btsnoop.py path/to/btsnoop_hci.log
    python tools/analyze_btsnoop.py --selftest      # verify parser against a synthetic job

Output: the full byte stream the app wrote to the printer, plus a decoded
        packet summary (opcodes, row byte-lengths, energy values).
"""

import os
import sys
import struct

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ── btsnoop binary format ────────────────────────────────────────────────
# Records: orig_len(4BE) incl_len(4BE) flags(4BE) drops(4BE) ts(8BE) data[incl_len]

BTSNOOP_MAGIC = b"btsnoop\x00"
H4_ACL = 0x02
L2CAP_CID_ATT = 0x0004
ATT_WRITE_CMD = 0x52   # write command (write-without-response)
ATT_WRITE_REQ = 0x12   # write request (write-with-response)


def read_btsnoop(path: str):
    """Yields HCI ACL payload chunks (handle, start_flag, data)."""
    with open(path, "rb") as f:
        magic = f.read(8)
        if magic != BTSNOOP_MAGIC:
            raise ValueError("Not a btsnoop file (bad magic). Is this the HCI snoop log?")
        version, datalink = struct.unpack(">II", f.read(8))
        while True:
            header = f.read(24)
            if len(header) < 24:
                break
            orig_len, incl_len, flags, drops, ts = struct.unpack(">IIIIq", header)
            data = f.read(incl_len)
            if len(data) < incl_len:
                break
            if not data:
                continue
            pkt_type = data[0]
            if pkt_type == H4_ACL:
                yield data[1:]  # ACL payload (handle+flags | len | l2cap...)
    f.close()


def reassemble_l2cap(acl_chunks):
    """
    Reassembles fragmented ACL packets per connection handle into complete
    L2CAP PDUs: returns list of (cid, payload_bytes).
    """
    buffers = {}
    pdus = []
    for acl in acl_chunks:
        if len(acl) < 4:
            continue
        hdr = struct.unpack_from("<HH", acl, 0)
        hf, _acl_len = hdr[0], hdr[1]
        handle = hf & 0x0FFF
        flags = (hf >> 12) & 0x0F
        body = acl[4:4 + _acl_len]
        is_start = (flags & 0x01) == 0
        if is_start:
            if len(body) >= 4:
                l2_len, cid = struct.unpack_from("<HH", body, 0)
                buffers[handle] = {"cid": cid, "need": l2_len, "buf": bytearray(body[4:])}
        else:
            buf = buffers.get(handle)
            if buf is not None:
                buf["buf"] += body
                if len(buf["buf"]) >= buf["need"]:
                    pdus.append((buf["cid"], bytes(buf["buf"][: buf["need"]])))
                    del buffers[handle]
    return pdus


def extract_gatt_writes(pdus):
    """Returns ordered list of (att_opcode, handle, value) from ATT PDUs."""
    writes = []
    for cid, payload in pdus:
        if cid != L2CAP_CID_ATT or len(payload) < 3:
            continue
        opcode = payload[0]
        if opcode in (ATT_WRITE_CMD, ATT_WRITE_REQ):
            handle = struct.unpack_from("<H", payload, 1)[0]
            writes.append((opcode, handle, payload[3:]))
        # ATT: 0x16/0x56 = prepare/execute long write (not used for
        # write-without-response, but collect for completeness)
        elif opcode in (0x16, 0x56, 0xD2):
            writes.append((opcode, 0, payload[1:]))
    return writes


def analyze_stream(stream: bytes):
    """Decodes the byte stream with the iPrint packet parser."""
    from backend.protocols.iprint import IPrintProtocol

    summary = {
        "total_bytes": len(stream),
        "iprint_packets": 0,
        "garbage_bytes": 0,
        "opcodes": {},          # opcode hex -> count
        "a2_row_lengths": set(),# row byte-lengths seen for Draw Bitmap
        "a2_row_count": 0,
        "af_energies": [],      # energy values from Set Energy
        "not_iprint": False,
    }
    if not stream:
        return summary

    packets = IPrintProtocol.parse_stream(stream)
    for p in packets:
        op = p.get("opcode")
        name = p.get("opcode_name")
        if op is None:
            summary["garbage_bytes"] += max(1, (p.get("length") or 0))
            summary["not_iprint"] = True
            continue
        summary["iprint_packets"] += 1
        summary["opcodes"][f"0x{op:02X} ({name})"] = summary["opcodes"].get(f"0x{op:02X} ({name})", 0) + 1
        if op == 0xA2:
            summary["a2_row_count"] += 1
            summary["a2_row_lengths"].add(p["length"])
        if op == 0xAF:
            raw = bytes.fromhex(p["payload_hex"])
            if len(raw) >= 2:
                summary["af_energies"].append(raw[0] | (raw[1] << 8))
    return summary


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--selftest":
        selftest()
        return

    path = sys.argv[1]
    print(f"Reading {path} ...")
    acl_chunks = list(read_btsnoop(path))
    print(f"HCI ACL packets found: {len(acl_chunks)}")
    pdus = reassemble_l2cap(acl_chunks)
    print(f"L2CAP PDUs reassembled: {len(pdus)}")
    writes = extract_gatt_writes(pdus)
    print(f"GATT writes captured: {len(writes)}")

    stream = b"".join(v for _, _, v in writes)
    out_raw = os.path.join(os.path.dirname(path), "printer_stream.bin")
    with open(out_raw, "wb") as f:
        f.write(stream)
    print(f"Raw write stream saved to: {out_raw}")

    s = analyze_stream(stream)
    print("\n=== DECODED SUMMARY ===")
    print(f"Total bytes written:   {s['total_bytes']}")
    print(f"iPrint packets:        {s['iprint_packets']}")
    print(f"Non-iPrint bytes:      {s['garbage_bytes']}  {'⚠  THE APP USES A DIFFERENT STREAM!' if s['not_iprint'] else ''}")
    for op, n in sorted(s["opcodes"].items()):
        print(f"  {op:<32} {n}")
    if s["a2_row_count"]:
        print(f"Draw Bitmap rows:      {s['a2_row_count']}  (row byte-lengths: {sorted(s['a2_row_lengths'])})")
        expected = 48
        if s["a2_row_lengths"] and sorted(s["a2_row_lengths"])[-1] != expected:
            print(f"⚠  ROWS ARE NOT {expected} BYTES — the app uses a different raster format!")
    if s["af_energies"]:
        print(f"Set Energy values:     {s['af_energies']}")

    print("\nNext: share the decoded printer_stream.bin + this summary, and I can")
    print("match our pipeline to whatever the app really sends.")


def selftest():
    """Builds a synthetic iPrint job, wraps it in ATT/ACL/btsnoop layers, and
    verifies the decoder recovers the exact original stream."""
    from backend.protocols.iprint import IPrintProtocol
    from PIL import Image

    img = Image.new("1", (384, 40), 1)
    job = IPrintProtocol.generate_payload(img, feed_lines=20, density=8)

    # Wrap into GATT writes exactly like bleak would (180-byte chunks).
    writes = []
    for i in range(0, len(job), 180):
        writes.append((ATT_WRITE_CMD, 0xAE01, job[i:i + 180]))

    # Build L2CAP → ACL → btsnoop records.
    records = b""
    for opcode, handle, value in writes:
        att = bytes([opcode]) + struct.pack("<H", handle) + value
        l2 = struct.pack("<HH", len(att), L2CAP_CID_ATT) + att
        chunks = [l2[i:i + 100] for i in range(0, len(l2), 100)]
        for idx, chunk in enumerate(chunks):
            flags = 0x02 if idx == 0 else 0x01
            hdr = struct.pack("<HH", (0x0001 & 0x0FFF) | (flags << 12), len(chunk))
            acl = bytes([H4_ACL]) + hdr + chunk
            records += struct.pack(">IIIIq", len(acl), len(acl), 0, 0, 0) + acl

    with open("selftest_btsnoop.bin", "wb") as f:
        f.write(BTSNOOP_MAGIC + struct.pack(">II", 1, 1002) + records)

    acl_chunks = list(read_btsnoop("selftest_btsnoop.bin"))
    pdus = reassemble_l2cap(acl_chunks)
    recovered = b"".join(v for _, _, v in extract_gatt_writes(pdus))

    assert recovered == job, "recovered stream differs from the original!"
    s = analyze_stream(recovered)
    assert s["a2_row_count"] == 40, f"expected 40 rows, got {s['a2_row_count']}"
    assert s["a2_row_lengths"] == {48}, s["a2_row_lengths"]
    assert s["af_energies"] == [17520], s["af_energies"]  # 0x70 0x44 = known-good baseline
    print("SELFTEST PASSED — decoder round-trips a full iPrint job exactly.")
    print(f"Rows={s['a2_row_count']} x 48B, energy={s['af_energies']}")
    os.remove("selftest_btsnoop.bin")


if __name__ == "__main__":
    main()
