import os
import io
import base64
import unittest
from PIL import Image

from backend.models.print_job import ContentBlock, PrintRequest, ImageProcessRequest
from backend.services.image_processor import ImageProcessor
from backend.services.print_engine import PrintEngine
from backend.services.template_manager import TemplateManager
from backend.services.printer_manager import PrinterManager
from backend.protocols.escpos import ESCPOSProtocol
from backend.protocols.tspl import TSPLProtocol


class TestMiniPrintStudio(unittest.TestCase):

    def setUp(self):
        # Create a small test PIL image
        img = Image.new("RGB", (100, 100), color=(128, 64, 200))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        self.test_b64_img = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('utf-8')}"

    def test_image_processor_pipeline(self):
        img = ImageProcessor.load_image(self.test_b64_img)
        self.assertEqual(img.size, (100, 100))

        # Test Floyd-Steinberg dithering
        processed_fs = ImageProcessor.process_image(
            image=img,
            target_width_px=384,
            dither_mode="floyd-steinberg",
            brightness=1.1,
            contrast=1.2
        )
        self.assertEqual(processed_fs.width, 384)
        self.assertEqual(processed_fs.mode, "1")

        # Test Bayer dithering
        processed_bayer = ImageProcessor.process_image(
            image=img,
            target_width_px=384,
            dither_mode="bayer"
        )
        self.assertEqual(processed_bayer.width, 384)
        self.assertEqual(processed_bayer.mode, "1")

        # Test Thresholding
        processed_thresh = ImageProcessor.process_image(
            image=img,
            target_width_px=384,
            dither_mode="threshold"
        )
        self.assertEqual(processed_thresh.width, 384)
        self.assertEqual(processed_thresh.mode, "1")

        # Raster bytes conversion
        raster_data = ImageProcessor.to_raster_bytes(processed_fs)
        self.assertTrue(len(raster_data) > 0)
        print("[OK] ImageProcessor tests passed.")

    def test_print_engine_blocks(self):
        blocks = [
            ContentBlock(type="text", content="Test Header", font_size="large", bold=True, align="center"),
            ContentBlock(type="line", line_style="solid"),
            ContentBlock(type="qr", qr_payload="https://miniprint.studio", qr_size=4, align="center"),
            ContentBlock(type="barcode", barcode_payload="TEST12345", barcode_type="code128", align="center"),
            ContentBlock(type="space", space_height=10)
        ]

        rendered_canvas = PrintEngine.render_blocks_to_image(blocks, target_width_px=384, margin_px=8)
        self.assertEqual(rendered_canvas.width, 384)
        self.assertTrue(rendered_canvas.height > 100)

        # ESC/POS byte generation
        esc_bytes = PrintEngine.generate_protocol_bytes(rendered_canvas, protocol="escpos")
        self.assertTrue(len(esc_bytes) > 0)
        self.assertTrue(esc_bytes.startswith(ESCPOSProtocol.INIT))

        # TSPL byte generation
        tspl_bytes = PrintEngine.generate_protocol_bytes(rendered_canvas, protocol="tspl")
        self.assertTrue(len(tspl_bytes) > 0)
        print("[OK] PrintEngine tests passed.")

    def test_template_manager(self):
        manager = TemplateManager(templates_dir="data/templates")
        templates = manager.get_all_templates()
        self.assertTrue(len(templates) >= 6)
        
        simple_note = manager.get_template("simple_note")
        self.assertIsNotNone(simple_note)
        self.assertEqual(simple_note.name, "Simple Note")
        print("[OK] TemplateManager tests passed.")

    async def async_test_printer_manager_status(self):
        pm = PrinterManager(data_dir="data")
        status = pm.get_status()
        self.assertFalse(status.connected)
        self.assertIsNone(status.current_printer)

        # Test job submission raises ConnectionError when not connected
        req = PrintRequest(
            title="Unit Test Print Job",
            blocks=[
                ContentBlock(type="text", content="Hello Thermal Printer!", font_size="normal")
            ]
        )
        with self.assertRaises(ConnectionError):
            await pm.submit_print_job(req)
            
        print("[OK] PrinterManager async tests passed.")

    def test_printer_manager_wrapper(self):
        import asyncio
        asyncio.run(self.async_test_printer_manager_status())


if __name__ == "__main__":
    unittest.main()
