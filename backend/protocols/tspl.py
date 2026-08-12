class TSPLProtocol:
    """
    TSPL (TSC Printer Language) Protocol Command Generator.
    Used for label printers like Gprinter, Xprinter TSPL models.
    """

    @classmethod
    def initialize(cls, paper_width_mm: int = 58, paper_height_mm: int = 0) -> bytes:
        if paper_height_mm > 0:
            cmd = f"SIZE {paper_width_mm} mm, {paper_height_mm} mm\nCLS\n"
        else:
            cmd = f"SIZE {paper_width_mm} mm, 100 mm\nCLS\n"
        return cmd.encode('ascii')

    @classmethod
    def print_label(cls, copies: int = 1) -> bytes:
        return f"PRINT {copies},1\n".encode('ascii')

    @classmethod
    def text(cls, x: int, y: int, font: str, text_str: str, x_multi: int = 1, y_multi: int = 1) -> bytes:
        return f'TEXT {x},{y},"{font}",0,{x_multi},{y_multi},"{text_str}"\n'.encode('utf-8')

    @classmethod
    def barcode(cls, x: int, y: int, code_type: str, height: int, payload: str) -> bytes:
        return f'BARCODE {x},{y},"{code_type.upper()}",{height},1,0,2,2,"{payload}"\n'.encode('ascii')

    @classmethod
    def qrcode(cls, x: int, y: int, size: int, payload: str) -> bytes:
        return f'QRCODE {x},{y},L,{size},A,0,"{payload}"\n'.encode('utf-8')

    @classmethod
    def bitmap(cls, x: int, y: int, width_bytes: int, height_dots: int, raster_bytes: bytes) -> bytes:
        header = f"BITMAP {x},{y},{width_bytes},{height_dots},0,".encode('ascii')
        return header + raster_bytes + b"\n"
