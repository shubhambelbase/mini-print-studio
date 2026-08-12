import io
import base64
import math
from typing import Tuple
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


class ImageProcessor:
    """
    Thermal image processing engine.
    Converts full-color / grayscale images into 1-bit black-and-white images optimized for thermal printing.
    """

    BAYER_MATRIX_4X4 = [
        [ 0,  8,  2, 10],
        [12,  4, 14,  6],
        [ 3, 11,  1,  9],
        [15,  7, 13,  5]
    ]

    BAYER_MATRIX_8X8 = [
        [ 0, 32,  8, 40,  2, 34, 10, 42],
        [48, 16, 56, 24, 50, 18, 58, 26],
        [12, 44,  4, 36, 14, 46,  6, 38],
        [60, 28, 52, 20, 62, 30, 54, 22],
        [ 3, 35, 11, 43,  1, 33,  9, 41],
        [51, 19, 59, 27, 49, 17, 57, 25],
        [15, 47,  7, 39, 13, 45,  5, 37],
        [63, 31, 55, 23, 61, 29, 53, 21]
    ]

    @staticmethod
    def _histogram_percentile(hist: list, fraction: float) -> tuple:
        """
        Returns the (low, high) luminance values that bracket the given
        cumulative fraction of pixels (e.g. 0.01 = the 1%-99% range).
        Used to decide whether a histogram stretch is actually needed.
        """
        total = sum(hist)
        if total <= 0:
            return 0, 255
        target = total * fraction
        lo = 0
        acc = 0
        for v, count in enumerate(hist):
            acc += count
            if acc >= target:
                lo = v
                break
        hi = 255
        acc = 0
        for v in range(255, -1, -1):
            acc += hist[v]
            if acc >= target:
                hi = v
                break
        return lo, hi

    @classmethod
    def load_image(cls, image_source: str) -> Image.Image:
        """
        Loads an image from Base64 string, data URL, or binary payload.
        """
        if isinstance(image_source, str):
            if image_source.startswith("data:image"):
                # Strip header
                header, base64_data = image_source.split(",", 1)
                image_bytes = base64.b64decode(base64_data)
            else:
                image_bytes = base64.b64decode(image_source)
            return Image.open(io.BytesIO(image_bytes))
        raise ValueError("Unsupported image source format")

    @classmethod
    def process_image(
        cls,
        image: Image.Image,
        target_width_px: int = 384,
        dither_mode: str = "atkinson",
        brightness: float = 1.0,
        contrast: float = 1.0,
        sharpen: float = 1.0,
        scale_mode: str = "fit",
        invert: bool = False,
        auto_level: bool = True,
        smooth: float = 0.7
    ) -> Image.Image:
        """
        Main pipeline: Resize -> Grayscale -> Auto-level -> Brightness -> Contrast
        -> Sharpen -> Smooth (photos) -> Dither -> 1-bit output.
        Auto-level (histogram stretch) is applied by default so photos print with
        the same punch as the official iPrint app instead of looking washed out.
        `smooth` applies a hair of Gaussian blur before error-diffusion dithering
        (photos only) so the output doesn't read as harshly "sharpened".
        """
        # Ensure RGB/RGBA
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            # Composite over white background for transparent PNGs
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode != "RGBA":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[3])
            image = background
        else:
            image = image.convert("RGB")

        # 1. Scaling & Resizing
        orig_w, orig_h = image.size
        if scale_mode == "crop":
            # Crop: fill the full printable width at (near) native resolution.
            # Wider-than-print sources are center-cropped to a 384px-wide slice;
            # narrower sources are scaled up to fill the width (same as fit).
            if image.width > target_width_px:
                left = (image.width - target_width_px) // 2
                image = image.crop((left, 0, left + target_width_px, image.height))
                width_now, height_now = image.size
                if width_now != target_width_px:
                    image = image.resize((target_width_px, height_now), Image.Resampling.LANCZOS)
            elif image.width != target_width_px:
                aspect_ratio = orig_h / orig_w
                target_height = int(target_width_px * aspect_ratio)
                image = image.resize((target_width_px, target_height), Image.Resampling.LANCZOS)
        elif scale_mode == "fit" or orig_w != target_width_px:
            aspect_ratio = orig_h / orig_w
            target_height = int(target_width_px * aspect_ratio)
            image = image.resize((target_width_px, target_height), Image.Resampling.LANCZOS)

        # 2. Grayscale conversion
        grayscale = image.convert("L")

        # 2b. Auto-level: the doc's 1% clip histogram stretch is the reason
        # photos print "punchy" like the iPrint app — but applied blindly it
        # CRUSHES shadows to solid black (blackish prints) and amplifies
        # grain (over-sharpened look). Only stretch when the image is
        # genuinely flat/washed out; already-wide histograms keep their tone.
        if auto_level:
            hist = grayscale.histogram()
            lo, hi = cls._histogram_percentile(hist, 0.01)
            if hi - lo < 170:  # < ~2/3 of the full range → flat image
                grayscale = ImageOps.autocontrast(grayscale, cutoff=1)

        # 3. Brightness adjustment (neutral at 1.0)
        if brightness != 1.0:
            enhancer = ImageEnhance.Brightness(grayscale)
            grayscale = enhancer.enhance(brightness)

        # 4. Contrast adjustment (neutral at 1.0)
        if contrast != 1.0:
            enhancer = ImageEnhance.Contrast(grayscale)
            grayscale = enhancer.enhance(contrast)

        # 5. Sharpening filter
        if sharpen > 1.0:
            radius = 1.5
            percent = int((sharpen - 1.0) * 150 + 100)
            grayscale = grayscale.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=3))

        # 6. Invert if requested
        if invert:
            grayscale = ImageOps.invert(grayscale)

        # 6b. Photo smoothing (diffusion dithers only). Error diffusion
        # amplifies high-frequency noise into a harsh, "over-sharpened" dot
        # pattern; a hair of Gaussian blur removes that noise, and a gentle
        # midtone lift keeps blacks from overwhelming the print. Threshold
        # mode (text / QR / line art) is left untouched so it stays crisp.
        dither_key = dither_mode.lower()
        diffusion = dither_key in ("atkinson", "floyd-steinberg", "floyd", "stucki")
        if diffusion:
            radius = max(0.0, float(smooth if smooth is not None else 0.7))
            if radius > 0:
                grayscale = grayscale.filter(ImageFilter.GaussianBlur(radius))
            grayscale = grayscale.point(lambda v: int(255 * ((v / 255.0) ** 0.92)))

        # 7. Dithering to 1-bit (B&W)
        if dither_key == "floyd-steinberg" or dither_key == "floyd":
            # Pillow built-in high quality Floyd-Steinberg error diffusion
            bw_img = grayscale.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
        elif dither_key == "atkinson":
            bw_img = cls._apply_atkinson_dithering(grayscale)
        elif dither_key == "stucki":
            bw_img = cls._apply_stucki_dithering(grayscale)
        elif dither_key == "bayer" or dither_key == "ordered":
            bw_img = cls._apply_bayer_dithering(grayscale)
        else:
            # Simple threshold cutoff
            threshold_val = 128
            bw_img = grayscale.point(lambda p: 255 if p > threshold_val else 0, mode="1")

        return bw_img

    @classmethod
    def _apply_atkinson_dithering(cls, grayscale_img: Image.Image) -> Image.Image:
        """
        Atkinson error diffusion (the kernel thermal-printing apps favour).
        Spreads 3/4 of the error to 6 neighbours (1/8 each); the lost 1/4
        lightens the result slightly, which reads as clean crisp dots on
        thermal paper instead of muddy worm patterns.
        """
        width, height = grayscale_img.size
        pixels = grayscale_img.load()
        output_img = Image.new("1", (width, height))
        out_pixels = output_img.load()
        err = [[0.0] * (width + 3) for _ in range(height + 3)]

        for y in range(height):
            for x in range(width):
                old = pixels[x, y] + err[y + 1][x + 1]
                new = 255 if old >= 128 else 0
                out_pixels[x, y] = new
                qe = old - new
                if qe == 0:
                    continue
                e = qe / 8.0
                err[y + 1][x + 2] += e
                err[y + 2][x + 3] += e
                err[y + 2][x + 2] += e
                err[y + 2][x + 1] += e
                err[y + 2][x] += e
                err[y + 3][x + 1] += e

        return output_img

    @classmethod
    def _apply_stucki_dithering(cls, grayscale_img: Image.Image) -> Image.Image:
        """
        Stucki error diffusion — heavier kernel than Floyd-Steinberg, keeps
        richer blacks and smoother gradients.
        """
        width, height = grayscale_img.size
        pixels = grayscale_img.load()
        output_img = Image.new("1", (width, height))
        out_pixels = output_img.load()
        err = [[0.0] * (width + 4) for _ in range(height + 3)]

        for y in range(height):
            for x in range(width):
                old = pixels[x, y] + err[y + 1][x + 2]
                new = 255 if old >= 128 else 0
                out_pixels[x, y] = new
                qe = old - new
                if qe == 0:
                    continue
                e = qe / 42.0
                err[y + 1][x + 3] += e * 8
                err[y + 1][x + 4] += e * 4
                err[y + 2][x] += e * 2
                err[y + 2][x + 1] += e * 4
                err[y + 2][x + 2] += e * 8
                err[y + 2][x + 3] += e * 4
                err[y + 2][x + 4] += e * 2
                err[y + 3][x] += e * 1
                err[y + 3][x + 1] += e * 2
                err[y + 3][x + 2] += e * 4
                err[y + 3][x + 3] += e * 2
                err[y + 3][x + 4] += e * 1

        return output_img

    @classmethod
    def _apply_bayer_dithering(cls, grayscale_img: Image.Image) -> Image.Image:
        """
        Applies an 8x8 Bayer ordered dithering matrix.
        """
        width, height = grayscale_img.size
        pixels = grayscale_img.load()
        output_img = Image.new("1", (width, height))
        out_pixels = output_img.load()

        matrix = cls.BAYER_MATRIX_8X8
        m_size = 8
        factor = 256.0 / (m_size * m_size + 1)

        for y in range(height):
            for x in range(width):
                gray = pixels[x, y]
                bayer_val = matrix[y % m_size][x % m_size] * factor
                out_pixels[x, y] = 255 if gray > bayer_val else 0

        return output_img

    @classmethod
    def to_base64_png(cls, image: Image.Image) -> str:
        """
        Converts PIL Image to Base64 PNG data URL.
        """
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64_str}"

    @classmethod
    def to_raster_bytes(cls, image: Image.Image) -> bytes:
        """
        Converts 1-bit Image to packed raster bytes suitable for thermal printer bit image commands.
        In 1-bit image: 0 is black (dot on), 1 (255) is white (dot off).
        Packed 8 pixels per byte (MSB first).
        """
        image_1bit = image.convert("1")
        width, height = image_1bit.size
        
        # Ensure width is divisible by 8 (pad right with white pixels if needed)
        padded_width = ((width + 7) // 8) * 8
        if padded_width != width:
            padded_img = Image.new("1", (padded_width, height), 1) # 1 = white
            padded_img.paste(image_1bit, (0, 0))
            image_1bit = padded_img
            width = padded_width

        pixels = image_1bit.load()
        bytes_per_row = width // 8
        raster_data = bytearray(bytes_per_row * height)

        idx = 0
        for y in range(height):
            for x_byte in range(bytes_per_row):
                b = 0
                for bit in range(8):
                    x = x_byte * 8 + bit
                    # In thermal printing: 1 bit in byte = black dot printed
                    # In PIL "1" mode: 0 = black pixel, 255 (or True/1) = white pixel
                    pix = pixels[x, y]
                    if pix == 0:  # Black pixel -> print dot
                        b |= (1 << (7 - bit))
                raster_data[idx] = b
                idx += 1

        return bytes(raster_data)
