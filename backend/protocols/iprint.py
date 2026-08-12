import struct
from PIL import Image

class IPrintProtocol:
    """
    Implements the proprietary binary protocol for "iPrint" / "Cat Printers" (GB01, GB02, WalkPrint, FunPrint, etc.)
    Reverse engineered by the community (WerWolv, NaitLee).
    """

    CRC8_TABLE = (
        0x00, 0x07, 0x0e, 0x09, 0x1c, 0x1b, 0x12, 0x15, 0x38, 0x3f, 0x36, 0x31,
        0x24, 0x23, 0x2a, 0x2d, 0x70, 0x77, 0x7e, 0x79, 0x6c, 0x6b, 0x62, 0x65,
        0x48, 0x4f, 0x46, 0x41, 0x54, 0x53, 0x5a, 0x5d, 0xe0, 0xe7, 0xee, 0xe9,
        0xfc, 0xfb, 0xf2, 0xf5, 0xd8, 0xdf, 0xd6, 0xd1, 0xc4, 0xc3, 0xca, 0xcd,
        0x90, 0x97, 0x9e, 0x99, 0x8c, 0x8b, 0x82, 0x85, 0xa8, 0xaf, 0xa6, 0xa1,
        0xb4, 0xb3, 0xba, 0xbd, 0xc7, 0xc0, 0xc9, 0xce, 0xdb, 0xdc, 0xd5, 0xd2,
        0xff, 0xf8, 0xf1, 0xf6, 0xe3, 0xe4, 0xed, 0xea, 0xb7, 0xb0, 0xb9, 0xbe,
        0xab, 0xac, 0xa5, 0xa2, 0x8f, 0x88, 0x81, 0x86, 0x93, 0x94, 0x9d, 0x9a,
        0x27, 0x20, 0x29, 0x2e, 0x3b, 0x3c, 0x35, 0x32, 0x1f, 0x18, 0x11, 0x16,
        0x03, 0x04, 0x0d, 0x0a, 0x57, 0x50, 0x59, 0x5e, 0x4b, 0x4c, 0x45, 0x42,
        0x6f, 0x68, 0x61, 0x66, 0x73, 0x74, 0x7d, 0x7a, 0x89, 0x8e, 0x87, 0x80,
        0x95, 0x92, 0x9b, 0x9c, 0xb1, 0xb6, 0xbf, 0xb8, 0xad, 0xaa, 0xa3, 0xa4,
        0xf9, 0xfe, 0xf7, 0xf0, 0xe5, 0xe2, 0xeb, 0xec, 0xc1, 0xc6, 0xcf, 0xc8,
        0xdd, 0xda, 0xd3, 0xd4, 0x69, 0x6e, 0x67, 0x60, 0x75, 0x72, 0x7b, 0x7c,
        0x51, 0x56, 0x5f, 0x58, 0x4d, 0x4a, 0x43, 0x44, 0x19, 0x1e, 0x17, 0x10,
        0x05, 0x02, 0x0b, 0x0c, 0x21, 0x26, 0x2f, 0x28, 0x3d, 0x3a, 0x33, 0x34,
        0x4e, 0x49, 0x40, 0x47, 0x52, 0x55, 0x5c, 0x5b, 0x76, 0x71, 0x78, 0x7f,
        0x6a, 0x6d, 0x64, 0x63, 0x3e, 0x39, 0x30, 0x37, 0x22, 0x25, 0x2c, 0x2b,
        0x06, 0x01, 0x08, 0x0f, 0x1a, 0x1d, 0x14, 0x13, 0xae, 0xa9, 0xa0, 0xa7,
        0xb2, 0xb5, 0xbc, 0xbb, 0x96, 0x91, 0x98, 0x9f, 0x8a, 0x8d, 0x84, 0x83,
        0xde, 0xd9, 0xd0, 0xd7, 0xc2, 0xc5, 0xcc, 0xcb, 0xe6, 0xe1, 0xe8, 0xef,
        0xfa, 0xfd, 0xf4, 0xf3
    )

    # Commands
    CMD_RETRACT_PAPER = 0xA0
    CMD_FEED_PAPER = 0xA1
    CMD_DRAW_BITMAP = 0xA2
    CMD_GET_DEV_STATE = 0xA3
    CMD_CONTROL_LATTICE = 0xA6
    CMD_GET_DEV_INFO = 0xA8
    CMD_OTHER_FEED_PAPER = 0xBD
    CMD_DRAWING_MODE = 0xBE
    CMD_SET_ENERGY = 0xAF
    CMD_SET_QUALITY = 0xA4

    LATTICE_PRINT = [0xAA, 0x55, 0x17, 0x38, 0x44, 0x5F, 0x5F, 0x5F, 0x44, 0x38, 0x2C]
    LATTICE_FINISH = [0xAA, 0x55, 0x17, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x17]
    SPEED_PRINT = [0x23]
    SPEED_BLANK = [0x19]
    QUALITY_STANDARD = [0x33]
    ENERGY_MODERATE = [0x70, 0x44] # 17500 in little endian 16-bit

    OPCODE_NAMES = {
        0xA0: "Retract Paper",
        0xA1: "Feed Paper",
        0xA2: "Draw Bitmap",
        0xA3: "Get Device State",
        0xA4: "Set Quality",
        0xA6: "Control Lattice",
        0xA8: "Get Device Info",
        0xAF: "Set Energy",
        0xBD: "Other Feed",
        0xBE: "Drawing Mode",
    }

    @classmethod
    def parse_stream(cls, data: bytes, start: int = 0, end: int = None) -> list:
        """
        Parses a concatenated iPrint packet stream into a list of packet dicts:
        {offset, opcode, opcode_name, flags, length, crc_ok, payload_hex}.
        Malformed trailing bytes are reported as a 'garbage' entry so the raw
        stream can be audited (debug view) without guessing.
        """
        if end is None:
            end = len(data)
        packets = []
        i = start
        while i < end:
            remaining = end - i
            if remaining < 8:
                if remaining > 0:
                    packets.append({
                        "offset": i, "opcode": None, "opcode_name": "trailing bytes",
                        "flags": None, "length": None, "crc_ok": None,
                        "payload_hex": data[i:end].hex()
                    })
                break
            if data[i] != 0x51 or data[i + 1] != 0x78:
                # Not a packet boundary: scan forward for the magic.
                j = i + 1
                while j < end - 1 and not (data[j] == 0x51 and data[j + 1] == 0x78):
                    j += 1
                packets.append({
                    "offset": i, "opcode": None, "opcode_name": "garbage",
                    "flags": None, "length": None, "crc_ok": None,
                    "payload_hex": data[i:j].hex()
                })
                i = j
                continue
            opcode = data[i + 2]
            flags = data[i + 3]
            length = data[i + 4] | (data[i + 5] << 8)
            total = 6 + length + 2
            if i + total > end:
                packets.append({
                    "offset": i, "opcode": opcode, "opcode_name": cls.OPCODE_NAMES.get(opcode, "Unknown"),
                    "flags": flags, "length": length, "crc_ok": None,
                    "payload_hex": data[i:end].hex()
                })
                break
            payload = data[i + 6:i + 6 + length]
            crc_byte = data[i + 6 + length]
            packets.append({
                "offset": i,
                "opcode": opcode,
                "opcode_name": cls.OPCODE_NAMES.get(opcode, "Unknown"),
                "flags": flags,
                "length": length,
                "crc_ok": (crc_byte == cls.crc8(payload)),
                "payload_hex": payload.hex()
            })
            i += total
        return packets

    @classmethod
    def crc8(cls, data: bytes) -> int:
        crc = 0
        for byte in data:
            crc = cls.CRC8_TABLE[(crc ^ byte) & 0xFF]
        return crc & 0xFF

    @classmethod
    def format_message(cls, command: int, data: list) -> bytes:
        """
        General message format:
        Magic: 0x51, 0x78
        Command: 1 byte
        Zero: 0x00
        Data length: 1 byte
        Zero: 0x00
        Data: Data Length bytes
        CRC8 of Data: 1 byte
        End: 0xFF
        """
        packet = bytearray([0x51, 0x78, command, 0x00, len(data) & 0xFF, (len(data) >> 8) & 0xFF])
        packet.extend(data)
        packet.append(cls.crc8(bytes(data)))
        packet.append(0xFF)
        return bytes(packet)

    @classmethod
    def split_into_segments(cls, payload: bytes, segment_size: int = 4096) -> list:
        """
        Splits a payload at packet boundaries into whole-packet bursts.
        Each packet is: 6 header bytes + <len> data bytes + 1 crc + 1 terminator.
        Used to let the SC03h firmware drain its buffer between bursts on
        long print jobs, which otherwise silently drop their tail.
        """
        segments = []
        i = 0
        current = bytearray()
        n = len(payload)
        while i < n:
            if n - i < 6:
                current.extend(payload[i:])
                break
            length = payload[i + 4] | (payload[i + 5] << 8)
            packet_len = 6 + length + 2
            if i + packet_len > n:
                packet_len = n - i
            current.extend(payload[i:i + packet_len])
            i += packet_len
            if len(current) >= segment_size:
                segments.append(bytes(current))
                current = bytearray()
        if current:
            segments.append(bytes(current))
        return segments

    @classmethod
    def printer_short(cls, i: int) -> list:
        return [i & 0xFF, (i >> 8) & 0xFF]

    @classmethod
    def generate_payload(cls, image: Image.Image, feed_lines: int = 112, density: int = 8) -> bytes:
        """
        Converts a 1-bit PIL image into the iPrint binary protocol sequence.
        density (1-10) scales the thermal head energy; the default 8 maps to
        the known-good 17500 energy value.
        """
        # Ensure correct format just in case
        if image.mode != "1":
            image = image.convert("1")

        density = max(1, min(10, int(density)))
        energy = [0x70, 0x44]  # 17500 little endian
        if density != 8:
            energy_value = int(17500 * density / 8)
            energy_value = max(0, min(0xFFFF, energy_value))
            energy = [energy_value & 0xFF, (energy_value >> 8) & 0xFF]

        cmdqueue = bytearray()
        
        # 0. Wake up / Get Status
        cmdqueue.extend(cls.format_message(cls.CMD_GET_DEV_STATE, [0x00]))
        
        # 1. Initialize (No 0xA6 Lattice commands as they crash SC03h)
        cmdqueue.extend(cls.format_message(cls.CMD_SET_QUALITY, cls.QUALITY_STANDARD))
        cmdqueue.extend(cls.format_message(cls.CMD_SET_ENERGY, energy))
        cmdqueue.extend(cls.format_message(cls.CMD_DRAWING_MODE, [0]))
        cmdqueue.extend(cls.format_message(cls.CMD_OTHER_FEED_PAPER, cls.SPEED_PRINT))

        # 2. Draw Bitmap
        width_px = image.width
        height_px = image.height
        
        # Note: GB01 / iPrint requires exactly 384 pixels width (48 bytes per line)
        if width_px != 384:
            if width_px > 384:
                # A row wider than 384 dots would produce >48-byte 0xA2 rows
                # (garbled output); center-crop to the printable width instead.
                left = (width_px - 384) // 2
                image = image.crop((left, 0, left + 384, height_px))
            else:
                # Narrower images are centered on a white canvas.
                pad_amount = (384 - width_px) // 2
                padded = Image.new("1", (384, height_px), 1)
                padded.paste(image, (pad_amount, 0))
                image = padded
            width_px = 384

        for y in range(height_px):
            line_bytes = bytearray()
            bit_idx = 0
            current_byte = 0
            
            for x in range(width_px):
                if bit_idx % 8 == 0:
                    current_byte = 0
                
                current_byte >>= 1
                pixel = image.getpixel((x, y))
                if pixel == 0:  # If black
                    current_byte |= 0x80
                    
                if bit_idx % 8 == 7:
                    line_bytes.append(current_byte)
                    
                bit_idx += 1
                
            cmdqueue.extend(cls.format_message(cls.CMD_DRAW_BITMAP, list(line_bytes)))

        # 3. Finish (No Lattice Finish needed)
        
        # 4. Feed Paper
        if feed_lines > 0:
            count = feed_lines
            while count > 0:
                feed = min(count, 100)  # Use 100 dot chunks to prevent firmware signed-int overflows
                cmdqueue.extend(cls.format_message(cls.CMD_FEED_PAPER, cls.printer_short(feed)))
                count -= feed

        return bytes(cmdqueue)
