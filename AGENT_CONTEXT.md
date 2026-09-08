# Mini Print Studio — Agent Context
Last updated: 2026-09-08. Status: all 81 tests green; queue/CSVs/fonts/SSE hardened; BLE scan `cls`→`self` fixed; dither UI simplified to Photo/Text.

## What
Local-first FastAPI + vanilla-JS app driving 58mm BLE thermal printers (SC03h iPrint + clones). No cloud/DB; JSON files in `data/`.

## Stack
Python 3.10–3.12, FastAPI/uvicorn/pydantic, Pillow/qrcode/python-barcode, Bleak, httpx (tests). Frontend: vanilla JS (`app.js` 1.7k lines, `editor.js`), no framework.

## Layout
- `backend/main.py` — app, localhost CORS, 9 routers, lifespan restores `queue.json` + auto-reconnect. `--reload`/`MPS_DEV=1` for dev reload.
- `backend/api/` — printers, print_jobs (incl. `/csv`), images, settings, templates, history (incl. `/export`), documents, events (SSE), debug.
- `backend/services/` — `printer_manager.py` (queue+SSE+watchdog, persists `queue.json`), `print_engine.py` (blocks→384px, divider/thick/wave styles, Linux font fallbacks, gray-parity paste), `image_processor.py` (`_pixel_values()` Pillow-14-safe), `template_manager.py`, `minilzo.py`, `document_manager.py`.
- `backend/protocols/iprint.py` — `51 78…FF`, CRC-8/0x07, `energy_for_density()`, `feed_chunks()`, OPCODE_NAMES incl. 0xCF. Never send 0xA6.
- `backend/adapters/` — ble, bluetooth_classic, mock, base.
- `frontend/js/app.js` — SSE-healthy flag (30s fallback poll, was 5s), `refreshIcons()`.
- `tools/` — `analyze_btsnoop.py`, `validate_image_quality.py`.

## Run/Test
- `python -m venv venv; pip install -r requirements.txt; python -m backend.main`
- `python -m unittest discover -s tests -q` (81 tests). `MPS_DATA_DIR` isolates data in tests.
- Linux BLE needs bluez; fonts fall back to DejaVu/Liberation/Noto.

## Conventions
- 384-dot rows, 48B MSB-first; 180B chunks, 10ms (25ms >20KB), 4KB bursts + 600ms drain.
- Blocks: text,image,qr,barcode,line|divider|separator|hr,space,table,totals. `line_style`: solid,thick|divider,dashed,dotted,double,wave.
- Dither UI is 2 modes: Photo (`hybrid`: Bayer×Threshold blend, s=0.5) + Text (`threshold`); `normalizeDither()` in `api.js` maps legacy floyd/atkinson/stucki→hybrid, bayer→threshold. Backend accepts all 6; `photo` preset uses hybrid.
- Photo mode auto-checks True Grayscale (`PreviewManager.syncGrayscaleToggle()`); Text/Default uncheck it. Toggle stays manually overridable; `getPrintRequest()` reads it live.
- CSV `/api/print/csv`: index cols or `*_header` names, `barcode_type`, `max_labels` (200).
- History: `GET /api/history/export?fmt=csv`.

## Next
- Split `app.js` monolith; batch-basket server sync; ESC/POS+TSPL hardware tests; template_manager refactor.
