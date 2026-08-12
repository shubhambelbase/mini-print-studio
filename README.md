# Mini Print Studio

<p align="center">
  <img src="banner.png" alt="Mini Print Studio" width="225">
</p>

[![CI](https://github.com/shubhambelbase/mini-print-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/shubhambelbase/mini-print-studio/actions/workflows/ci.yml)

Local-first web application for controlling a Bluetooth mini thermal printer from a desktop browser. No cloud services, no database — a FastAPI backend that talks to the printer, and a vanilla-JS frontend for designing, previewing, and printing content.

**Primary target hardware:** SC03h "iPrint" thermal pocket printer (58 mm, 384 dots) and its clones (FC02, D1, GB01, GB02, WalkPrint, FunPrint).

**Protocol reference:** [iPrint_SC03h_Protocol_Documentation.md](iPrint_SC03h_Protocol_Documentation.md) — a full implementation guide for the proprietary BLE binary protocol.

---

## Features

### Printing
- Block-based editor: text, images, QR codes, barcodes, separators, spacers
- **Receipt designer**: structured `table` and `totals` blocks (item rows, dotted-leader subtotal/TOTAL lines)
- Thermal image pipeline: auto-level, brightness/contrast/sharpen, dithering (Atkinson, Floyd–Steinberg, Stucki, Bayer, threshold)
- Live thermal preview (384 px, 1-bit), PNG/PDF export
- Print queue with queued → preparing → printing → completed/failed/cancelled states
- Multi-copy printing; per-copy wake+init (protocol §6.1); cancel between copies
- CSV → barcode label batch printing
- Batch basket (localStorage) → queue with live status
- Hardware diagnostic test page
- Reprint from history

### Printer management
- BLE scan/connect with protocol auto-detection from device name (iPrint vs ESC/POS)
- Interactive connection popup (steps + waiting/error/retry states), 20 s connect cap
- **Device info**: sends `0xA8` on connect and shows model/firmware on the dashboard
- **Keep-alive watchdog**: pings `0xA3` every 30 s; a failing ping tears down the stale BLE link (protocol §13.2) instead of failing mysteriously mid-print
- Battery/paper status from notify payloads (best-effort)
- Auto-reconnect to the last used printer on startup and after mid-print failures
- Settings: paper width, print resolution, margin, density, **tear-bar feed dots**

### Reliability (iPrint protocol)
- 180-byte BLE chunking, 10 ms pacing (25 ms for > 20 KB jobs)
- Packet-aligned 4 KB bursts with 600 ms drain pauses for long jobs
- CRC-8 (poly 0x07) validated per packet; wrong-width rows center-cropped
- Mandatory notify subscription enforced at connect time
- **Packet Inspector** (`/api/debug/*`): parsed last-job packets with CRC pass/fail, opcode names, raw hex, plus a live wire trace (TX/RX)

### Live updates
- **SSE** (`/api/events`): job state transitions and printer connect/disconnect pushed to the UI in real time (polling fallback)
- History modal with stats: totals by status, content-type breakdown, paper usage, prints today

---

## Architecture

```
┌────────────────────────────────────────────┐
│              WEB INTERFACE (vanilla JS)    │
│  Editor • Preview • Templates • Settings   │
│  Batch • History • Packet Inspector        │
└───────────────────┬────────────────────────┘
                    │ HTTP/JSON + SSE (EventSource)
                    ▼
┌────────────────────────────────────────────┐
│              FASTAPI BACKEND               │
│                                            │
│  api/        REST routers + events + debug │
│  services/   printer_manager (queue + SSE)│
│              print_engine (blocks → image) │
│              image_processor (thermal pipe)│
│              template_manager, documents   │
│  adapters/   ble (Bleak), bluetooth_classic│
│              mock                          │
│  protocols/  iprint, escpos, tspl          │
└───────────────────┬────────────────────────┘
                    │ BLE (180 B chunks, paced)
                    ▼
             Bluetooth Thermal Printer
```

Everything runs on `127.0.0.1`; no user content leaves the machine.

---

## Installation Guide

### 1. Requirements

| Requirement | Version / Notes |
| :--- | :--- |
| Python | **3.10+** (tested with 3.10–3.12) |
| OS | **Windows 10/11** (primary; BLE via Bleak + system Bluetooth, fonts from `C:/Windows/Fonts`) |
| Linux | Works for the web app + ESC/POS; BLE needs `bluez` and `python3-dev` (see below) |
| macOS | Web app + ESC/POS work; BLE support in Bleak is best-effort |
| Printer | Any BLE thermal printer speaking the iPrint protocol (SC03h, FC02, D1, GB01/02, WalkPrint, FunPrint…) or a standard ESC/POS-over-BLE printer |

### 2. Install

**Windows (PowerShell):**

```powershell
# 1. Clone / download the project, then:
cd mini-print-studio

# 2. Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt
```

**macOS / Linux (bash):**

```bash
cd mini-print-studio
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Linux only — BLE requires BlueZ + dev headers:
sudo apt install bluez libbluetooth-dev python3-dev   # Debian/Ubuntu
sudo systemctl enable --now bluetooth
```

### 3. Run the app

```bash
python -m backend.main
```

- The backend serves both the API and the web UI at **<http://127.0.0.1:8000>**
- It binds to localhost only — nothing is exposed to the network
- Optional: `MPS_DATA_DIR` relocates `settings.json`, `printers.json`, `history.json` (tests use this to isolate data)

### 4. Connect your printer (first run)

1. Power the printer **on** and put it near the computer (charge it first if it is low).
2. Make sure the computer's **Bluetooth radio is on** (Settings → Bluetooth & devices).
3. Open the app → **Devices** → **Scan BLE Printers**.
4. Click your printer (name should contain `SC03h`, `iprint`, `gb01`, `walkprint`, etc.) → the connection popup walks through BLE link → service discovery → notify subscription → done.
5. Run **Test Page** to verify density, alignment, and paper feed.

> No OS-level pairing is required — the app connects directly over GATT. If Windows has previously paired the printer, remove it first (Settings → Bluetooth → remove device) to avoid interference.

### 5. Verify the installation (optional)

```bash
python -m unittest discover -s tests -q
```

All 30 tests must pass (protocol packet/CRC, image pipeline, block rendering, templates, REST API).

### 6. Installation troubleshooting

| Symptom | Fix |
| :--- | :--- |
| `pip install` fails on `bleak` / `Pillow` | Upgrade pip (`python -m pip install --upgrade pip`), then retry |
| Server won't start — "port 8000 in use" | Close the other server, or start on a different port: `python -m uvicorn backend.main:app --port 8001` |
| Scan finds nothing | Bluetooth radio off → enable it; printer off/low battery → charge and power on; click Scan again |
| Connect times out after 20 s | Printer too far away; radio interference; reboot the printer, then retry |
| Linux: `Could not initialize Bluetooth` | Install BlueZ (`libbluetooth-dev`), restart the `bluetooth` service |
| Fonts render as boxes | Windows fonts are used by default (`C:/Windows/Fonts`); on Linux install `ttf-mscorefonts` or `fonts-dejavu` |
| Prints look faint / too dark | Settings → **Print Density** (energy scales from the 17500 baseline); **Tear-bar Feed** adjusts the trailing feed |

---

## API Overview

| Endpoint | Description |
| :--- | :--- |
| `GET /api/printers` | Scan for BLE printers |
| `POST /api/printers/connect` | Connect (body: `printer_id`, `connection_type`, `address`, `protocol`) |
| `POST /api/printers/disconnect` | Disconnect |
| `GET /api/printers/status` | Status incl. battery, paper, `device_info` |
| `POST /api/printers/test` | Print diagnostic page |
| `POST /api/print` | Submit a job (blocks, copies, feed) |
| `GET /api/print/jobs/{job_id}` | Job status |
| `GET /api/print/queue` | Active + queued jobs |
| `POST /api/print/preview` | Render blocks → base64 PNG |
| `POST /api/print/export?fmt=png\|pdf` | Download rendered output |
| `POST /api/print/cancel` | Cancel job(s) |
| `POST /api/print/csv` | CSV → barcode labels |
| `POST /api/images/process` | Image → thermal 1-bit |
| `GET/POST /api/settings` | App settings (`printer.tear_bar_feed_dots`, `density`, …) |
| `GET /api/templates` | Built-in + saved templates |
| `GET /api/history`, `/api/history/stats` | Print history + statistics |
| `GET /api/documents` | Saved documents |
| `GET /api/events` | **SSE** — job + printer events |
| `GET /api/debug/last-payload` | Parsed last job packets with CRC status |
| `GET /api/debug/trace` | Recent wire activity (TX/RX hex) |

---

## Printing with the iPrint / SC03h protocol

- Packet: `51 78 <op> 00 <len16le> <payload> <crc8(payload)> FF`
- CRC-8/ATM (poly `0x07`), computed over the payload only
- Job sequence: `0xA3 [0x00]` wake → `0xA4 [0x33]` quality → `0xAF` energy → `0xBE [0x00]` mode → `0xBD [0x23]` speed → rows → feed
- Rows: exactly 48 bytes (384 dots, MSB-first, `1` = black)
- Writes: 180-byte chunks, ≥ 10 ms apart (25 ms for > 20 KB), 600 ms drain between 4 KB bursts
- **Never** send `0xA6` (crashes SC03h), disconnect immediately, or skip the notify subscription

See [iPrint_SC03h_Protocol_Documentation.md](iPrint_SC03h_Protocol_Documentation.md) for the complete reference (opcodes, CRC table, test vectors, pitfalls).

---

## Settings file (`data/settings.json`)

```json
{
  "printer": {
    "paper_width_mm": 58,
    "printable_width_px": 384,
    "margin_px": 8,
    "density": 8,
    "tear_bar_feed_dots": 130
  },
  "image": { "default_dither": "atkinson" },
  "app": { "theme": "dark", "debug_mode": false }
}
```

`tear_bar_feed_dots` controls the trailing feed of iPrint jobs (sent as `0xA1` chunks of ≤ 100 dots); `0` disables it.

---

## Testing

```bash
python -m unittest discover -s tests -q
```

30 tests cover the image pipeline, block rendering (incl. table/totals), protocol packet parsing + CRC validation, feed chunking, device-info parsing, SSE event flow, templates, and the REST API (via a persistent-loop ASGI client with an isolated `MPS_DATA_DIR`).

---

## Troubleshooting

| Symptom | Fix |
| :--- | :--- |
| Nothing prints, no response | Reconnect; the notify subscription is mandatory (§13.3) |
| Prints worked, now writes fail | Stale BLE socket after system restart — reconnect fresh; the watchdog now detects this proactively |
| Page tail missing | Long job: pacing is automatic (> 20 KB → 25 ms + bursts) |
| Garbled rows | 48-byte rows, MSB-first — use the Packet Inspector to check CRC |
| Faint/dark output | Adjust density in Settings (energy scales from 17500) |
| Job aborts on disconnect | Hold the connection ≥ 3 s after the last write (server keeps it open) |

See [Bluetooth_Incident_Report.md](Bluetooth_Incident_Report.md) for a real-world stale-socket incident and the fix that became the auto-reconnect + watchdog behavior.

---

## Repository notes

- Device addresses in the docs are sanitized placeholders (`AA:BB:CC:DD:EE:FF`) — configure your own printer's address.
- `data/` is machine-local runtime storage (settings, history, saved documents) and is gitignored; the folder is kept in the repo with a `.gitkeep` so the app can create its files on first run.
- The local checkout also contains a reference implementation of the protocol by the community (`data/gb01print`, credits: WerWolv & NaitLee) and ad-hoc hardware test scripts with a private printer address — these are intentionally not part of this public repository.

