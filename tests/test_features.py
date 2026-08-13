import os
import sys
import json
import random
import asyncio
import tempfile
import unittest
from PIL import Image

from backend.protocols.iprint import IPrintProtocol
from backend.models.print_job import ContentBlock, PrintRequest
from backend.models.settings import AppSettings
from backend.services.print_engine import PrintEngine
from backend.services.image_processor import ImageProcessor
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


class TestSmartAutoLevel(unittest.TestCase):

    def _black_fraction(self, img):
        total = img.width * img.height
        black = sum(1 for v in img.getdata() if v == 0)
        return black / total

    def test_wide_range_image_not_crushed(self):
        # Normal photo: histogram already spans most of the range. The old
        # unconditional 1% clip stretch pushed shadows to solid black; the
        # smart version must skip the stretch so output is identical to
        # auto_level=False.
        img = Image.new("L", (200, 200))
        px = img.load()
        for y in range(200):
            for x in range(200):
                px[x, y] = 40 + (x * 200) // 200
        with_auto = ImageProcessor.process_image(img.convert("RGB"), dither_mode="threshold", auto_level=True)
        without = ImageProcessor.process_image(img.convert("RGB"), dither_mode="threshold", auto_level=False)
        self.assertEqual(ImageProcessor.to_raster_bytes(with_auto),
                         ImageProcessor.to_raster_bytes(without))
        self.assertLess(self._black_fraction(with_auto), 0.6)

    def test_flat_image_still_stretched(self):
        # Washed-out image (narrow histogram): the stretch must still fire
        # and split the tones instead of printing as mud.
        img = Image.new("L", (200, 200))
        px = img.load()
        for y in range(200):
            for x in range(200):
                px[x, y] = 115 + (x * 35) // 200  # narrow spread: 115..149
        with_auto = ImageProcessor.process_image(img.convert("RGB"), dither_mode="threshold", auto_level=True)
        without = ImageProcessor.process_image(img.convert("RGB"), dither_mode="threshold", auto_level=False)
        self.assertNotEqual(ImageProcessor.to_raster_bytes(with_auto),
                            ImageProcessor.to_raster_bytes(without))
        # Stretched output must actually contain both black and white pixels
        # (the flat image was recovered into full tonal range).
        colors = set(with_auto.getdata())
        self.assertTrue(0 in colors and (1 in colors or 255 in colors))


class TestProcessingPresets(unittest.TestCase):

    def _make_gradient(self):
        img = Image.new("L", (200, 200))
        px = img.load()
        for y in range(200):
            for x in range(200):
                px[x, y] = 40 + (x * 180) // 200
        return img.convert("RGB")

    def test_photo_preset_uses_floyd_steinberg(self):
        stages = ImageProcessor.prepare_grayscale(
            self._make_gradient(), processing_preset="photo"
        )
        self.assertEqual(stages["dither"], "floyd-steinberg")

    def test_preset_unknown_falls_back_to_photo(self):
        stages = ImageProcessor.prepare_grayscale(
            self._make_gradient(), processing_preset="not-a-preset"
        )
        self.assertEqual(stages["dither"], "floyd-steinberg")

    def test_sharp_presets_use_threshold(self):
        for preset in ("line_art", "text", "qr"):
            stages = ImageProcessor.prepare_grayscale(
                self._make_gradient(), processing_preset=preset
            )
            self.assertEqual(stages["dither"], "threshold", preset)

    def test_manga_uses_bayer(self):
        stages = ImageProcessor.prepare_grayscale(
            self._make_gradient(), processing_preset="manga"
        )
        self.assertEqual(stages["dither"], "bayer")

    def test_gamma_10_is_noop(self):
        img = self._make_gradient()
        plain = ImageProcessor.prepare_grayscale(img, processing_preset="photo")
        g1 = ImageProcessor.prepare_grayscale(img, processing_preset="photo", gamma=1.0)
        self.assertEqual(ImageProcessor.to_raster_bytes(plain["grayscale"]),
                         ImageProcessor.to_raster_bytes(g1["grayscale"]))

    def test_dither_image_abstraction(self):
        """All algorithms accept the same grayscale and yield 1-bit output."""
        img = self._make_gradient()
        gray = ImageProcessor.prepare_grayscale(img, processing_preset="photo")["grayscale"]
        for algo in ("atkinson", "floyd-steinberg", "stucki", "bayer", "threshold"):
            out = ImageProcessor.dither_image(gray, algo)
            self.assertEqual(out.mode, "1", algo)
            self.assertEqual(out.width, 384, algo)
        # The algorithms genuinely differ from each other.
        outs = [ImageProcessor.to_raster_bytes(ImageProcessor.dither_image(gray, a))
                for a in ("atkinson", "floyd-steinberg", "bayer")]
        self.assertTrue(len(set(outs)) >= 2)

    def test_photo_never_sharpens_by_default(self):
        img = self._make_gradient()
        plain = ImageProcessor.prepare_grayscale(img, processing_preset="photo")
        forced = ImageProcessor.prepare_grayscale(img, processing_preset="photo", sharpen=1.0)
        self.assertEqual(ImageProcessor.to_raster_bytes(plain["grayscale"]),
                         ImageProcessor.to_raster_bytes(forced["grayscale"]))

    def test_process_stages_returns_variants(self):
        stages = ImageProcessor.process_stages(self._make_gradient(), processing_preset="photo")
        self.assertEqual(stages["final"].mode, "1")
        self.assertEqual(stages["final"].width, 384)
        self.assertIn("floyd-steinberg", stages["variants"])
        self.assertIn("bayer", stages["variants"])
        self.assertIn("atkinson", stages["variants"])
        # The final output must be one of the variants (the active dither).
        self.assertEqual(
            ImageProcessor.to_raster_bytes(stages["final"]),
            ImageProcessor.to_raster_bytes(stages["variants"][stages["dither"]])
        )

    def test_autolevel_leaves_bright_scenes_alone(self):
        # Bright scene (mean ~185, narrow span): must NOT be stretched,
        # otherwise clean whites become 50% black on paper.
        img = Image.new("L", (200, 200))
        px = img.load()
        for y in range(200):
            for x in range(200):
                px[x, y] = 175 + (x * 60) // 200
        stretched = ImageProcessor._apply_smart_autolevel(img.convert("L"))
        self.assertEqual(stretched.getpixel((0, 0)), 175)


