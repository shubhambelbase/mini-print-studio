# SC03h "iPrint" Thermal Printer Protocol — Complete Implementation Guide

A fully documented, implementation-ready reference for the proprietary Bluetooth Low Energy (BLE) binary protocol used by the **SC03h** thermal pocket printer and its clones (**FC02, D1, GB01, GB02, WalkPrint, FunPrint**). These printers are sold under many generic brands and normally pair with the mobile app "iPrint".

This guide is written so the protocol can be implemented in **any language or platform** (Python, JavaScript/Web Bluetooth, C, Rust, Kotlin, Flutter…), with exact byte layouts, algorithms, reference code, and a hard list of what to do and what never to do.

---

## Table of Contents

1. [Hardware Identification](#1-hardware-identification)
2. [BLE Discovery & Connection](#2-ble-discovery--connection)
3. [Packet Structure (The Foundation)](#3-packet-structure-the-foundation)
4. [CRC8 Checksum (Self-Contained)](#4-crc8-checksum-self-contained)
5. [Opcode Reference](#5-opcode-reference)
6. [The Print Sequence](#6-the-print-sequence)
7. [Image Data Format](#7-image-data-format)
8. [Reliable Transport for Long Jobs](#8-reliable-transport-for-long-jobs)
9. [Reading Device Status (Battery / Paper)](#9-reading-device-status-battery--paper)
10. [Implementing in Any Language](#10-implementing-in-any-language)
11. [Reference Implementation — Python (Bleak)](#11-reference-implementation--python-bleak)
12. [Reference Implementation — JavaScript (Web Bluetooth)](#12-reference-implementation--javascript-web-bluetooth)
13. [What NOT To Do (The Full Pitfall List)](#13-what-not-to-do-the-full-pitfall-list)
14. [Troubleshooting Checklist](#14-troubleshooting-checklist)
15. [Quick Reference Card](#15-quick-reference-card)
16. [Working With the Companion App](#16-working-with-the-companion-app-mini-print-studio)

---

## 1. Hardware Identification

### 1.1 What the printer looks like over BLE

| Field | Typical value |
| :--- | :--- |
| Device name | `SC03h-XXXX`, `FC02`, `D1`, `GB01`, `GB02`, `WalkPrint`, `FunPrint`, "iPrint", "Cat"… |
| MAC address | Local/random address, e.g. `AA:BB:CC:DD:EE:FF` |
| Primary service | `0000ae30-0000-1000-8000-00805f9b34fb` |
| Write characteristic | `0000ae01-0000-1000-8000-00805f9b34fb` |
| Notify characteristic | `0000ae02-0000-1000-8000-00805f9b34fb` |
| Paper width | 58 mm, **384 dots** printable width |
| Resolution | 384 × N dots (8 dots/mm) |

### 1.2 Detecting an iPrint device in a scan

Not every BLE device near you is this printer. Use **both** filters:

1. **Service filter**: device advertises the `0000ae30-...` service (when advertised).
2. **Name heuristic**: lowercase name contains any of
   `iprint, cat, gb01, gb02, walkprint, funprint, sc03h, fc02, d1, pocket, mini, thermal`.
   If matched → the device almost certainly speaks this protocol. Otherwise it is likely a standard ESC/POS-over-BLE printer and **this protocol must not be used**.

### 1.3 Discovering services after connect

After connecting, enumerate all services/characteristics and collect candidates:

- Writable characteristics (`write` or `write-without-response`) — pick `0000ae01-...` first if present, then fall back to any other writable one (many clones expose `ae3b`, `ae10`, or vendor UART UUIDs).
- Notifiable characteristics (`notify`/`indicate`) — you must subscribe to **all** of them (at minimum `ae02`).

Common fallback write UUIDs seen in the wild:

```
0000ae01-0000-1000-8000-00805f9b34fb   (iPrint main — prefer this)
0000ae3b-0000-1000-8000-00805f9b34fb   (iPrint alternate service)
0000ae10-0000-1000-8000-00805f9b34fb
49535343-8841-43f4-a8d4-ecbe34729bb3   (ISSC transparent UART)
49535343-1e4d-4bd9-ba61-23c647249616
e7810a71-73ae-499d-8c15-faa9aef0c3f2
0000ffe1-0000-1000-8000-00805f9b34fb   (HM-10 style UART)
00002af1-0000-1000-8000-00805f9b34fb
6e400002-b5a3-f393-e0a9-e50e24dcca9e   (Nordic UART)
0000ff02-0000-1000-8000-00805f9b34fb
0000ff01-0000-1000-8000-00805f9b34fb
000018f0-0000-1000-8000-00805f9b34fb
```

Rule: **try characteristics in priority order; the first one that accepts a write and doesn't error wins.** If a write partially succeeds and then fails, do **not** retry the same payload on another characteristic (see §13.7).

---

## 2. BLE Discovery & Connection

### 2.1 Connection requirements (do these in order)

1. **Connect** to the device (classic GATT connect).
2. **Subscribe to every notify/indicate characteristic immediately** — especially `ae02`. The printer uses the subscription as a "host is alive" signal. **If you skip it, the printer ignores writes or falls back asleep.**
3. **Confirm the write characteristic** (see §1.3).
4. Never assume `is_connected` means the link is healthy — see stale socket pitfall (§13.2).

### 2.2 Write chunking (MTU limit)

The printer's BLE receive buffer is tiny.

- **Maximum chunk size: 180 bytes** per write.
- **Delay between chunks: ≥ 10 ms** normally, **≥ 25 ms for large jobs** (payload > ~20 KB).
- Send with `write-without-response` when the characteristic supports it; regular write also works on most units.

---

## 3. Packet Structure (The Foundation)

Every command is an independent binary packet. Packets are simply concatenated into one stream and written in order.

| Offset | Size | Name | Value |
| :--- | :--- | :--- | :--- |
| 0 | 1 | Magic | `0x51` |
| 1 | 1 | Magic | `0x78` |
| 2 | 1 | Opcode | Command ID (see §5) |
| 3 | 1 | Flags | Always `0x00` |
| 4 | 2 | Payload length | **uint16 little-endian** — length of payload only |
| 6 | N | Payload | Command data (variable) |
| 6+N | 1 | CRC8 | `crc8(payload)` — **only the payload bytes** |
| 7+N | 1 | Terminator | Always `0xFF` |

> ⚠️ **Length field is 16-bit LE.** Older community docs and some samples use a single byte. On this printer every payload in practice is < 256 bytes, so byte 5 is usually `0x00` — but encode it as a proper little-endian uint16 anyway.

### 3.1 Pseudo-code

```
function make_packet(opcode, payload):
    packet = [0x51, 0x78, opcode, 0x00]
    packet += little_endian_u16(len(payload))
    packet += payload
    packet += [crc8(payload), 0xFF]
    return packet
```

---

## 4. CRC8 Checksum (Self-Contained)

**CRC-8/ATM: polynomial `0x07`, initial value `0x00`**, MSB-first, no reflection, no final XOR. Computed **only over the payload bytes**.

> ⚠️ **Correction to older community docs:** some guides claim polynomial `0x31`. That is **incorrect** — a table built with `0x31` mismatches the firmware-verified table in 254 of 256 entries. The hardware-verified polynomial is `0x07` (see the full-table comparison in the test-vector section). The table below is the one that actually works on real devices.

### 4.1 Bit-by-bit implementation (any language)

```
function crc8(data):
    crc = 0x00
    for byte in data:
        crc ^= byte
        for i in 1..8:
            if crc & 0x80:
                crc = (crc << 1) ^ 0x07
            else:
                crc = crc << 1
            crc &= 0xFF
    return crc
```

### 4.2 Table-based implementation (fast)

Precompute (or copy) this 256-entry table, then:

```
crc = 0
for byte in data:
    crc = TABLE[(crc ^ byte) & 0xFF]
return crc
```

```
0x00 0x07 0x0e 0x09 0x1c 0x1b 0x12 0x15 0x38 0x3f 0x36 0x31 0x24 0x23 0x2a 0x2d
0x70 0x77 0x7e 0x79 0x6c 0x6b 0x62 0x65 0x48 0x4f 0x46 0x41 0x54 0x53 0x5a 0x5d
0xe0 0xe7 0xee 0xe9 0xfc 0xfb 0xf2 0xf5 0xd8 0xdf 0xd6 0xd1 0xc4 0xc3 0xca 0xcd
0x90 0x97 0x9e 0x99 0x8c 0x8b 0x82 0x85 0xa8 0xaf 0xa6 0xa1 0xb4 0xb3 0xba 0xbd
0xc7 0xc0 0xc9 0xce 0xdb 0xdc 0xd5 0xd2 0xff 0xf8 0xf1 0xf6 0xe3 0xe4 0xed 0xea
0xb7 0xb0 0xb9 0xbe 0xab 0xac 0xa5 0xa2 0x8f 0x88 0x81 0x86 0x93 0x94 0x9d 0x9a
0x27 0x20 0x29 0x2e 0x3b 0x3c 0x35 0x32 0x1f 0x18 0x11 0x16 0x03 0x04 0x0d 0x0a
0x57 0x50 0x59 0x5e 0x4b 0x4c 0x45 0x42 0x6f 0x68 0x61 0x66 0x73 0x74 0x7d 0x7a
0x89 0x8e 0x87 0x80 0x95 0x92 0x9b 0x9c 0xb1 0xb6 0xbf 0xb8 0xad 0xaa 0xa3 0xa4
0xf9 0xfe 0xf7 0xf0 0xe5 0xe2 0xeb 0xec 0xc1 0xc6 0xcf 0xc8 0xdd 0xda 0xd3 0xd4
0x69 0x6e 0x67 0x60 0x75 0x72 0x7b 0x7c 0x51 0x56 0x5f 0x58 0x4d 0x4a 0x43 0x44
0x19 0x1e 0x17 0x10 0x05 0x02 0x0b 0x0c 0x21 0x26 0x2f 0x28 0x3d 0x3a 0x33 0x34
0x4e 0x49 0x40 0x47 0x52 0x55 0x5c 0x5b 0x76 0x71 0x78 0x7f 0x6a 0x6d 0x64 0x63
0x3e 0x39 0x30 0x37 0x22 0x25 0x2c 0x2b 0x06 0x01 0x08 0x0f 0x1a 0x1d 0x14 0x13
0xae 0xa9 0xa0 0xa7 0xb2 0xb5 0xbc 0xbb 0x96 0x91 0x98 0x9f 0x8a 0x8d 0x84 0x83
0xde 0xd9 0xd0 0xd7 0xc2 0xc5 0xcc 0xcb 0xe6 0xe1 0xe8 0xef 0xfa 0xfd 0xf4 0xf3
```

### 4.3 Test vectors

```
payload = 0x00                        → crc8 = 0x00
payload = 0x33  (quality cmd)         → crc8 = 0x99
payload = 0x70 0x44 (energy 17500)    → crc8 = 0x79
payload = 0x23  (feed speed)          → crc8 = 0xE9
payload = 0x00..0x2F (48 bytes)       → crc8 = 0xC0
```

Verify your implementation by checking that `packet[len(packet)-2] == crc8(payload)` for any packet.

---

## 5. Opcode Reference

| Opcode | Name | Payload | Purpose |
| :--- | :--- | :--- | :--- |
| `0xA0` | Retract Paper | – | Pull paper back (rarely used) |
| `0xA1` | Feed Paper | uint16 LE dot count | Advance paper; **keep ≤ 100 dots per packet** |
| `0xA2` | Draw Bitmap | 48 bytes (one 384-dot row) | Print one horizontal line (1-bit) |
| `0xA3` | Get Device State | `[0x00]` | Wake-up / status query |
| `0xA4` | Set Quality | `[0x33]` | Blackening/quality level |
| `0xA6` | Control Lattice | multi-byte sequence | **NEVER on SC03h** (GB01-only calibration; crashes SC03h) |
| `0xA8` | Get Device Info | – | Firmware/model info |
| `0xAF` | Set Energy | uint16 LE heat energy | Density control; default `[0x70, 0x44]` = 17520 |
| `0xBD` | Other Feed (continuous) | `[0x23]` or `[0x19]` | Safe paper feed for tear-bar clearance |
| `0xBE` | Drawing Mode | `[0x00]` / `[0x00,0x00]` / `[0x00,0x01]` | 0 = 1-bit image; 0,0 = 8-level gray; 0,1 = **16-level gray** |
| `0xCF` | Gray Image Chunk | `len16, uncomp16, comp16, LZO data` | LZO-compressed 16-level grayscale rows (official app) |

### 5.1 Recommended parameter values

| Setting | Opcode | Value | Notes |
| :--- | :--- | :--- | :--- |
| Quality / blackening | `0xA4` | `0x33` | Standard quality |
| Energy (default) | `0xAF` | `0x70, 0x44` (17500 LE) | Known-good baseline |
| Energy (density 1–10) | `0xAF` | `uint16(17500 * density / 8)` | Scale from the default; clamp 0–65535 |
| Drawing mode | `0xBE` | `0x00` | Image mode |
| Print speed | `0xBD` | `0x23` (print) / `0x19` (blank) | See §6 |

---

## 6. The Print Sequence

The canonical sequence for printing one image. **Do not reorder, do not skip.**

```
STEP 1  0xA3 [0x00]                     Wake up / get device state
STEP 2  0xA4 [0x33]                     Set quality
        0xAF [0x70 0x44]                Set energy (or density-scaled value)
        0xBE [0x00]                     Set drawing mode = image
        0xBD [0x23]                     Set print speed
STEP 3  0xA2 <48 bytes>                 One packet per row, top row first,
        0xA2 <48 bytes>                 ... continuing until every row is sent
STEP 4  0xBD [0x23]  × 30–100           Feed paper past the tear bar
```

- All packets are concatenated into one byte stream and written in chunks (§2.2).
- The entire job can (and should) be built as one payload before sending.

### 6.1 Why a fixed init sequence

Each print job must start with the wake + init packets. Without them the printer may ignore rows or print with wrong energy. Sending the init packets **between** jobs (multi-copy printing) is fine — treat each copy as its own job.

### 6.2 Feed options

| Need | Command | Why |
| :--- | :--- | :--- |
| Clear tear bar (~40 mm) | `0xBD [0x23]` repeated ~50–100× | Safest; never overflows |
| Precise feed amount | `0xA1 <uint16 dots>` | OK, but **chunk in steps ≤ 100 dots** |
| Retract | `0xA0` | Rare; some firmwares ignore |

---

## 7. Image Data Format

### 7.1 Geometry

- **Width is fixed at 384 dots** (= 48 bytes per row). Images narrower than 384 must be **centered-padded** to 384. If a firmware ever receives a row of a different width, output will be garbled.
- Height is unbounded (limited by paper), each row is an independent packet.

### 7.2 Bit packing (MSB-first)

- 1 bit per pixel, 8 pixels per byte, **first (leftmost) pixel = bit 7**.
- **Bit value `1` = black dot printed; `0` = white.**
- Example — row `0b11000000 0b00000001` prints two dots at the left edge and one at the far right.

### 7.3 Converting an image (generic algorithm)

```
1. Decode image, convert to grayscale.
2. AUTO-LEVEL: stretch the histogram (1% clip both ends) — this single step is
   the biggest difference between washed-out prints and the official iPrint
   app's punchy output. Without it, midtones print as flat gray mud.
3. Dither to 1-bit (photos): Atkinson error diffusion is the recommended
   default (same family of kernels the official app uses); Floyd–Steinberg
   and Stucki are good alternatives; Bayer for flat graphics; plain
   threshold for text/QR/line art.
4. Resize so width == 384 (keep aspect, or pad centered with white).
5. For each row y:
       row_bytes = []
       byte = 0
       for x in 0..383:
           bit = 7 - (x % 8)
           if pixel(x, y) is black: byte |= (1 << bit)
           if x % 8 == 7:
               row_bytes.append(byte); byte = 0
       packet = make_packet(0xA2, row_bytes)
```

#### Dithering modes in the companion app (default = Atkinson)

| Mode | Kernel | Best for |
| :--- | :--- | :--- |
| `atkinson` | Atkinson error diffusion (6 neighbours, ⅛ each, ¼ discarded) | Photos, sketches, gradients — **default** |
| `floyd-steinberg` | Floyd–Steinberg (Pillow built-in) | Smooth classic diffusion |
| `stucki` | Stucki (12 neighbours, ÷42) | Richest blacks, smoothest gradients |
| `bayer` | 8×8 ordered matrix | Logos, icons, charts, flat graphics |
| `threshold` | Fixed 50% cutoff (no dither) | Text, QR codes, barcodes, line art |

### 7.4 Padding rule

```
if width != 384:
    pad = (384 - width) // 2          # left+right padding, white (0x00 pixels)
    paste image centered onto a 384-wide white canvas
```

---

## 8. Reliable Transport for Long Jobs

The single most important operational detail: **the printer's internal buffer is smaller than any real photo job.** If data arrives faster than the thermal head burns, the firmware silently drops the tail — the job "succeeds" from the host's point of view but the last part of the page never prints.

### 8.1 Pacing

- Payload ≤ ~20 KB → chunk delay **10 ms**.
- Payload > ~20 KB → chunk delay **25 ms**.
- This roughly matches the head's burn rate so the buffer never fills.

### 8.2 Packet-aligned segmentation (for very long jobs)

For jobs > ~20 KB, split the byte stream into **whole-packet bursts** and pause between bursts so the firmware drains:

```
1. Parse the stream packet-by-packet:
       packet_len = 6 + payload_len(packet[4:6]) + 2
2. Accumulate packets into bursts of ≈ 4 KB.
3. Send burst 1 (180-byte chunks, 25 ms apart).
4. Pause 600 ms.
5. Send burst 2 ... repeat until done.
```

Because bursts always start/end on `0x51 0x78` boundaries, the printer never sees a truncated packet.

### 8.3 After the last chunk

- **Do not disconnect for at least 3 seconds** after the final write. Closing early aborts the job and flushes the buffer.
- If the host keeps the connection open (normal for an app/server), this is automatic.

---

## 9. Reading Device Status (Battery / Paper)

The printer pushes status packets over the notify characteristic (`ae02`). Payloads arrive wrapped in the standard envelope (§3); strip it:

```
if packet[0] == 0x51 and packet[1] == 0x78:
    length = packet[4] | (packet[5] << 8)
    data   = packet[6 : 6 + length]
```

Best-effort state decoding (firmware-dependent — treat every field as optional):

| Field | Where | Heuristic |
| :--- | :--- | :--- |
| Battery % | `data[1]` | If `0 < data[1] <= 100` → battery level |
| Paper present | `data[0]` bit 2 | `data[0] & 0x04` set → paper out |
| Idle/OK | `data[0] == 0x00` | Paper present, ready |

Keep the raw hex for debugging. Always treat `0x00 0x00 ...` responses as "ready".

---

## 10. Implementing in Any Language

Whatever the platform, you need exactly these pieces:

1. **BLE connect + notify subscribe** (platform API).
2. **A byte-array builder** (packet encoder + CRC8).
3. **An image → 384×1-bit → 48-byte-rows converter** (§7).
4. **A chunked writer with pacing + optional segmentation** (§2.2, §8).
5. **A keep-alive wait** (≥ 3 s) before disconnect (§8.3).

### 10.1 Minimal pseudo-code (language-neutral)

```
job = []
job += packet(0xA3, [0x00])
job += packet(0xA4, [0x33])
job += packet(0xAF, u16le(17500))
job += packet(0xBE, [0x00])
job += packet(0xBD, [0x23])
for row in image_rows_384:          # each row = 48 bytes
    job += packet(0xA2, row)
for i in range(50):
    job += packet(0xBD, [0x23])

await ble.connect(mac)
await ble.subscribe(notify_uuid, on_notify)   # MANDATORY
chunks = split(job, 180)
delay = 0.025 if len(job) > 20000 else 0.01
for chunk in chunks:
    await ble.write(write_uuid, chunk)
    sleep(delay)
sleep(3.0)                                    # let it finish
# keep connection open if this is a service/app
```

### 10.2 Platform notes

- **Python / Bleak**: see §11.
- **Web Bluetooth**: see §12.
- **Android / Kotlin**: `BluetoothGatt.writeCharacteristic` in 180-byte slices; register a notify callback before writing.
- **iOS / Swift**: `CBPeripheral.writeValue` with `.withoutResponse` in slices.
- **Rust**: `btleplug` — same chunking rules.
- **Flutter**: `flutter_blue_plus` — same rules.

The protocol itself has **zero dependencies** — only raw byte arrays and timers are required.

---

## 11. Reference Implementation — Python (Bleak)

Complete, production-shaped example (pacing + segmentation + notify subscription + status capture).

```python
import asyncio
from bleak import BleakClient, BleakScanner

MAC = "AA:BB:CC:DD:EE:FF"          # your printer's address

SERVICE   = "0000ae30-0000-1000-8000-00805f9b34fb"
WRITE     = "0000ae01-0000-1000-8000-00805f9b34fb"
NOTIFY    = "0000ae02-0000-1000-8000-00805f9b34fb"

CHUNK = 180

# ── CRC8 (self-contained bit-by-bit; the faster table is in section 4.2) ──
def crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc

def packet(opcode: int, payload: bytes) -> bytes:
    length = len(payload)
    head = bytes([0x51, 0x78, opcode, 0x00, length & 0xFF, (length >> 8) & 0xFF])
    return head + payload + bytes([crc8(payload), 0xFF])

# ── Image → rows ──────────────────────────────────────────────
def image_rows(img_1bit_384wide) -> list:
    rows = []
    px = img_1bit_384wide.load()
    w, h = img_1bit_384wide.size
    for y in range(h):
        row = bytearray()
        for x in range(0, w, 8):
            byte = 0
            for bit in range(8):
                if px[x + bit, y] == 0:          # black pixel
                    byte |= 1 << (7 - bit)       # MSB-first
            row.append(byte)
        rows.append(bytes(row))
    return rows

# ── Payload construction ──────────────────────────────────────
def build_job(rows) -> bytes:
    out = bytearray()
    out += packet(0xA3, b"\x00")                 # wake
    out += packet(0xA4, b"\x33")                 # quality
    out += packet(0xAF, (17500).to_bytes(2, "little"))  # energy
    out += packet(0xBE, b"\x00")                 # image mode
    out += packet(0xBD, b"\x23")                 # speed
    for row in rows:
        out += packet(0xA2, row)                 # one per line
    for _ in range(50):
        out += packet(0xBD, b"\x23")             # tear-bar feed
    return bytes(out)

# ── Packet-aligned segmentation for long jobs ────────────────
def split_packets(payload: bytes, burst_size: int = 4096) -> list:
    bursts, current, i, n = [], bytearray(), 0, len(payload)
    while i < n:
        if n - i < 6:
            current += payload[i:]; break
        plen = payload[i + 4] | (payload[i + 5] << 8)
        plen = 6 + plen + 2
        if i + plen > n:
            plen = n - i
        current += payload[i:i + plen]
        i += plen
        if len(current) >= burst_size:
            bursts.append(bytes(current)); current = bytearray()
    if current:
        bursts.append(bytes(current))
    return bursts

# ── Sender ────────────────────────────────────────────────────
async def send_job(mac: str, payload: bytes):
    async with BleakClient(mac) as client:
        last_notify = []
        def on_notify(sender, data):
            last_notify.append(bytes(data))

        await client.start_notify(NOTIFY, on_notify)      # MANDATORY
        chunks = split_packets(payload) if len(payload) > 20000 else [payload]
        delay = 0.025 if len(payload) > 20000 else 0.01

        for burst in chunks:
            for i in range(0, len(burst), CHUNK):
                await client.write_gatt_char(WRITE, burst[i:i + CHUNK])
                await asyncio.sleep(delay)
            await asyncio.sleep(0.6)                      # drain pause

        await asyncio.sleep(3.0)                          # finish before exit
        # keep-alive: leave the connection open in a real service

# ── Example ───────────────────────────────────────────────────
async def main():
    rows = image_rows(render_your_bitmap())               # 384-wide "1" mode PIL image
    await send_job(MAC, build_job(rows))

asyncio.run(main())
```

---

## 12. Reference Implementation — JavaScript (Web Bluetooth)

```js
const SERVICE = "0000ae30-0000-1000-8000-00805f9b34fb";
const WRITE   = "0000ae01-0000-1000-8000-00805f9b34fb";
const NOTIFY  = "0000ae02-0000-1000-8000-00805f9b34fb";
const CHUNK   = 180;

const CRC8_TABLE = [ /* 256 entries from section 4.2 */ ];

function crc8(data) {
  let crc = 0;
  for (const b of data) crc = CRC8_TABLE[(crc ^ b) & 0xFF];
  return crc & 0xFF;
}

function packet(opcode, payload) {
  const len = payload.length;
  return new Uint8Array([
    0x51, 0x78, opcode, 0x00, len & 0xFF, (len >> 8) & 0xFF,
    ...payload, crc8(payload), 0xFF,
  ]);
}

async function printBitmap(canvas) {
  // canvas: 384-wide, 1-bit (0 = black) ImageData
  const device = await navigator.bluetooth.requestDevice({
    filters: [{ services: [SERVICE] }, { namePrefix: "SC03h" }],
  });
  const server = await device.gatt.connect();
  const service = await server.getPrimaryService(SERVICE);

  await service.getCharacteristic(NOTIFY).startNotifications(); // MANDATORY

  const jobs = [];  // build packets...
  // wake / init / rows / feed  (same order as Python example)

  const write = service.getCharacteristic(WRITE);
  for (let i = 0; i < jobs.length; i += CHUNK) {
    await write.writeValueWithoutResponse(jobs.slice(i, i + CHUNK));
    await new Promise(r => setTimeout(r, len > 20000 ? 25 : 10));
  }
  await new Promise(r => setTimeout(r, 3000)); // let it finish
}
```

---

## 13. What NOT To Do (The Full Pitfall List)

1. **NEVER send `0xA6` (Control Lattice) to an SC03h.** GB01-era docs recommend it for calibration; on SC03h it **crashes the firmware / drops the job**.
2. **NEVER reuse a stale BLE connection after the system restarts.** The OS socket can die while `is_connected` still reports `True`. If writes start failing "mysteriously", tear down and reconnect fresh.
3. **NEVER skip the notify subscription.** No `start_notify` → the printer stalls or ignores you.
4. **NEVER write chunks > 180 bytes.** Tiny MTU buffer — hard limit.
5. **NEVER disconnect right after the last chunk.** Wait ≥ 3 s or the job aborts and the buffer flushes.
6. **NEVER use `0xA1` for large feeds.** Keep each `0xA1` ≤ 100 dots; prefer repeated `0xBD [0x23]` for tear-bar clearance.
7. **NEVER retry a payload on another characteristic after a partial write.** The printer already received part of it; re-sending duplicates/corrupts. Fail the job and reconnect instead.
8. **NEVER assume a plain ESC/POS command stream works.** This is a binary packet protocol, not text commands. (ESC/POS-style jobs go to *different* printer models.)
9. **NEVER send rows wider than 384 dots.** Pad/center first (§7.4).
10. **NEVER flood a long job without pacing.** Payload > ~20 KB without 25 ms pacing silently loses the tail (§8).
11. **NEVER rely on the notify payload layout being identical across clones.** Battery/paper heuristics (§9) are best-effort; always log raw hex.
12. **NEVER treat a successful `write_gatt_char` as "printed".** It only means the bytes left your machine.

---

## 14. Troubleshooting Checklist

| Symptom | Most likely cause | Fix |
| :--- | :--- | :--- |
| Nothing prints, no response | Notify not subscribed | Subscribe to `ae02` before writing |
| Nothing prints, writes error | Stale socket after reboot | Reconnect fresh (§13.2) |
| Page prints but **tail is missing** | Buffer overflow on long job | 25 ms pacing + packet bursts (§8) |
| Garbled / mirrored rows | Wrong bit order or row width | MSB-first packing, exactly 48 bytes/row |
| Faint or too-dark output | Energy wrong | `0xAF` energy 17500 baseline; scale with density |
| Only first page of a multi-copy job | Treated copies as one stream | Send wake+init per copy (§6.1) |
| Job aborts on disconnect | Closed too fast | Hold ≥ 3 s (§8.3) |
| Writes fail mid-job | Connection dropped | Auto-reconnect + resend the whole job |
| Battery always missing | Clone doesn't report it | Accept `None`; don't guess |

---

## 15. Quick Reference Card

```
SERVICE 0000ae30-...  WRITE 0000ae01-...  NOTIFY 0000ae02-...
PACKET  51 78 <op> 00 <len16le> <payload> <crc8(payload)> FF
CRC8    poly 0x07 (CRC-8/ATM), init 0x00, over payload only
IMAGE   384 dots wide · 1 bit/pixel · MSB-first · 48 bytes/row · 1=black
CHUNK   180 B max · 10 ms (25 ms if >20 KB) · 600 ms between 4 KB bursts
JOB     0xA3[00] 0xA4[33] 0xAF[70 44] 0xBE[00] 0xBD[23] rows... feed×50
FEED    use 0xBD[23] repeatedly · 0xA1 only ≤100 dots
STATUS  notify payload[0]: 0x04 bit = paper out · payload[1] = battery%
NEVER   0xA6 · stale sockets · skip notify · >180 B chunks · instant drop
```

---

## 16. Working With the Companion App (Mini Print Studio)

### 16.1 Device discovery & connection

- **Real devices only.** Scan results contain BLE hardware exclusively — unnamed devices (phones, TVs, trackers) and any mock/virtual entries are filtered out. No simulator is shipped in the UI.
- The protocol is auto-detected from the device name (`SC03h`, `gb01`, `walkprint`, etc. → `iprint`; everything else → `escpos`).
- Connect uses a **20-second hard cap** (`asyncio.wait_for`) plus a 10s Bleak timeout, so an unreachable printer fails cleanly instead of hanging.
- The UI shows an interactive **connection popup**: animated steps (Locating → BLE link → Service discovery → Notify subscription → Finalizing), a pulsing "Waiting for the printer to respond…" state, then a connected card with device name, protocol, address, and battery — or a red failure step with the error and a Retry button.

### 16.2 Template conventions (as of the latest build)

- **No `bold=True` in templates** — bold was removed from all built-in templates because it prints poorly on the SC03h at small sizes. Headings rely on `font_size`, inversion, and spacing.
- Image blocks may set an explicit `dither_mode` (e.g. `"threshold"` for line art); blocks **without** one follow the global toolbar selection (default `atkinson`).
- Every image passes through **auto-level** (histogram stretch, 1% clip) before dithering — do not add extra contrast on top or output becomes harsh.
- Text blocks support `font_family` (arial, courier, times, tahoma, verdana, georgia, comic, impact, consolas, calibri), `custom_font_size`, `line_spacing`, `letter_spacing`.
- Templates appear in the modal with automatic category chips, a favorite ⭐ toggle, and a "+ Batch" button.

### 16.3 Batch printing workflow

1. **Add items from the dashboard** — the editor's "Add to Batch" button, or the "+ Batch" button on any template/saved document. Duplicate adds are rejected; the basket persists in `localStorage` and is auto-deduplicated on load.
2. **Batch tab** shows only what you added. Each item is one job; the footer shows the exact total (`items × copies = prints`).
3. **Send to Queue** — one `POST /api/print` per basket item, processed by the backend queue (queued → preparing → printing → completed) with live status in the batch tab.
4. Every job record stores its original blocks, enabling one-click **Reprint** from the History modal.

### 16.4 Example template addition

```python
PrintTemplate(
    id="custom_label",
    name="Custom Cool Label",
    description="A sleek label with graphics and barcode.",
    category="Labels",
    icon="star",
    is_builtin=True,
    blocks=[
        ContentBlock(type="text", content="PREMIUM", font_size="title", align="center"),
        ContentBlock(type="space", space_height=10),
        ContentBlock(
            type="image",
            image_data="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
            align="center",
            scale_mode="fit",
            dither_mode="threshold"   # explicit mode is respected over the toolbar
        ),
        ContentBlock(type="line", line_style="solid"),
        ContentBlock(
            type="barcode",
            barcode_payload="1234567890",
            barcode_type="code128",
            barcode_height=50,
            show_barcode_text=True,
            align="center"
        )
    ]
)
```

The system converts these blocks into a 384-pixel-wide 1-bit thermal image, packs it with the SC03h protocol, and sends it over Bluetooth.

---

*Compiled from hardware testing against an SC03h unit (MAC `AA:BB:CC:DD:EE:FF`). Protocol reverse-engineering credits: the community work by WerWolv and NaitLee on the iPrint/GB01 protocol.*

---

## 17. True Grayscale Printing (16-level) — the official app's photo mode

**Why official-app photos look "natural":** the SC03h firmware has a **real
grayscale mode**. Every dot receives one of **16 heat levels** — the paper
shows actual gray shades, with no dithering dot patterns at all. The 1-bit
`0xA2` path in §7 is only the "image" mode the app uses for text/line art.

This section is decoded from the official app APK (`com.frogtosea.iprint`,
classes `com.lib.blueUtils.PrintDataUtils` / `ImageDisposeUtil`) and verified
against the SC03h profile data (`PrinterModelUtils`), not from the earlier
community documentation.

### 17.1 Mode activation

```
0xBE [0x00, 0x00]  →  8-level  grayscale image mode
0xBE [0x00, 0x01]  →  16-level grayscale image mode   ← the app's photo mode
```

### 17.2 Energy

The app uses a **separate gray energy** for the SC03h (not the 17520
baseline):

```
gray_energy = 4100 × (1 + 0.15 × (density − 4))
```

where `density` is the app's concentration setting (default 4 → exactly
4100). Sent as a normal `0xAF` packet before the mode switch.

### 17.3 Job sequence

```
0xAF  <gray_energy LE16>           set gray energy
0xBE  [0x00, 0x01]                 16-level gray image mode
0xBD  [<speed>]                    gray image speed (SC03h: 40)
<zero preheat header>              384/2 × 16 = 3072 zero bytes
0xCF  chunk 1 (LZO, 20 rows)       rows, 192 bytes each
0xBD  [<speed>]                    separator packet between chunks
0xCF  chunk 2 …
```

### 17.4 Gray chunk packet (`0xCF`)

```
51 78 CF 00 <len16le> <uncomp_len16le> <comp_len16le> <LZO data> <crc8> FF
```

| Field | Meaning |
| :--- | :--- |
| `len` | `comp_len + 4` (payload length) |
| `uncomp_len` | uncompressed chunk length (20 rows × 192 = 3840) |
| `comp_len` | compressed length |
| `LZO data` | **MiniLZO (LZO1X) compressed** chunk — the printer decompresses internally; raw data will NOT print |

The data must be compressed with LZO1X (minilzo-compatible). The chunked
data stream is: `[3072 zero preheat bytes] + rows`, split into chunks of
1920 bytes (20 rows) per `0xCF` packet, with a `0xBD [speed]` packet
between chunks.

### 17.5 Row format

- 384 dots → **192 bytes per row** (2 pixels per byte)
- Each pixel = **4-bit burn level** (0..15)
- **Nibble 0 = full heat (black), nibble 15 = no heat (white)**
- **First pixel in the LOW nibble**:
  `byte = (level(pixel x+1) << 4) | level(pixel x)`

### 17.6 Image processing (the app's math, exact)

1. **Grayscale** (weights 0.3 / 0.59 / 0.11)
2. **Tone curve** with a 20% histogram clip (far gentler than the 1% clip
   used for 1-bit prints), bounded to [110, 150]:
   - `v ≤ low` → `v × 0.46`
   - `v ≥ high` → `v + (255 − v) × 0.54`
   - between → linear interpolation
3. Multiply by **grayScale 0.9** (SC03h profile)
4. **Gray-level Floyd–Steinberg error diffusion** to 16 levels — errors
   spread between *gray shades*, not black/white
5. Pack to 4-bit nibbles (17.5)

### 17.7 Reference implementation

- `backend/services/minilzo.py` — pure-Python LZO1X compressor + decompressor,
  cross-verified against the reference C minilzo in both directions
- `ImageProcessor.process_gray()` — the exact image math above
- `IPrintProtocol.build_gray_payload()` — the job sequence / chunk builder
- Frontend: the **"True Grayscale"** toggle (job-level)

### 17.8 Pitfalls

- **Never** send uncompressed data in `0xCF` chunks (firmware decompresses).
- The nibble polarity (0 = black) is decoded from the app; an inverted print
  means the polarity is flipped on that firmware — flip `nibble = 15 − level`.
- Mixing gray chunks with 1-bit `0xA2` rows in one job requires a mode switch
  (`0xBE`) in between — the app treats gray and 1-bit as separate jobs.
