class ESCPOSProtocol:
    """
    ESC/POS Protocol Command Generator for 58mm / 80mm thermal receipt printers.
    """

    # Control Commands
    ESC = b'\x1b'
    GS = b'\x1d'

    INIT = ESC + b'@'
    LF = b'\n'

    # Alignment
    ALIGN_LEFT = ESC + b'a\x00'
    ALIGN_CENTER = ESC + b'a\x01'
    ALIGN_RIGHT = ESC + b'a\x02'

    # Formatting
    BOLD_ON = ESC + b'E\x01'
    BOLD_OFF = ESC + b'E\x00'
    UNDERLINE_ON = ESC + b'-\x01'
    UNDERLINE_OFF = ESC + b'-\x00'
    INVERT_ON = GS + b'B\x01'
    INVERT_OFF = GS + b'B\x00'

    # Fonts
    FONT_A = ESC + b'M\x00'  # Normal
    FONT_B = ESC + b'M\x01'  # Monospace / Small

    # Sizes
    TEXT_SIZE_NORMAL = GS + b'!\x00'
    TEXT_SIZE_MEDIUM = GS + b'!\x11'  # 2x width & height
    TEXT_SIZE_LARGE = GS + b'!\x22'   # 3x width & height
    TEXT_SIZE_TITLE = GS + b'!\x33'   # 4x width & height

    # Paper Control
    CUT_PAPER = GS + b'VA\x00'

    @classmethod
    def set_alignment(cls, align: str) -> bytes:
        align = align.lower()
        if align == "center":
            return cls.ALIGN_CENTER
        elif align == "right":
            return cls.ALIGN_RIGHT
        return cls.ALIGN_LEFT

    @classmethod
    def set_text_size(cls, size: str) -> bytes:
        size = size.lower()
        if size == "small":
            return cls.FONT_B + cls.TEXT_SIZE_NORMAL
        elif size == "large":
            return cls.FONT_A + cls.TEXT_SIZE_MEDIUM
        elif size == "title":
            return cls.FONT_A + cls.TEXT_SIZE_LARGE
        return cls.FONT_A + cls.TEXT_SIZE_NORMAL

    @classmethod
    def feed_lines(cls, lines: int = 3) -> bytes:
        return cls.ESC + b'd' + bytes([min(255, max(1, lines))])

    @classmethod
    def build_raster_image(cls, width_px: int, height_px: int, raster_bytes: bytes) -> bytes:
        """
        Build GS v 0 raster bit image command.
        Command format: GS v 0 m xL xH yL yH d1...dk
        where m=0, xL xH is width in bytes, yL yH is height in dots.
        """
        bytes_per_row = (width_px + 7) // 8
        xL = bytes_per_row & 0xFF
        xH = (bytes_per_row >> 8) & 0xFF
        yL = height_px & 0xFF
        yH = (height_px >> 8) & 0xFF

        header = cls.GS + b'v0\x00' + bytes([xL, xH, yL, yH])
        return header + raster_bytes
