# Product Requirements Document

**Product:** Mini Thermal Printer Studio
**Version:** 0.1 — Draft
**Platform:** Local Web Application / Desktop Browser
**Frontend:** HTML5, CSS3, JavaScript
**Backend:** Python + FastAPI
**Primary Hardware:** Bluetooth Mini Thermal Printer, approximately 50–58 mm print width
**Design Direction:** Professional, minimal, fast, utility-focused

---

## 1. Product Overview

Mini Thermal Printer Studio is a lightweight local-first web application for controlling a Bluetooth mini thermal printer from a computer.

The application will provide a clean browser-based interface for creating, previewing, processing, and printing content such as text, images, QR codes, labels, notes, receipts, diagrams, and small documents.

The Python FastAPI backend will act as the hardware integration layer between the browser and the thermal printer.

The product should require no cloud service for core printing functionality.

---

## 2. Product Goals

### Primary Goals

* Provide a simple interface for printing to the user's Bluetooth thermal printer.
* Support text and image printing.
* Automatically optimize content for thermal paper.
* Provide an accurate print preview.
* Abstract Bluetooth and printer communication behind a stable backend API.
* Support different printer protocols where practical.
* Keep the application lightweight enough to run on low-spec computers.
* Make printing possible without uploading personal content to a remote server.

### Secondary Goals

* Provide reusable print templates.
* Support QR codes and barcodes.
* Offer thermal-image processing controls.
* Maintain printer configuration locally.
* Make the architecture extensible for future printers and features.

---

# 3. Target Users

### Primary User

A user who owns a small Bluetooth thermal printer and wants more control than the manufacturer's basic mobile application provides.

### Typical Use Cases

* Printing short notes
* Printing study material
* Printing labels
* Printing QR codes
* Printing small receipts
* Printing images
* Printing manga or line-art panels
* Printing diagrams
* Printing checklists
* Creating small decorative prints
* Testing thermal-paper quality
* Experimenting with custom thermal graphics

---

# 4. Core Product Concept

The application consists of two major layers:

```text
┌──────────────────────────────────────────┐
│              WEB INTERFACE               │
│                                          │
│ HTML + CSS + JavaScript                  │
│ Editor • Preview • Templates • Settings  │
└───────────────────┬──────────────────────┘
                    │ HTTP / JSON
                    ▼
┌──────────────────────────────────────────┐
│             FASTAPI BACKEND              │
│                                          │
│ Print Engine • Image Processor           │
│ Printer Manager • Bluetooth Adapter      │
└───────────────────┬──────────────────────┘
                    │
                    ▼
             Bluetooth Printer
```

The browser handles the user experience.

FastAPI handles hardware communication, print preparation, image conversion, and printer-specific operations.

---

# 5. Functional Requirements

## 5.1 Dashboard

The main dashboard should provide an immediate overview of the printer.

Display:

* Printer connection status
* Printer name
* Connection type
* Paper width
* Current print job
* Quick print button
* Recent print activity
* Printer settings shortcut

Example:

```text
MINI PRINT STUDIO

Printer
● Connected
Mini Printer 01
58 mm

[ New Print ]

Recent
────────────────────────
Study Note        10:21
QR Label          10:17
Image             09:52
```

---

# 5.2 Print Editor

The editor will be the primary workspace.

### Supported Content

* Plain text
* Rich text formatting
* Images
* QR codes
* Barcodes
* Horizontal separators
* Simple shapes
* Blank spacing
* Custom layouts

### Text Controls

* Font size
* Bold
* Italic
* Alignment
* Line spacing
* Character spacing
* Monospace option
* Invert
* Centered text
* Width constraints

The first implementation should prioritize reliable thermal output over advanced typography.

---

# 5.3 Image Printing

Users should be able to upload:

* PNG
* JPG/JPEG
* WEBP

The application should process the image before printing.

### Processing Pipeline

```text
Original Image
      ↓
Resize
      ↓
Crop / Fit
      ↓
Grayscale
      ↓
Contrast
      ↓
Brightness
      ↓
Sharpen
      ↓
Dithering
      ↓
1-bit Thermal Image
      ↓
Printer Data
```

### Dithering Modes

Initial implementation:

* Threshold
* Floyd–Steinberg
* Ordered/Bayer

The user should be able to compare the processed image in the preview before printing.

---

# 5.4 Print Width Management

The application must support printer-specific printable widths.

Example profiles:

```text
58 mm Printer
Typical printable width: configurable

80 mm Printer
Typical printable width: configurable
```

The exact pixel width should be configurable because different printers expose different effective resolutions.

Example setting:

```text
Print Width
[ 384 px ]

Paper Width
[ 58 mm ]

Margin
[ 8 px ]
```

The system must never assume that every 58 mm printer uses the same pixel width.

---

# 5.5 Print Preview

The preview should visually represent the expected thermal output.

The preview should:

* Show paper proportions
* Show printable boundaries
* Display margins
* Render grayscale/1-bit output
* Support zoom
* Show image scaling
* Show page height
* Update in real time

Primary actions:

```text
[ Edit ]   [ Preview ]   [ Print ]
```

---

# 5.6 Bluetooth Printer Management

The backend will provide printer discovery and connection APIs.

Required operations:

```text
Discover printers
Connect
Disconnect
Get status
Send print data
Cancel job
Reconnect
```

Example API concept:

```text
GET  /api/printers
POST /api/printers/connect
POST /api/printers/disconnect
GET  /api/printers/status
POST /api/print
POST /api/print/test
POST /api/print/cancel
```

---

# 5.7 Printer Protocol Abstraction

Because inexpensive thermal printers may use different protocols, the backend must not tightly couple the application to one printer implementation.

Use an abstraction similar to:

```text
PrinterAdapter
    ├── BLEAdapter
    ├── BluetoothClassicAdapter
    └── FutureAdapter
```

And:

```text
PrinterProtocol
    ├── ESC/POS
    ├── TSPL
    └── Custom
```

The application should identify or manually configure the appropriate adapter/protocol.

The goal is to allow additional printer models to be supported without redesigning the frontend.

---

# 5.8 Thermal Command Engine

The backend should convert processed content into printer-compatible data.

The engine should support operations such as:

```text
Initialize
Set alignment
Set text size
Set bold
Print text
Print bitmap
Print QR code
Feed paper
Cut paper, where supported
Finalize
```

For printers using ESC/POS, the backend should generate the appropriate byte sequences.

Protocol-specific functionality must remain isolated from the general application logic.

---

# 5.9 QR Code Printing

Users should be able to enter:

* URL
* Plain text
* Wi-Fi information
* Contact information
* Custom QR payload

Controls:

* QR size
* Error correction
* Alignment
* Quiet zone

Preview should render exactly as it will be converted for thermal output.

---

# 5.10 Templates

The application should provide reusable templates.

Initial templates:

* Simple Note
* Study Note
* Checklist
* Label
* QR Label
* Receipt
* Image Print
* Title + Body

Users should be able to duplicate and customize templates.

---

# 5.11 Print History

Maintain local print history.

Each record should include:

* Print date/time
* Document title
* Content type
* Printer name
* Print dimensions
* Status

Example:

```text
Today

Study Note        Printed
QR Label          Printed
Manga Panel       Failed
```

No cloud storage should be required.

---

# 5.12 Test Print

The application should provide a dedicated test-print function.

The test page should include:

```text
MINI PRINT STUDIO

ABCDEFGHIJKLMNOPQRSTUVWXYZ
abcdefghijklmnopqrstuvwxyz
0123456789

████████████████████
░░░░░░░░░░░░░░░░░░░░

Alignment Test
Left | Center | Right

Image Test
QR Test
```

This helps diagnose paper quality, density, alignment, and printer communication.

---

# 6. User Interface Requirements

## Design Language

The UI should be:

* Minimal
* Professional
* Clean
* Compact
* Responsive
* Keyboard-friendly
* Fast
* Low visual clutter

Avoid:

* Excessive gradients
* Large decorative elements
* Unnecessary animations
* Oversized navigation
* Heavy dashboards

---

## Recommended Layout