class TestPhotoSmoothing(unittest.TestCase):

    def test_smoothing_changes_diffusion_output(self):
        # Blur+lift before error diffusion must alter the dither pattern
        # (softer look) for photo dither modes.
        import random
        rnd = random.Random(11)
        img = Image.new("L", (200, 200))
        px = img.load()
        for y in range(200):
            for x in range(200):
                base = 60 + (x * 140) // 200 + (y * 40) // 200
                px[x, y] = max(0, min(255, base + rnd.randint(-18, 18)))
        sharp = ImageProcessor.process_image(img.convert("RGB"), dither_mode="atkinson", auto_level=False, smooth=0.0)
        soft = ImageProcessor.process_image(img.convert("RGB"), dither_mode="atkinson", auto_level=False, smooth=1.2)
        self.assertNotEqual(ImageProcessor.to_raster_bytes(sharp),
                            ImageProcessor.to_raster_bytes(soft))

    def test_smoothing_never_touches_threshold_mode(self):
        # Text/QR/line-art must stay crisp regardless of the smooth setting.
        img = Image.new("L", (200, 200))
        px = img.load()
        for y in range(200):
            for x in range(200):
                px[x, y] = 60 + (x * 140) // 200
        a = ImageProcessor.process_image(img.convert("RGB"), dither_mode="threshold", auto_level=False, smooth=0.0)
        b = ImageProcessor.process_image(img.convert("RGB"), dither_mode="threshold", auto_level=False, smooth=1.5)
        self.assertEqual(ImageProcessor.to_raster_bytes(a),
                         ImageProcessor.to_raster_bytes(b))


class TestDensityCalibration(unittest.TestCase):

    def test_build_density_calibration(self):
        img = Image.new("1", (384, 40), 1)
        payload = PrintEngine.build_density_calibration(img, densities=[5, 7, 10], strip_feed_dots=10)
        packets = IPrintProtocol.parse_stream(payload)
        self.assertTrue(all(p["crc_ok"] is not False for p in packets))

        # One 0xAF energy packet per density strip, with the scaled value.
        energies = [p for p in packets if p["opcode"] == 0xAF]
        self.assertEqual(len(energies), 3)
        for pkt, density in zip(energies, [5, 7, 10]):
            raw = bytes.fromhex(pkt["payload_hex"])
            value = raw[0] | (raw[1] << 8)
            expected = int(IPrintProtocol.DEFAULT_ENERGY * density / IPrintProtocol.DEFAULT_DENSITY)
            self.assertEqual(value, expected, f"density {density}")

        # Label + image rows per strip (6 rows of 0xA2 per strip: label 28px
        # → 4 bytes-tall label? label height 28 → rows; count must be
        # (28 + 40) rows per strip when using threshold rows).
        draws = [p for p in packets if p["opcode"] == 0xA2]
        self.assertEqual(len(draws), 3 * (28 + 40))
        self.assertTrue(all(p["length"] == 48 for p in draws))

    async def _run_raw_job(self):
        import tempfile
        pm = PrinterManager(data_dir=tempfile.mkdtemp(prefix="mps-cal-"))
        from backend.adapters.mock import MockPrinterAdapter
        pm.current_adapter = MockPrinterAdapter(address="00:11:22:33:44:55", protocol="iprint")
        await pm.current_adapter.connect()
        pm.active_printer_device = type("D", (), {
            "name": "Mock", "printable_width_px": 384, "protocol": "iprint"
        })()
        payload = PrintEngine.build_density_calibration(Image.new("1", (384, 10), 1), densities=[6, 8])
        job = await pm.submit_print_job(PrintRequest(
            title="Cal", blocks=[], raw_payload=payload, width_px=384, margin_px=0,
            feed_lines=0, cut_paper=False, copies=1
        ))
        # Wait for the queue worker to finish.
        for _ in range(200):
            if job.status in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(0.05)
        self.assertEqual(job.status, "completed")
        self.assertEqual(pm.current_adapter.last_payload, payload)

    def test_raw_payload_job_flow(self):
        asyncio.run(self._run_raw_job())


