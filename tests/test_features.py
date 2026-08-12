import os
import sys
import json
import asyncio
import tempfile
import unittest
from PIL import Image

from backend.protocols.iprint import IPrintProtocol
from backend.models.print_job import ContentBlock, PrintRequest
from backend.models.settings import AppSettings
from backend.services.print_engine import PrintEngine
from backend.services.template_manager import TemplateManager
from backend.services.printer_manager import PrinterManager
from backend.adapters.ble import BLEPrinterAdapter


class TestParseStream(unittest.TestCase):

    def test_parse_real_job(self):
        img = Image.new("1", (384, 5), 1)
        job = IPrintProtocol.generate_payload(img, feed_lines=10, density=8)
        packets = IPrintProtocol.parse_stream(job)
        self.assertEqual(len(packets), 11)  # wake + 4 init + 5 rows + 1 feed
        self.assertEqual(packets[0]["opcode_name"], "Get Device State")
        self.assertEqual(packets[0]["opcode"], 0xA3)
        self.assertTrue(all(p["crc_ok"] is not False for p in packets))
        draw_rows = [p for p in packets if p["opcode"] == 0xA2]
        self.assertEqual(len(draw_rows), 5)
        for p in draw_rows:
            self.assertEqual(p["length"], 48)
            self.assertTrue(p["crc_ok"])

    def test_garbage_and_trailing(self):
        job = IPrintProtocol.generate_payload(Image.new("1", (384, 2), 1), feed_lines=0, density=8)
        stream = b"\xde\xad\xbe\xef" + job + b"\x01\x02"
        packets = IPrintProtocol.parse_stream(stream)
        self.assertEqual(packets[0]["opcode_name"], "garbage")
        self.assertIsNone(packets[0]["opcode"])
        self.assertEqual(packets[-1]["opcode_name"], "trailing bytes")

    def test_crc_flagged(self):
        img = Image.new("1", (384, 2), 1)
        job = bytearray(IPrintProtocol.generate_payload(img, feed_lines=0, density=8))
        # Flip a payload byte inside the first 0xA2 packet
        for i in range(6, len(job) - 2):
            if job[i] == 0x51 and job[i + 1] == 0x78 and job[i + 2] == 0xA2:
                job[i + 8] ^= 0xFF
                break
        packets = IPrintProtocol.parse_stream(bytes(job))
        bad = [p for p in packets if p["crc_ok"] is False]
        self.assertEqual(len(bad), 1)


class TestDeviceInfoParse(unittest.TestCase):

    def test_text_payload(self):
        info = BLEPrinterAdapter.parse_device_info_payload(b"SC03h-RevA\r\nFW 2.1.4")
        self.assertEqual(info["model"], "SC03h-RevA")
        self.assertEqual(info["firmware"], "FW 2.1.4")

    def test_binary_payload(self):
        info = BLEPrinterAdapter.parse_device_info_payload(b"\x01\x02\xff\x00")
        self.assertIn("raw", info)
        self.assertEqual(info["raw"], "0102ff00")


class TestTableAndTotals(unittest.TestCase):

    def setUp(self):
        self.blocks = [
            ContentBlock(type="text", content="PIXEL BAZAAR", font_size="title", align="center"),
            ContentBlock(type="table",
                         table_headers=["Item", "Qty", "Price"],
                         table_rows=[["Pixel Sticker Pack", "2", "$4.50"],
                                     ["Thermal Paper Roll", "1", "$6.99"]]),
            ContentBlock(type="totals",
                         totals_lines=[{"label": "Subtotal", "value": "$11.49", "dotted": True, "bold": False},
                                       {"label": "TOTAL", "value": "$11.49", "dotted": True, "bold": True}]),
        ]

    def test_render_and_protocol(self):
        rendered = PrintEngine.render_blocks_to_image(self.blocks, 384, 8)
        self.assertEqual(rendered.width, 384)
        self.assertGreater(rendered.height, 50)

        payload = PrintEngine.generate_protocol_bytes(rendered, protocol="iprint", feed_lines=3, density=8, feed_dots=200)
        packets = IPrintProtocol.parse_stream(payload)
        self.assertTrue(all(p["crc_ok"] is not False for p in packets))
        feeds = [p for p in packets if p["opcode"] == 0xA1]
        feed_dots = []
        for p in feeds:
            h = bytes.fromhex(p["payload_hex"])
            feed_dots.append(h[0] | (h[1] << 8) if len(h) >= 2 else h[0])
        # 200 dots must be chunked into ≤100-dot 0xA1 packets (doc 6.2)
        self.assertEqual(sum(feed_dots), 200)
        self.assertTrue(all(d <= 100 for d in feed_dots))

    def test_feed_dots_zero(self):
        rendered = PrintEngine.render_blocks_to_image(self.blocks, 384, 8)
        payload = PrintEngine.generate_protocol_bytes(rendered, protocol="iprint", feed_lines=0, density=8)
        packets = IPrintProtocol.parse_stream(payload)
        self.assertFalse(any(p["opcode"] == 0xA1 for p in packets))


class TestSettingsAndTemplate(unittest.TestCase):

    def test_feed_dots_default(self):
        s = AppSettings()
        self.assertEqual(s.printer.tear_bar_feed_dots, 130)

    def test_structured_receipt_template(self):
        manager = TemplateManager(templates_dir="data/templates")
        tpl = manager.get_template("structured_receipt")
        self.assertIsNotNone(tpl)
        types = [b.type for b in tpl.blocks]
        self.assertIn("table", types)
        self.assertIn("totals", types)


class TestEventStream(unittest.TestCase):

    def test_broadcast_flow(self):
        async def run():
            pm = PrinterManager(data_dir=tempfile.mkdtemp(prefix="mps-ev-"))
            agen = pm.event_stream()
            await agen.__anext__()  # subscribe
            pm._broadcast({"type": "job", "job_id": "j1", "status": "printing", "title": "T"})
            chunk = await agen.__anext__()
            self.assertIn("j1", chunk)
            self.assertIn("printing", chunk)
            await agen.aclose()
            self.assertEqual(len(pm._subscribers), 0)
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
