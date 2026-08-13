import io
import base64
import logging
from typing import List, Tuple, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont, ImageOps
import qrcode
import barcode
from barcode.writer import ImageWriter

from backend.models.print_job import ContentBlock, PrintRequest
from backend.services.image_processor import ImageProcessor
from backend.protocols.escpos import ESCPOSProtocol
from backend.protocols.tspl import TSPLProtocol

logger = logging.getLogger("PrintEngine")


class PrintEngine:
    """
    Renders structured print layout blocks into a 1-bit thermal roll bitmap and protocol binary payloads.
    """

    @classmethod
    def render_blocks_to_image(
        cls,
        blocks: List[ContentBlock],
        target_width_px: int = 384,
        margin_px: int = 8,
        gray: bool = False
    ) -> Image.Image:
        """
        Composites all content blocks into a single vertical image.
        `gray=True` renders an 8-bit 'L' canvas (255 = white) instead of a
        1-bit canvas, for the printer's true 16-level grayscale mode — image
        blocks are NOT dithered in this path; the grayscale tone mapping
        happens once for the whole page at protocol generation time.
        """
        printable_width = target_width_px - (2 * margin_px)
        if printable_width <= 0:
            printable_width = target_width_px

        rendered_sub_images: List[Image.Image] = []

        for block in blocks:
            sub_img = cls._render_block(block, printable_width, gray=gray)
            if sub_img:
                rendered_sub_images.append(sub_img)

        if not rendered_sub_images:
            # Empty print - default 100px blank image
            canvas = Image.new("L" if gray else "1", (target_width_px, 100), 255 if gray else 1)
            return canvas

        # Calculate total height
        total_height = margin_px * 2 + sum(img.height for img in rendered_sub_images)
        canvas = Image.new("L" if gray else "1", (target_width_px, total_height), 255 if gray else 1)

        # Paste blocks sequentially
        current_y = margin_px
        for sub_img in rendered_sub_images:
            # Handle horizontal alignment within margins
            if sub_img.width < target_width_px:
                x_offset = margin_px
                if getattr(sub_img, "align", "center") == "center":
                    x_offset = max(0, (target_width_px - sub_img.width) // 2)
                elif getattr(sub_img, "align", "left") == "right":
                    x_offset = max(0, target_width_px - margin_px - sub_img.width)
            else:
                x_offset = 0

            canvas.paste(sub_img, (x_offset, current_y))
            current_y += sub_img.height

        return canvas

    @classmethod
    def _render_block(cls, block: ContentBlock, max_width_px: int, gray: bool = False) -> Optional[Image.Image]:
        b_type = block.type.lower()

        if b_type == "text":
            return cls._render_text_block(block, max_width_px)
        elif b_type == "image":
            return cls._render_image_block(block, max_width_px, gray=gray)
        elif b_type == "qr":
            return cls._render_qr_block(block, max_width_px)
        elif b_type == "barcode":
            return cls._render_barcode_block(block, max_width_px)
        elif b_type == "line":
            return cls._render_line_block(block, max_width_px)
        elif b_type == "space":
            height = block.space_height or 16
            img = Image.new("1", (max_width_px, height), 1)
            return img
        elif b_type == "table":
            return cls._render_table_block(block, max_width_px)
        elif b_type == "totals":
            return cls._render_totals_block(block, max_width_px)

        return None

    # Windows font name -> ttf variants
    FONT_FAMILIES = {
        "arial":     {"base": "arial",     "bold": "arialbd",     "italic": "ariali",     "mono": None},
        "calibri":   {"base": "calibri",   "bold": "calibrib",    "italic": "calibrii",   "mono": None},
        "times":     {"base": "times",     "bold": "timesbd",     "italic": "timesi",     "mono": None},
        "courier":   {"base": "cour",      "bold": "courbd",      "italic": "couri",      "mono": "cour"},
        "tahoma":    {"base": "tahoma",    "bold": "tahomabd",    "italic": None,         "mono": None},
        "verdana":   {"base": "verdana",   "bold": "verdanab",    "italic": "verdanai",   "mono": None},
        "georgia":   {"base": "georgia",   "bold": "georgiab",    "italic": "georgiai",   "mono": None},
        "comic":     {"base": "comic",     "bold": "comicbd",     "italic": "comici",     "mono": None},
        "impact":    {"base": "impact",    "bold": "impact",      "italic": None,         "mono": None},
        "consolas":  {"base": "consola",   "bold": "consolab",    "italic": "consolai",   "mono": "consola"},
    }

    @classmethod
    def get_font(cls, size_px: int, bold: bool = False, monospace: bool = False, italic: bool = False, family: str = "arial") -> Any:
        import os
        family = (family or "arial").lower()
        font_paths = []
        fam = cls.FONT_FAMILIES.get(family, cls.FONT_FAMILIES["arial"])

        if monospace and fam.get("mono"):
            base = fam["mono"]
        elif italic and fam.get("italic"):
            base = fam["italic"]
        elif bold and fam.get("bold"):
            base = fam["bold"]
        else:
            base = fam["base"]

        font_paths.append(f"C:/Windows/Fonts/{base}.ttf")
        font_paths.append(f"{base}.ttf")
        if monospace:
            font_paths.extend(["C:/Windows/Fonts/consola.ttf", "cour.ttf", "DejaVuSansMono.ttf"])
        elif italic:
            font_paths.extend(["C:/Windows/Fonts/ariali.ttf", "ariali.ttf", "DejaVuSans-Oblique.ttf"])
        elif bold:
            font_paths.extend(["C:/Windows/Fonts/arialbd.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"])
        else:
            font_paths.extend(["C:/Windows/Fonts/arial.ttf", "arial.ttf", "DejaVuSans.ttf"])

        for path in font_paths:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size_px)
                except Exception:
                    pass
        try:
            return ImageFont.truetype("arial.ttf", size_px)
        except Exception:
            return ImageFont.load_default()

    @classmethod
    def _measure_text(cls, draw, text: str, font, letter_spacing: int = 0) -> int:
        """Width of a string including inter-character spacing."""
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        if letter_spacing and len(text) > 1:
            width += letter_spacing * (len(text) - 1)
        return width

    @classmethod
    def _render_text_block(cls, block: ContentBlock, max_width_px: int) -> Image.Image:
        text = block.content or ""
        font_size_name = (block.font_size or "normal").lower()

        # Map font size
        font_size_px = 18
        if font_size_name == "small":
            font_size_px = 13
        elif font_size_name == "large":
            font_size_px = 26
        elif font_size_name == "title":
            font_size_px = 36
        if block.custom_font_size:
            font_size_px = max(6, min(72, int(block.custom_font_size)))

        line_spacing = max(0.6, float(block.line_spacing or 1.3))
        letter_spacing = max(0, int(block.letter_spacing or 0))

        font = cls.get_font(font_size_px, bold=block.bold or False, monospace=block.monospace or False, italic=block.italic or False, family=block.font_family or "arial")

        # Word wrap text using textbbox measurements
        temp_img = Image.new("1", (1, 1), 1)
        temp_draw = ImageDraw.Draw(temp_img)

        wrapped_lines = []
        for raw_line in text.split("\n"):
            if not raw_line:
                wrapped_lines.append("")
                continue
            words = raw_line.split(" ")
            current_line = ""
            for word in words:
                test_line = f"{current_line} {word}".strip()
                w = cls._measure_text(temp_draw, test_line, font, letter_spacing)
                if w <= max_width_px or not current_line:
                    current_line = test_line
                else:
                    wrapped_lines.append(current_line)
                    current_line = word
            if current_line:
                wrapped_lines.append(current_line)

        line_height = int(font_size_px * line_spacing)
        total_height = max(line_height, len(wrapped_lines) * line_height + 6)

        img = Image.new("1", (max_width_px, total_height), 1) # 1 = White background
        draw = ImageDraw.Draw(img)

        y = 3
        for line in wrapped_lines:
            if not line:
                y += line_height
                continue

            line_w = cls._measure_text(draw, line, font, letter_spacing)

            # Calculate alignment offset
            if block.align == "center":
                x = max(0, (max_width_px - line_w) // 2)
            elif block.align == "right":
                x = max(0, max_width_px - line_w)
            else:
                x = 0

            # Draw text with inter-character spacing when requested
            if letter_spacing and len(line) > 1:
                cx = x
                for ch in line:
                    draw.text((cx, y), ch, fill=0, font=font)
                    ch_w = cls._measure_text(draw, ch, font, 0)
                    cx += ch_w + letter_spacing
            else:
                draw.text((x, y), line, fill=0, font=font, stroke_width=1 if block.bold else 0)

            if block.underline:
                draw.line([(x, y + line_height - 3), (x + line_w, y + line_height - 3)], fill=0, width=2)
            y += line_height

        if block.invert:
            img = ImageOps.invert(img.convert("L")).convert("1")

        setattr(img, "align", block.align or "left")
        return img

    @classmethod
    def _render_image_block(cls, block: ContentBlock, max_width_px: int, gray: bool = False) -> Optional[Image.Image]:
        if not block.image_data:
            return None
        try:
            raw_img = ImageProcessor.load_image(block.image_data)
            if gray:
                # Grayscale job: skip dithering entirely — the page-level
                # tone mapping + 16-level diffusion happen once at protocol
                # time so photos keep their full tonal range.
                processed_img = ImageProcessor.prepare_grayscale(
                    image=raw_img,
                    target_width_px=max_width_px,
                    scale_mode=block.scale_mode or "fit",
                    brightness=block.brightness,
                    contrast=block.contrast,
                    invert=block.invert or False,
                    processing_preset="photo"
                )["grayscale"].convert("L")
            else:
                processed_img = ImageProcessor.process_image(
                    image=raw_img,
                    target_width_px=max_width_px,
                    dither_mode=block.dither_mode,
                    brightness=block.brightness,
                    contrast=block.contrast,
                    sharpen=block.sharpen,
                    scale_mode=block.scale_mode or "fit",
                    invert=block.invert or False,
                    auto_level=block.auto_level,
                    smooth=block.smooth,
                    processing_preset=block.processing_preset or "photo",
                    gamma=block.gamma
                )
            setattr(processed_img, "align", block.align or "center")
            return processed_img
        except Exception as e:
            logger.error(f"Error rendering image block: {e}")
            return None

    @classmethod
    def _render_qr_block(cls, block: ContentBlock, max_width_px: int) -> Optional[Image.Image]:
        payload = block.qr_payload or "https://github.com"
        box_size = block.qr_size or 4
        ecc_map = {
            "L": qrcode.constants.ERROR_CORRECT_L,
            "M": qrcode.constants.ERROR_CORRECT_M,
            "Q": qrcode.constants.ERROR_CORRECT_Q,
            "H": qrcode.constants.ERROR_CORRECT_H
        }
        ecc = ecc_map.get((block.qr_ecc or "M").upper(), qrcode.constants.ERROR_CORRECT_M)

        qr = qrcode.QRCode(
            version=None,
            error_correction=ecc,
            box_size=box_size,
            border=2
        )
        qr.add_data(payload)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white").convert("1")
        if qr_img.width > max_width_px:
            qr_img = qr_img.resize((max_width_px, max_width_px), Image.Resampling.NEAREST)

        setattr(qr_img, "align", block.align or "center")
        return qr_img

    @classmethod
    def _render_barcode_block(cls, block: ContentBlock, max_width_px: int) -> Optional[Image.Image]:
        payload = block.barcode_payload or "123456789"
        b_type = (block.barcode_type or "code128").lower()
        height = block.barcode_height or 50

        try:
            barcode_cls = barcode.get_barcode_class(b_type)
            bc = barcode_cls(payload, writer=ImageWriter())
            buffer = io.BytesIO()
            bc.write(buffer, options={"write_text": block.show_barcode_text, "text_distance": 2})
            buffer.seek(0)
            bc_img = Image.open(buffer).convert("1")

            # Scale so the barcode respects the requested height, while never
            # exceeding the printable width.
            aspect = bc_img.width / bc_img.height
            target_h = max(8, min(height, int(max_width_px / aspect)))
            target_w = int(target_h * aspect)
            if target_w > max_width_px:
                target_w = max_width_px
                target_h = int(target_w / aspect)
            if target_w != bc_img.width or target_h != bc_img.height:
                bc_img = bc_img.resize((target_w, target_h), Image.Resampling.NEAREST)

            setattr(bc_img, "align", block.align or "center")
            return bc_img
        except Exception as e:
            logger.error(f"Error rendering barcode block: {e}")
            return None

    @classmethod
    def _render_line_block(cls, block: ContentBlock, max_width_px: int) -> Image.Image:
        style = (block.line_style or "solid").lower()
        height = 8
        img = Image.new("1", (max_width_px, height), 1)
        draw = ImageDraw.Draw(img)

        y = height // 2
        if style == "solid":
            draw.line([(0, y), (max_width_px, y)], fill=0, width=1)
        elif style == "dashed":
            for x in range(0, max_width_px, 8):
                draw.line([(x, y), (min(max_width_px, x + 4), y)], fill=0, width=1)
        elif style == "dotted":
            for x in range(0, max_width_px, 4):
                draw.point((x, y), fill=0)
        elif style == "double":
            draw.line([(0, y - 1), (max_width_px, y - 1)], fill=0, width=1)
            draw.line([(0, y + 1), (max_width_px, y + 1)], fill=0, width=1)

        setattr(img, "align", "center")
        return img

    @classmethod
    def _render_table_block(cls, block: ContentBlock, max_width_px: int) -> Optional[Image.Image]:
        """
        Renders a column-aligned table (receipt items, inventory, etc.).
        Column widths are explicit (table_col_widths) when given, otherwise
        auto-distributed from the widest cell per column, capped at 384 dots.
        """
        headers = [str(h) for h in (block.table_headers or [])]
        rows = [[str(c) if c is not None else "" for c in row] for row in (block.table_rows or [])]
        col_count = max(len(headers), max((len(r) for r in rows), default=0))
        if col_count == 0:
            return None

        font = cls.get_font(13, monospace=True)
        temp_img = Image.new("1", (1, 1), 1)
        temp_draw = ImageDraw.Draw(temp_img)
        cell_pad = 6

        def cell_widths(values: List[List[str]]) -> List[int]:
            widths = []
            for c in range(col_count):
                w = 0
                for row in values:
                    if c < len(row):
                        for line in row[c].split("\n"):
                            w = max(w, cls._measure_text(temp_draw, line, font))
                widths.append(w)
            return widths

        widths = cell_widths([headers] + rows)
        explicit = block.table_col_widths or []
        if len(explicit) >= col_count and all(w and w > 0 for w in explicit[:col_count]):
            used = sum(explicit[:col_count])
            scale = max_width_px / used if used > max_width_px else 1.0
            widths = [max(8, int(w * scale)) for w in explicit[:col_count]]
        else:
            total = sum(widths) + cell_pad * col_count
            if total > max_width_px and total > 0:
                scale = max_width_px / total
                widths = [max(1, int(w * scale)) for w in widths]
            # Distribute the residual slack so rows always fill the width edge-to-edge
            slack = max_width_px - (sum(widths) + cell_pad * (col_count - 1))
            if slack > 0 and col_count:
                widths[0] += slack

        line_height = 20
        row_heights = []
        for row in rows:
            max_lines = max((len(c.split("\n")) for c in row), default=1)
            row_heights.append(max(1, max_lines) * line_height)
        header_height = line_height if headers else 0
        total_height = header_height + sum(row_heights)

        img = Image.new("1", (max_width_px, total_height), 1)
        draw = ImageDraw.Draw(img)

        y = 0
        if headers:
            x = 0
            for c in range(col_count):
                text = headers[c] if c < len(headers) else ""
                draw.text((x + 2, y + 4), text, fill=0, font=font)
                draw.line([(x, y + line_height - 2), (x + widths[c], y + line_height - 2)], fill=0, width=1)
                x += widths[c] + cell_pad
            y += header_height

        for row in rows:
            max_lines = max((len(c.split("\n")) for c in row), default=1)
            x = 0
            for c in range(col_count):
                text = row[c] if c < len(row) else ""
                cy = y
                for line in text.split("\n") or [""]:
                    draw.text((x + 2, cy + 4), line, fill=0, font=font)
                    cy += line_height
                x += widths[c] + cell_pad
            y += max_lines * line_height

        setattr(img, "align", "left")
        return img

    @classmethod
    def _render_totals_block(cls, block: ContentBlock, max_width_px: int) -> Optional[Image.Image]:
        """
        Renders label/value lines (Subtotal, Tax, TOTAL...) with dotted
        leaders, values right-aligned. 'bold' lines get a stroke for emphasis.
        """
        lines = block.totals_lines or []
        if not lines:
            return None

        font = cls.get_font(15)
        temp_img = Image.new("1", (1, 1), 1)
        temp_draw = ImageDraw.Draw(temp_img)
        line_height = 24
        total_height = len(lines) * line_height

        img = Image.new("1", (max_width_px, total_height), 1)
        draw = ImageDraw.Draw(img)

        for i, entry in enumerate(lines):
            label = str((entry or {}).get("label", "") if isinstance(entry, dict) else entry)
            value = str((entry or {}).get("value", "") if isinstance(entry, dict) else "")
            dotted = bool((entry or {}).get("dotted", True)) if isinstance(entry, dict) else True
            bold = bool((entry or {}).get("bold", False)) if isinstance(entry, dict) else False

            y = i * line_height + 5
            label_w = cls._measure_text(draw, label, font)
            value_w = cls._measure_text(draw, value, font)
            value_x = max_width_px - value_w

            stroke = 1 if bold else 0
            draw.text((0, y), label, fill=0, font=font, stroke_width=stroke)
            draw.text((value_x, y), value, fill=0, font=font, stroke_width=stroke)

            if dotted and value_x - label_w > 8:
                step = 6
                for x in range(label_w, value_x, step):
                    draw.point((x, y + font.size // 2), fill=0)
            if bold:
                draw.line([(0, y + line_height - 3), (max_width_px, y + line_height - 3)], fill=0, width=2)

        setattr(img, "align", "left")
        return img

    @classmethod
    def generate_protocol_bytes(
        cls,
        image: Image.Image,
        protocol: str = "escpos",
        feed_lines: int = 3,
        cut_paper: bool = False,
        density: int = 8,
        feed_dots: Optional[int] = None,
        gray: bool = False
    ) -> bytes:
        """
        Converts 1-bit thermal image into ESC/POS or TSPL protocol commands.
        feed_dots controls the iPrint trailing feed (tear-bar clearance) and
        defaults to the known-good 130 dots when not provided.
        `gray=True` (iPrint only) activates the printer's TRUE 16-level
        grayscale mode (the official app's 0xBE [0,1] + 0xCF LZO chunks),
        with the app's gray energy formula for the SC03h:
            energy = 4100 × (1 + 0.15 × (density − 4))
        """
        raster_data = ImageProcessor.to_raster_bytes(image)
        width_px, height_px = image.size

        if protocol.lower() == "tspl":
            width_bytes = (width_px + 7) // 8
            cmd_buf = bytearray()
            cmd_buf.extend(TSPLProtocol.initialize(58, 0))
            cmd_buf.extend(TSPLProtocol.bitmap(0, 0, width_bytes, height_px, raster_data))
            cmd_buf.extend(TSPLProtocol.print_label(1))
            return bytes(cmd_buf)
        elif protocol.lower() == "iprint":
            from backend.protocols.iprint import IPrintProtocol
            if gray:
                # True 16-level grayscale (SC03h firmware): the app's math.
                gray_rows = ImageProcessor.process_gray(image, target_width_px=width_px)
                energy = int(4100 * (1 + 0.15 * (max(1, min(10, density)) - 4)))
                actual_feed = (feed_dots if feed_dots is not None else 130) if feed_lines > 0 else 0
                return IPrintProtocol.build_gray_payload(gray_rows, energy=energy, speed=40, feed_lines=actual_feed)
            # Cat Printers usually need extra feed lines to clear the tear bar.
            # 130 dots is a good balance between clearing the bar and saving
            # paper; the value is user-configurable via printer settings.
            actual_feed = (feed_dots if feed_dots is not None else 130) if feed_lines > 0 else 0
            return IPrintProtocol.generate_payload(image, feed_lines=actual_feed, density=density)
        else:
            # Default ESC/POS
            cmd_buf = bytearray()
            cmd_buf.extend(ESCPOSProtocol.INIT)
            cmd_buf.extend(ESCPOSProtocol.ALIGN_CENTER)
            cmd_buf.extend(ESCPOSProtocol.build_raster_image(width_px, height_px, raster_data))
            if feed_lines > 0:
                cmd_buf.extend(ESCPOSProtocol.feed_lines(feed_lines))
            if cut_paper:
                cmd_buf.extend(ESCPOSProtocol.CUT_PAPER)
            return bytes(cmd_buf)

    # ------------------------------------------------------------------ #
    # Density calibration (image-only, one-tap)
    # ------------------------------------------------------------------ #

    @classmethod
    def _render_calibration_label(cls, text: str) -> Image.Image:
        """Small centered label strip (e.g. 'DENSITY 5') above each strip."""
        img = Image.new("1", (384, 28), 1)  # 1 = white
        draw = ImageDraw.Draw(img)
        font = cls.get_font(17)
        width = cls._measure_text(draw, text, font)
        draw.text(((384 - width) // 2, 5), text, fill=0, font=font)
        return img

    @classmethod
    def build_density_calibration(
        cls,
        processed_image: Image.Image,
        densities=(5, 6, 7, 8, 9, 10),
        strip_feed_dots: int = 30
    ) -> bytes:
        """
        Builds ONE payload that prints the same image at several energy
        levels. Each strip is its own self-contained iPrint job (wake + init
        + 0xAF energy + rows + feed), which the protocol allows (doc 6.1) —
        the energy value applies to everything after it until the next one.
        """
        from backend.protocols.iprint import IPrintProtocol

        if processed_image.mode != "1":
            processed_image = processed_image.convert("1")
        if processed_image.width != 384:
            # Center on a 384-wide canvas so rows stay 48 bytes.
            pad = (384 - processed_image.width) // 2
            canvas = Image.new("1", (384, processed_image.height), 1)
            canvas.paste(processed_image, (pad, 0))
            processed_image = canvas

        out = bytearray()
        for density in densities:
            density = max(1, min(10, int(density)))
            label = cls._render_calibration_label(f"DENSITY {density}")
            composite = Image.new("1", (384, label.height + processed_image.height), 1)
            composite.paste(label, (0, 0))
            composite.paste(processed_image, (0, label.height))
            out.extend(IPrintProtocol.generate_payload(
                composite, feed_lines=strip_feed_dots, density=density
            ))
        return bytes(out)