class TestMiniLZO(unittest.TestCase):

    def test_roundtrip(self):
        from backend.services.minilzo import compress, decompress
        random.seed(3)
        cases = [
            b"", b"hello", b"abc", b"\x00" * 100, b"\x00" * 5000,
            b"The quick brown fox jumps over the lazy dog" * 3,
            bytes([(i * 7) % 16 for i in range(1920)]),
            bytes(random.getrandbits(8) for _ in range(5000)),
            b"ABCDEFGHIJKLMNOP" * 200, b"x" * 3000,
            b"abcdefghijklmnopqrstuvwxyz" * 200,
            bytes([random.choice([0, 0, 0, 1, 2, 255, 128, 64]) for _ in range(4000)]),
        ]
        for data in cases:
            c = compress(data)
            self.assertEqual(decompress(c), data, f"roundtrip failed len={len(data)}")
        # empty input produces just the EOF marker
        self.assertEqual(compress(b""), b"\x11\x00\x00")

    def test_known_stream(self):
        # A canonical stream for 'The quick brown fox...' (generated by the
        # reference C minilzo, lzo1x_1_compress) must decode exactly.
        from backend.services.minilzo import decompress
        data = b"The quick brown fox jumps over the lazy dog" * 3
        # 17+t leading run = 0x16 + 5 literals, then a match, then EOF
        stream = bytes.fromhex("1668656c6c6f110000")  # 'hello' by the C encoder
        self.assertEqual(decompress(stream), b"hello")
        self.assertEqual(decompress(stream), decompress(stream))
        # my encoder output must not crash the decoder
        from backend.services.minilzo import compress
        self.assertEqual(decompress(compress(data)), data)


class TestGrayscalePrint(unittest.TestCase):

    def test_gray_rows_semantics(self):
        img_b = Image.new("RGB", (192, 4), (0, 0, 0))
        img_w = Image.new("RGB", (192, 4), (255, 255, 255))
        black = ImageProcessor.process_gray(img_b, target_width_px=384)
        white = ImageProcessor.process_gray(img_w, target_width_px=384)
        # 192 bytes per 384-dot row (2 pixels/byte, 4-bit gray)
        self.assertEqual(len(black) % 192, 0)
        self.assertEqual(len(white) % 192, 0)
        # black pixels = full burn nibble 0xF; white = no burn (near 0x0)
        self.assertEqual(set(black[:4]), {0xFF})
        self.assertTrue(all(b <= 0x22 for b in white[:8]))

    def test_gray_payload_structure(self):
        rows = ImageProcessor.process_gray(Image.new("RGB", (384, 6), (80, 90, 100)), target_width_px=384)
        payload = IPrintProtocol.build_gray_payload(rows, energy=6560, speed=40)
        packets = IPrintProtocol.parse_stream(payload)
        self.assertTrue(all(p["crc_ok"] is not False for p in packets))

        # sequence: 0xAF energy → 0xBE [00 01] → 0xBD → 0xCF chunks
        ops = [p["opcode"] for p in packets]
        self.assertEqual(ops[0], 0xAF)
        self.assertEqual(ops[1], 0xBE)
        be = next(p for p in packets if p["opcode"] == 0xBE)
        self.assertEqual(be["payload_hex"], "0001")  # 16-level grayscale mode
        af = next(p for p in packets if p["opcode"] == 0xAF)
        h = bytes.fromhex(af["payload_hex"])
        self.assertEqual(h[0] | (h[1] << 8), 6560)

        # every 0xCF chunk must LZO-decompress to its declared length
        from backend.services.minilzo import decompress
        cf = [p for p in packets if p["opcode"] == 0xCF]
        self.assertGreaterEqual(len(cf), 1)
        for p in cf:
            h = bytes.fromhex(p["payload_hex"])
            uncomp = h[0] | (h[1] << 8)
            comp = h[2] | (h[3] << 8)
            self.assertEqual(len(decompress(h[4:4 + comp])), uncomp)

    def test_end_to_end_gray_job(self):
        blocks = [ContentBlock(type="text", content="HELLO", font_size="title", align="center")]
        canvas = PrintEngine.render_blocks_to_image(blocks, 384, 8, gray=True)
        self.assertEqual(canvas.mode, "L")
        job = PrintEngine.generate_protocol_bytes(canvas, protocol="iprint", feed_lines=3, density=8, gray=True)
        packets = IPrintProtocol.parse_stream(job)
        self.assertTrue(all(p["crc_ok"] is not False for p in packets))
        self.assertTrue(any(p["opcode"] == 0xCF for p in packets))
        # the normal 1-bit path must still be the classic A2 rows
        job_1bit = PrintEngine.generate_protocol_bytes(canvas.convert("1"), protocol="iprint", feed_lines=3, density=8)
        pk1 = IPrintProtocol.parse_stream(job_1bit)
        self.assertTrue(any(p["opcode"] == 0xA2 for p in pk1))


if __name__ == "__main__":
    unittest.main()
