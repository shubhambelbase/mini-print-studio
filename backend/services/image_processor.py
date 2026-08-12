import io
import base64
from typing import Dict, Optional
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


class ImageProcessor:
    """
    Thermal image processing engine.

    Converts full-color / grayscale images into 1-bit black-and-white images
    optimized for THERMAL printing (not for LCD viewing). The pipeline is
    staged so the tone-mapped grayscale can be reused to compare dithering
    algorithms before the 1-bit conversion:

        source
        → aspect-ratio correction
        → resize to printer resolution (384 px)
        → grayscale
        → tone/brightness (gamma + brightness)
        → mild contrast
        → optional very-light smoothing (photos only)
        → tone mapping (smart auto-level)
        → dithering
        → 1-bit bitmap
        → printer raster data

    Design rules (from real SC03h prints):
      * NEVER sharpen before dithering a photo — artificial high-frequency
        noise becomes harsh dot texture on paper.
      * NEVER resize after dithering — pixels are hard dots.
      * Diffusing dithers amplify sensor noise: a hair of blur first.
      * Gamma is a tunable preset parameter, NOT a blind constant.
    """

    # Printer geometry (iPrint / SC03h): fixed 384 dots across, 8 dots/mm.
    PRINT_WIDTH_PX = 384

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

    # Ordered-dither matrix choice: 8x8 gives cleaner flat regions on thermal
    # paper than 4x4 (fewer, larger pattern cells read as intentional texture).
    BAYER_MATRIX = BAYER_MATRIX_8X8
    BAYER_SIZE = 8

    # ── Processing presets ──────────────────────────────────────────────
    # Each preset fixes the thermal-appropriate defaults for one content
    # type. Every value can still be overridden per-image by the caller.
    PRESET_DEFS: Dict[str, dict] = {
        # Photo — Natural (default for photographic content)
        "photo": {
            "label": "Photo — Natural",
            "dither": "floyd-steinberg",   # serpentine FS: smoothest gradients
            "gamma": 1.0,                   # no tone shift by default
            "brightness": 1.0,
            "contrast": 1.0,
            "sharpness": 0.0,               # NO sharpening — avoids dot noise
            "smooth": 0.7,                  # hair of blur kills sensor noise
            "auto_level": True,             # smart stretch (washed-out only)
        },
        # Photo — High Detail: a touch more contrast, extremely mild sharpen
        "photo_detail": {
            "label": "Photo — High Detail",
            "dither": "atkinson",
            "gamma": 1.0,
            "brightness": 1.0,
            "contrast": 1.12,
            "sharpness": 0.15,              # very mild UnsharpMask
            "smooth": 0.35,
            "auto_level": True,
        },
        # Manga: solid blacks, clean whites, strong separation, thin lines kept
        "manga": {
            "label": "Manga",
            "dither": "bayer",              # ordered = no diffusion noise
            "gamma": 1.0,
            "brightness": 1.0,
            "contrast": 1.3,                # push toward black/white
            "sharpness": 0.0,
            "smooth": 0.0,                  # never blur line art
            "auto_level": True,
        },
        # Line Art: crisp lines, minimal gray processing
        "line_art": {
            "label": "Line Art",
            "dither": "threshold",
            "gamma": 1.0,
            "brightness": 1.0,
            "contrast": 1.15,
            "sharpness": 0.0,
            "smooth": 0.0,
            "auto_level": True,
        },
        # Text: maximum readability, no photographic dithering
        "text": {
            "label": "Text",
            "dither": "threshold",
            "gamma": 1.0,
            "brightness": 1.0,
            "contrast": 1.1,
            "sharpness": 0.0,
            "smooth": 0.0,
            "auto_level": False,            # keep the source's own range
        },
        # QR / Barcode: clean threshold, untouched tone
        "qr": {
            "label": "QR / Barcode",
            "dither": "threshold",
            "gamma": 1.0,
            "brightness": 1.0,
            "contrast": 1.0,
            "sharpness": 0.0,
            "smooth": 0.0,
            "auto_level": False,
        },
    }

    DIFFUSION_DITHERS = ("atkinson", "floyd-steinberg", "floyd", "stucki")

    @classmethod
    def _resolve_preset(cls, processing_preset: Optional[str]) -> dict:
        """Resolves a preset id; unknown ids fall back to the photo preset.
        `None` keeps the pre-preset pipeline (legacy callers stay identical)."""
        if processing_preset is None:
            return {
                "label": "Legacy",
                "dither": "atkinson",
                "gamma": 0.92,
                "brightness": 1.0,
                "contrast": 1.0,
                "sharpness": 0.0,
                "smooth": 0.7,
                "auto_level": True,
            }
        key = str(processing_preset).strip().lower()
        return cls.PRESET_DEFS.get(key, cls.PRESET_DEFS["photo"])

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
                header, base64_data = image_source.split(",", 1)
                image_bytes = base64.b64decode(base64_data)
            else:
                image_bytes = base64.b64decode(image_source)
            return Image.open(io.BytesIO(image_bytes))
        raise ValueError("Unsupported image source format")

    # ── Stage 1+2: alpha flatten, aspect correction, resize to 384 ─────

    @classmethod
    def _prepare_canvas(cls, image: Image.Image, target_width_px: int, scale_mode: str) -> Image.Image:
        """
        Aspect-ratio correction and resize to the printer's dot width.
        All resizing happens BEFORE dithering (never after).
        """
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            # Composite over white so transparency becomes white paper.
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode != "RGBA":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[3])
            image = background
        else:
            image = image.convert("RGB")

        orig_w, orig_h = image.size
        if scale_mode == "crop":
            # Center-crop wide sources at (near) native resolution, then pad
            # narrow sources up — the printable width must always be filled.
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
        return image

    # ── Stages 3–8: grayscale → tone → contrast → smooth → tonemap ─────

    @classmethod
    def _apply_gamma(cls, grayscale: Image.Image, gamma: float) -> Image.Image:
        """Gamma tone curve: <1 lifts midtones (lighter print, fewer dots),
        >1 darkens. 1.0 is a no-op and leaves pixels untouched."""
        if gamma is None or abs(gamma - 1.0) < 1e-6:
            return grayscale
        return grayscale.point(lambda v: int(255 * ((v / 255.0) ** gamma)))

    @classmethod
    def _apply_smart_autolevel(cls, grayscale: Image.Image, cutoff: float = 1.0,
                               span_threshold: int = 170) -> Image.Image:
        """
        Tone mapping: the 1% clip histogram stretch that makes prints look
        punchy — but only when it helps, never when it hurts:

          * narrow 1%–99% span (< ~2/3 of the range) — the image is flat, AND
          * mean below 175 — the image is NOT an intentionally bright scene.

        Rationale (measured on real pipeline outputs):
          * dark image (span < 170, mean ~65): stretching 25..105 → 0..255
            yields a printable ~50% black image with visible detail; NOT
            stretching leaves it ~80–100% black (solid sheet).
          * light image (span < 170, mean ~185): stretching 175..255 → 0..255
            wrongly doubles darkness (50% black); skipping keeps clean whites.
          * washed-out mid-gray (span small, mean ~130): stretch restores the
            full tonal range — the classic iPrint-app "punch".
        """
        hist = grayscale.histogram()
        total = sum(hist)
        if total <= 0:
            return grayscale
        lo, hi = cls._histogram_percentile(hist, cutoff / 100.0)
        if hi - lo >= span_threshold:
            return grayscale
        mean = sum(v * c for v, c in enumerate(hist)) / total
        if mean >= 175.0:
            return grayscale
        return ImageOps.autocontrast(grayscale, cutoff=cutoff)

    @classmethod
    def _apply_very_mild_sharpening(cls, grayscale: Image.Image, strength: float) -> Image.Image:
        """Extremely mild UnsharpMask. `strength` in 0..1; 0 disables.
        Used ONLY by high-detail presets — never for natural photos, because
        sharpening before dithering creates artificial dot noise."""
        if strength is None or strength <= 0:
            return grayscale
        percent = 100 + int(min(1.0, strength) * 80)
        return grayscale.filter(ImageFilter.UnsharpMask(radius=1.0, percent=percent, threshold=3))

    @classmethod
    def prepare_grayscale(
        cls,
        image: Image.Image,
        target_width_px: int = 384,
        scale_mode: str = "fit",
        processing_preset: Optional[str] = None,
        brightness: Optional[float] = None,
        contrast: Optional[float] = None,
        sharpen: Optional[float] = None,
        invert: bool = False,
        auto_level: Optional[bool] = None,
        smooth: Optional[float] = None,
        gamma: Optional[float] = None,
        dither_mode: Optional[str] = None,
    ) -> Dict[str, Image.Image]:
        """
        Runs stages 1–8 and returns the intermediate images for reuse:
            original  — resized RGB canvas (384 wide)
            grayscale — fully tone-mapped 'L' image ready for dithering
            dither    — the resolved dither algorithm id
        """
        preset = cls._resolve_preset(processing_preset)

        # Explicit caller parameters override the preset; None = use preset.
        eff_brightness = preset["brightness"] if brightness is None else brightness
        eff_contrast = preset["contrast"] if contrast is None else contrast
        eff_auto_level = preset["auto_level"] if auto_level is None else auto_level
        eff_smooth = preset["smooth"] if smooth is None else smooth
        eff_gamma = preset["gamma"] if gamma is None else gamma
        eff_dither = preset["dither"] if dither_mode is None else dither_mode

        # Sharpening: the legacy `sharpen` parameter (1.0 = off) still wins
        # when explicitly set; otherwise preset sharpness (0..1) applies.
        if sharpen is not None and abs(sharpen - 1.0) > 1e-6:
            sharp_strength = max(0.0, (sharpen - 1.0) / 2.0)  # map 1..3 → 0..1
        else:
            sharp_strength = preset.get("sharpness", 0.0)

        # Diffusion dithers (photo pipelines) may apply gamma + smoothing;
        # ordered/threshold dithers (text/QR/line art) never do.
        dither_key = str(eff_dither).lower()
        is_diffusion = dither_key in cls.DIFFUSION_DITHERS

        # Stage 1–2: aspect correction + resize to the printer resolution.
        canvas = cls._prepare_canvas(image, target_width_px, scale_mode)

        # Stage 3: grayscale.
        grayscale = canvas.convert("L")

        # Stage 4: tone/brightness. Gamma is the tonal lever for photo
        # pipelines (kept from the legacy pipeline; 1.0 = no-op) — never
        # applied to threshold/ordered dithers so text and lines stay crisp.
        if is_diffusion:
            grayscale = cls._apply_gamma(grayscale, eff_gamma)
        if eff_brightness != 1.0:
            grayscale = ImageEnhance.Brightness(grayscale).enhance(eff_brightness)

        # Stage 5: mild contrast.
        if eff_contrast != 1.0:
            grayscale = ImageEnhance.Contrast(grayscale).enhance(eff_contrast)

        # Stage 5b: sharpening (opt-in, always mild). Natural photos never
        # sharpen — artificial high-frequency detail turns into dot noise on
        # paper. Only explicit user requests / high-detail presets reach here.
        if sharp_strength > 0:
            grayscale = cls._apply_very_mild_sharpening(grayscale, sharp_strength)

        # Stage 6: optional very-light smoothing (diffusion dithers only).
        # Error diffusion amplifies high-frequency noise into harsh dot
        # texture; a hair of Gaussian blur removes that noise. Threshold and
        # ordered dithers (text/QR/line art) stay untouched and crisp.
        if is_diffusion:
            radius = max(0.0, float(eff_smooth or 0.0))
            if radius > 0:
                grayscale = grayscale.filter(ImageFilter.GaussianBlur(radius))

        # Stage 7: tone mapping (smart auto-level).
        if eff_auto_level:
            grayscale = cls._apply_smart_autolevel(grayscale)

        # Stage 8: invert (applied last so the dither sees the final tones).
        if invert:
            grayscale = ImageOps.invert(grayscale)

        return {
            "original": canvas,
            "grayscale": grayscale,
            "dither": dither_key,
        }

    # ── Dithering ──────────────────────────────────────────────────────

    @classmethod
    def dither_image(cls, grayscale_img: Image.Image, algorithm: str) -> Image.Image:
        """
        Clean abstraction over every dithering algorithm. All algorithms take
        the same tone-mapped 'L' image and produce a 1-bit image, so they are
        interchangeable (used for the in-app comparison view).
        """
        key = (algorithm or "atkinson").lower()
        if key in ("floyd-steinberg", "floyd"):
            return cls._apply_floyd_steinberg(grayscale_img)
        if key == "atkinson":
            return cls._apply_atkinson_dithering(grayscale_img)
        if key == "stucki":
            return cls._apply_stucki_dithering(grayscale_img)
        if key in ("bayer", "ordered"):
            return cls._apply_bayer_dithering(grayscale_img)
        # threshold (default for text/QR/line art)
        return grayscale_img.point(lambda p: 255 if p > 128 else 0, mode="1")

    @classmethod
    def _apply_floyd_steinberg(cls, grayscale_img: Image.Image) -> Image.Image:
        """
        Serpentine (zig-zag) Floyd-Steinberg error diffusion.
        Full 16/16 error spread for the smoothest gradients; scanning
        direction alternates every row so no horizontal "worm" streaks form.
        This is the recommended thermal default for photographic content.
        """
        width, height = grayscale_img.size
        pixels = grayscale_img.load()
        output_img = Image.new("1", (width, height))
        out_pixels = output_img.load()
        err = [[0.0] * (width + 2) for _ in range(height + 2)]

        for y in range(height):
            left_to_right = (y % 2 == 0)
            row = range(width) if left_to_right else range(width - 1, -1, -1)
            for x in row:
                old = pixels[x, y] + err[y + 1][x + 1]
                new = 255 if old >= 128 else 0
                out_pixels[x, y] = new
                qe = old - new
                if qe == 0:
                    continue
                e7 = qe * 7 / 16.0
                e3 = qe * 3 / 16.0
                e5 = qe * 5 / 16.0
                e1 = qe / 16.0
                if left_to_right:
                    err[y + 1][x + 2] += e7
                    err[y + 2][x + 2] += e3
                    err[y + 2][x + 1] += e5
                    err[y + 2][x] += e1
                else:
                    err[y + 1][x] += e7
                    err[y + 2][x] += e3
                    err[y + 2][x + 1] += e5
                    err[y + 2][x + 2] += e1

        return output_img

    @classmethod
    def _apply_atkinson_dithering(cls, grayscale_img: Image.Image) -> Image.Image:
        """
        Atkinson error diffusion (the kernel the official iPrint app uses).
        Spreads 3/4 of the error to 6 neighbours (1/8 each); the lost 1/4
        lightens the result slightly, which reads as clean crisp dots on
        thermal paper instead of muddy worm patterns. Best for high-detail
        photos; slightly grainier than Floyd-Steinberg.
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
        8x8 Bayer ordered dithering. Produces a fixed, evenly-spaced dot
        pattern: no diffusion noise, clean flat regions — the right choice
        for manga/flat graphics. Larger matrix than 4x4 so the pattern is
        visible as intentional texture instead of buzzing noise.
        """
        width, height = grayscale_img.size
        pixels = grayscale_img.load()
        output_img = Image.new("1", (width, height))
        out_pixels = output_img.load()

        matrix = cls.BAYER_MATRIX
        m_size = cls.BAYER_SIZE
        factor = 256.0 / (m_size * m_size + 1)

        for y in range(height):
            for x in range(width):
                gray = pixels[x, y]
                bayer_val = matrix[y % m_size][x % m_size] * factor
                out_pixels[x, y] = 255 if gray > bayer_val else 0

        return output_img

    # ── Public pipeline entry points ───────────────────────────────────

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
        smooth: float = 0.7,
        processing_preset: Optional[str] = None,
        gamma: Optional[float] = None,
    ) -> Image.Image:
        """
        Full pipeline → 1-bit image.

        `processing_preset` ("photo", "photo_detail", "manga", "line_art",
        "text", "qr") selects thermal-tuned defaults; explicit parameters
        (dither_mode, brightness, contrast, sharpen, smooth, auto_level,
        gamma) override the preset. When no preset is given, the legacy
        pipeline (Atkinson + lift) is kept for backward compatibility.
        """
        stages = cls.prepare_grayscale(
            image=image,
            target_width_px=target_width_px,
            scale_mode=scale_mode,
            processing_preset=processing_preset,
            brightness=brightness if brightness != 1.0 else None,
            contrast=contrast if contrast != 1.0 else None,
            sharpen=sharpen,
            invert=invert,
            auto_level=auto_level,
            smooth=smooth,
            gamma=gamma,
            dither_mode=dither_mode,
        )
        return cls.dither_image(stages["grayscale"], stages["dither"])

    @classmethod
    def process_stages(
        cls,
        image: Image.Image,
        target_width_px: int = 384,
        dither_mode: Optional[str] = None,
        brightness: Optional[float] = None,
        contrast: Optional[float] = None,
        sharpen: Optional[float] = None,
        scale_mode: str = "fit",
        invert: bool = False,
        auto_level: Optional[bool] = None,
        smooth: Optional[float] = None,
        processing_preset: str = "photo",
        gamma: Optional[float] = None,
    ) -> Dict[str, object]:
        """
        Stage-by-stage processing for the compare view: returns the resized
        original, the tone-mapped grayscale, the final 1-bit output, and the
        same tone-mapped grayscale dithered with every algorithm so the user
        can pick what prints best on their paper.
        """
        stages = cls.prepare_grayscale(
            image=image,
            target_width_px=target_width_px,
            scale_mode=scale_mode,
            processing_preset=processing_preset,
            brightness=brightness,
            contrast=contrast,
            sharpen=sharpen,
            invert=invert,
            auto_level=auto_level,
            smooth=smooth,
            gamma=gamma,
            dither_mode=dither_mode,
        )
        gray = stages["grayscale"]
        variants = {}
        for algo in ("floyd-steinberg", "atkinson", "bayer", "threshold"):
            variants[algo] = cls.dither_image(gray, algo)
        return {
            "original": stages["original"],
            "grayscale": gray,
            "final": cls.dither_image(gray, stages["dither"]),
            "dither": stages["dither"],
            "variants": variants,
        }

    # ── True grayscale pipeline (iPrint app's 16-level mode) ────────────
    # The SC03h firmware supports REAL grayscale printing (per-dot heat
    # levels). The official app activates it with 0xBE [0x00, 0x01] and sends
    # 16-level rows: 2 pixels per byte, 4 bits each, burn level 0..15 where
    # 15 = white (no heat) and 0 = black (full heat), FIRST pixel in the LOW
    # nibble. This pipeline replicates the app's image math exactly.

    @classmethod
    def process_gray(cls, image: Image.Image, target_width_px: int = 384,
                     gray_scale: float = 0.9, level: int = 16,
                     low_threshold: float = 0.2, high_threshold: float = 0.2,
                     threshold_scale: float = 0.46,
                     gray_low_value: int = 110, gray_high_value: int = 150) -> bytes:
        """
        Converts an image to the app's grayscale print data:
        resize → grayscale → 20%-clip tone curve → ×gray_scale →
        gray-level Floyd–Steinberg diffusion → 4-bit packing (2 px/byte).
        Returns the raw row data (192 bytes per 384-dot row, no headers).
        """
        canvas = cls._prepare_canvas(image, target_width_px, "fit")
        gray = canvas.convert("L")
        w, h = gray.size
        pix = list(gray.getdata())

        # Tone curve from the app (convertGreyImgByFloydPixels):
        # percentile clip at `low_threshold`/`high_threshold` (20% default —
        # far gentler than the 1% used for 1-bit prints), bounded by the
        # gray_low/gray_high values.
        hist = [0] * 256
        for v in pix:
            hist[v] += 1
        total = w * h
        low = 0
        acc = 0
        for i in range(256):
            acc += hist[i]
            if acc > total * low_threshold:
                low = i
                break
        high = 255
        acc = 0
        for i in range(255, -1, -1):
            acc += hist[i]
            if acc > total * high_threshold:
                high = i
                break
        low = min(low, gray_low_value)
        high = max(high, gray_high_value)

        # map pixel: dark side scaled by threshold_scale, light side pulled
        # toward white, middle linearly interpolated, then × gray_scale.
        mapped = []
        for v in pix:
            if v <= low:
                out_v = v * threshold_scale
            elif v >= high:
                out_v = v + (255 - v) * (1.0 - threshold_scale)
            else:
                f_lo = low * threshold_scale
                f_hi = high + (255 - high) * (1.0 - threshold_scale)
                out_v = ((v - low) * (f_hi - f_lo) / (high - low)) + f_lo
            out_v *= gray_scale
            out_v = 255 if out_v > 255 else (0 if out_v < 0 else int(out_v))
            mapped.append(out_v)

        # Gray-level Floyd–Steinberg error diffusion to `level` steps.
        diffused = cls._diffuse_gray_levels(mapped, w, h, level)

        # 4-bit packing: first pixel in the low nibble; nibble = 15 - level.
        out = bytearray()
        for y in range(h):
            for x in range(0, w, 2):
                p0 = diffused[y * w + x]
                p1 = diffused[y * w + x + 1] if x + 1 < w else 255
                n0 = 15 - min(15, p0 // (256 // level))
                n1 = 15 - min(15, p1 // (256 // level))
                out.append((n1 << 4) | n0)
        return bytes(out)

    @classmethod
    def _diffuse_gray_levels(cls, pixels: list, width: int, height: int, level: int) -> list:
        """
        Error diffusion between GRAY LEVELS (not black/white): each pixel is
        quantized to one of `level` steps and the residual error is spread to
        neighbours (7/16, 3/16, 5/16, 1/16) — this is what makes the app's
        grayscale prints look smooth and natural instead of dithered.
        """
        step = 256 // level
        quant = 256 // (level - 1)
        buf = [float(v) for v in pixels]
        for y in range(height):
            for x in range(width):
                i = y * width + x
                v = buf[i]
                q = (v // step) * quant
                q = min(255, q)
                buf[i] = q
                err = v - q
                if err == 0:
                    continue
                if x + 1 < width:
                    buf[i + 1] += err * 7 / 16
                if y + 1 < height:
                    if x > 0:
                        buf[i + width - 1] += err * 3 / 16
                    buf[i + width] += err * 5 / 16
                    if x + 1 < width:
                        buf[i + width + 1] += err / 16
        return [max(0, min(255, int(v))) for v in buf]

    @classmethod
    def gray_rows_to_image(cls, rows: bytes, width_px: int = 384) -> Image.Image:
        """
        Decodes packed 4-bit gray rows back into an 'L' image — the exact
        16-level output the printer will burn (nibble 0 = black, 15 = white).
        Used for the thermal preview so what you see equals what prints.
        """
        row_bytes = width_px // 2
        if row_bytes <= 0 or len(rows) < row_bytes:
            return Image.new("L", (width_px, 0), 255)
        height = len(rows) // row_bytes
        img = Image.new("L", (width_px, height), 255)
        px = img.load()
        for y in range(height):
            base = y * row_bytes
            for x in range(0, width_px, 2):
                b = rows[base + x // 2]
                px[x, y] = (15 - (b & 0x0F)) * 17
                px[x + 1, y] = (15 - ((b >> 4) & 0x0F)) * 17
        return img

    # ── Output helpers ─────────────────────────────────────────────────

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
        Packed 8 pixels per byte (MSB first). 384 px wide → 48 bytes per row.
        """
        image_1bit = image.convert("1")
        width, height = image_1bit.size

        # Ensure width is divisible by 8 (pad right with white pixels if needed)
        padded_width = ((width + 7) // 8) * 8
        if padded_width != width:
            padded_img = Image.new("1", (padded_width, height), 1)  # 1 = white
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