```text
┌──────────────────────────────────────────────────┐
│ MINI PRINT STUDIO                 ● Connected    │
├──────────────┬───────────────────┬───────────────┤
│              │                   │               │
│ Workspace    │     Editor        │   Preview     │
│              │                   │               │
│ New          │   Content        │   Thermal      │
│ Templates    │   Controls       │   Preview      │
│ History      │                   │               │
│ Settings     │                   │               │
│              │                   │               │
├──────────────┴───────────────────┴───────────────┤
│                    [ PRINT ]                      │
└──────────────────────────────────────────────────┘
```

On smaller displays, the three-column layout should collapse into tabs or stacked panels.

---

# 7. Frontend Requirements

## Technology

Use:

* HTML5
* CSS3
* Vanilla JavaScript initially

A frontend framework should not be required for version 1.

### Frontend Responsibilities

* UI rendering
* Editor state
* Preview rendering
* User interactions
* Local settings
* API communication
* Upload handling
* Print-job submission

The frontend should communicate with FastAPI using REST/JSON.

---

# 8. Backend Requirements

## Technology

**Python 3.x + FastAPI**

Recommended supporting libraries may include:

```text
FastAPI
Uvicorn
Pillow
Bleak
qrcode
python-barcode
Pydantic
```

Exact Bluetooth libraries depend on the printer's communication method.

---

## Backend Modules

```text
backend/
│
├── main.py
│
├── api/
│   ├── printers.py
│   ├── print_jobs.py
│   ├── images.py
│   └── settings.py
│
├── services/
│   ├── printer_manager.py
│   ├── print_engine.py
│   ├── image_processor.py
│   └── template_manager.py
│
├── adapters/
│   ├── base.py
│   ├── ble.py
│   └── bluetooth_classic.py
│
├── protocols/
│   ├── escpos.py
│   └── tspl.py
│
└── models/
    ├── printer.py
    ├── print_job.py
    └── settings.py
```

---

# 9. API Design

### Printer Discovery

```http
GET /api/printers
```

Response:

```json
{
  "printers": [
    {
      "id": "printer-01",
      "name": "Mini Printer",
      "connection": "bluetooth",
      "status": "available"
    }
  ]
}
```

### Connect

```http
POST /api/printers/connect
```

### Printer Status

```http
GET /api/printers/status
```

### Print

```http
POST /api/print
```

Example request:

```json
{
  "type": "image",
  "title": "Test Image",
  "width": 384,
  "alignment": "center",
  "dither": "floyd-steinberg"
}
```

The actual binary image data may be transferred separately using `multipart/form-data`.

### Test Print

```http
POST /api/printers/test
```

---

# 10. Local-First Architecture

Core functionality should work completely offline.

```text
Browser
   │
   │ localhost
   ▼
FastAPI
   │
   ├── Local processing
   ├── Local settings
   ├── Local history
   │
   ▼
Bluetooth
   │
   ▼
Printer
```

No user content should be sent to a third-party server for normal printing.

Internet access should not be required after installation.

---

# 11. Storage

Version 1 should avoid requiring a database.

Use local files or lightweight JSON storage for:

* Settings
* Printer profiles
* Templates
* Print history

Example:

```text
data/
├── settings.json
├── printers.json
├── templates/
└── history.json
```

A database can be introduced later if the application becomes substantially larger.

---

# 12. Security Requirements

Because the FastAPI service controls local hardware, the application should be designed conservatively.

### Requirements

* Bind the backend to localhost by default.
* Do not expose the printer API publicly.
* Restrict CORS to the local application origin.
* Validate uploaded files.
* Limit maximum image dimensions.
* Validate print-job payloads.
* Sanitize filenames.
* Avoid executing user-supplied commands.
* Do not transmit print content externally.

Default:

```text
127.0.0.1
```

rather than:

```text
0.0.0.0
```

---

# 13. Performance Requirements

The application should run comfortably on low-spec hardware.

Targets:

* Fast startup
* Minimal RAM usage
* No mandatory database server
* No cloud dependency
* Efficient image processing
* Printer communication should happen asynchronously where possible
* UI should remain responsive during printing

Large images should be resized before intensive image processing.

---

# 14. Error Handling

The user should receive clear, human-readable messages.

Examples:

```text
Printer not found.

Bluetooth connection failed.

Printer disconnected during printing.

Image is larger than the supported limit.

Unsupported printer protocol.

Print job failed.
```

Avoid exposing raw Python stack traces to the user.

Detailed errors should be available in a developer/debug log.

---

# 15. Print Queue

The backend should use a print-job queue rather than sending multiple jobs simultaneously.

Example:

```text
QUEUED
   ↓
PREPARING
   ↓
CONNECTING
   ↓
PRINTING
   ↓
COMPLETED
```

Failure:

```text
PRINTING
   ↓
FAILED
```

The UI should display progress.

---

# 16. Settings

### Printer

* Printer name
* Connection type
* Protocol
* Printable width
* Density
* Speed
* Default alignment
* Default margin
* Auto-feed amount

### Image

* Default brightness
* Default contrast
* Default dithering
* Default sharpening
* Default scaling mode

### Application

* Theme
* Default template
* Print history retention
* Debug mode

---

# 17. MVP Scope

Version 1.0 should focus on reliable basic printing.

### MVP Features

* Dashboard
* Bluetooth printer discovery
* Connect/disconnect
* Text editor
* Image upload
* Image preprocessing
* Thermal preview
* Print
* Test print
* Printer settings
* Error handling
* Local configuration

### Post-MVP

* QR codes
* Barcodes
* Templates
* Print history
* Advanced dithering
* Multiple printer profiles
* Batch printing
* Receipt designer
* Label designer
* Custom print canvas

---

# 18. Development Phases

## Phase 1 — Hardware Investigation

Determine:

* Bluetooth type
* Device services
* Characteristics or SPP channel
* Printer protocol
* Command format
* Printable resolution
* Maximum print width

**Deliverable:** Working Python proof-of-concept that sends a test print.

---

## Phase 2 — FastAPI Hardware Layer

Implement:

* Printer discovery
* Connection
* Disconnect
* Status
* Raw print command
* Test print

**Deliverable:** REST API capable of controlling the printer.

---

## Phase 3 — Image Processing

Implement:

* Resize
* Crop
* Grayscale
* Contrast
* Threshold
* Dithering
* Bitmap conversion

**Deliverable:** Input image → correct thermal bitmap.

---

## Phase 4 — Web Interface

Build:

* Dashboard
* Editor
* Preview
* Printer panel
* Settings
* Print workflow

**Deliverable:** Complete local web application.

---

## Phase 5 — Templates and Utilities

Add:

* QR
* Barcode
* Notes
* Labels
* Receipts
* Study templates

---

## Phase 6 — Packaging

Package the application as a desktop application or local launcher.

Potential final structure:

```text
Mini Printer Studio
├── frontend
├── FastAPI backend
├── printer drivers
├── templates
└── local data
```

---

# 19. Acceptance Criteria

The MVP is considered successful when:

1. The application starts locally without cloud services.
2. The printer can be discovered or manually configured.
3. The user can connect and disconnect the printer.
4. Text can be entered and printed.
5. Images can be uploaded and printed.
6. Images are automatically converted to a suitable thermal format.
7. The preview accurately represents the processed print.
8. Print failures are reported clearly.
9. The application works without requiring a large runtime stack.
10. Printer-specific communication remains isolated from the frontend.

---

# 20. Future Expansion

The architecture should leave room for:

```text
              MINI PRINT STUDIO
                     │
     ┌───────────────┼────────────────┐
     │               │                │
  Thermal         Label            Receipt
  Printing       Designer          Designer
     │               │                │
     └───────────────┼────────────────┘
                     │
               Printer Engine
                     │
        ┌────────────┼────────────┐
        │            │            │
       BLE       Bluetooth      USB
                  Classic
```

Future versions could support additional printer models without changing the core application.

---

# 21. Design Principles

The product should follow five principles:

**Fast** — The user should reach the print screen quickly.

**Minimal** — Every interface element should serve a clear purpose.

**Local** — Core printing should work without the internet.

**Reliable** — Hardware communication should be separated from UI logic.

**Extensible** — New printer models and protocols should be addable without rewriting the application.

---

# 22. Recommended Project Name

**Mini Print Studio**

Alternative names:

* Thermal Studio
* PrintPocket
* TinyPrint
* ThermoDesk
* Pocket Printer Studio

**Recommended:** Mini Print Studio

It describes the product clearly while leaving room for support of multiple thermal printers.
