"""Unit tests for iPrint protocol encoding, packet parsing, and settings model."""

import unittest
from PIL import Image

from backend.protocols.iprint import IPrintProtocol
from backend.models.settings import AppSettings, PrinterConfig


# ------------------------------------------------------------------ #
# CRC-8
# ------------------------------------------------------------------ #

class TestCRC8(unittest.TestCase):

    def test_empty_data(self):
        self.assertEqual(IPrintProtocol.crc8(b""), 0)

    def test_known_sequence(self):
        # CRC must be deterministic.
        crc = IPrintProtocol.crc8(b"\x00\x01\x02\x03")
        self.assertIsInstance(crc, int)
        self.assertIn(crc, range(256))

    def test_consistency(self):
        data = b"hello"
        self.assertEqual(IPrintProtocol.crc8(data), IPrintProtocol.crc8(data))


# ------------------------------------------------------------------ #
# format_message
# ------------------------------------------------------------------ #

class TestFormatMessage(unittest.TestCase):

    def test_magic_bytes(self):
        msg = IPrintProtocol.format_message(0xA1, [0x00])
        self.assertEqual(msg[0], 0x51)
        self.assertEqual(msg[1], 0x78)

    def test_command_byte(self):
        msg = IPrintProtocol.format_message(0xA3, [0x00])
        self.assertEqual(msg[2], 0xA3)

    def test_data_length_encoding(self):
        data = list(range(5))
        msg = IPrintProtocol.format_message(0xA1, data)
        length = msg[4] | (msg[5] << 8)
        self.assertEqual(length, 5)

    def test_terminator(self):
        msg = IPrintProtocol.format_message(0xA1, [0x00])
        self.assertEqual(msg[-1], 0xFF)

    def test_crc_correct(self):
        data = [0x10, 0x20]
        msg = IPrintProtocol.format_message(0xA2, data)
        payload = msg[6:6 + len(data)]
        crc_byte = msg[6 + len(data)]
        self.assertEqual(crc_byte, IPrintProtocol.crc8(bytes(payload)))

    def test_empty_data(self):
        msg = IPrintProtocol.format_message(0xA3, [])
        length = msg[4] | (msg[5] << 8)
        self.assertEqual(length, 0)
        # Should still have magic(2) + cmd(1) + flags(1) + len(2) + crc(1) + term(1) = 8
        self.assertEqual(len(msg), 8)

    def test_large_data(self):
        data = list(range(256))
        msg = IPrintProtocol.format_message(0xA2, data)
        length = msg[4] | (msg[5] << 8)
        self.assertEqual(length, 256)


# ------------------------------------------------------------------ #
# printer_short
# ------------------------------------------------------------------ #

class TestPrinterShort(unittest.TestCase):

    def test_zero(self):
        self.assertEqual(IPrintProtocol.printer_short(0), [0x00, 0x00])

    def test_255(self):
        self.assertEqual(IPrintProtocol.printer_short(255), [0xFF, 0x00])

    def test_256(self):
        self.assertEqual(IPrintProtocol.printer_short(256), [0x00, 0x01])

    def test_default_feed_dots(self):
        result = IPrintProtocol.printer_short(130)
        self.assertEqual(result, [130 & 0xFF, (130 >> 8) & 0xFF])
        self.assertEqual(result, [0x82, 0x00])


# ------------------------------------------------------------------ #
# Feed commands
# ------------------------------------------------------------------ #

class TestFeedCommands(unittest.TestCase):

    def _count_feed_opcodes(self, payload: bytes) -> int:
        """Counts 0xA1 (Feed Paper) packets in the payload."""
        packets = IPrintProtocol.parse_stream(payload)
        return sum(1 for p in packets if p["opcode"] == IPrintProtocol.CMD_FEED_PAPER)

    def test_no_feed(self):
        img = Image.new("1", (384, 2), 1)
        payload = IPrintProtocol.generate_payload(img, feed_lines=0, density=8)
        self.assertEqual(self._count_feed_opcodes(payload), 0)

    def test_small_feed(self):
        img = Image.new("1", (384, 2), 1)
        payload = IPrintProtocol.generate_payload(img, feed_lines=50, density=8)
        self.assertEqual(self._count_feed_opcodes(payload), 1)

    def test_chunked_feed(self):
        img = Image.new("1", (384, 2), 1)
        payload = IPrintProtocol.generate_payload(img, feed_lines=150, density=8)
        # 150 dots → ceil(150/100) = 2 feed packets
        self.assertEqual(self._count_feed_opcodes(payload), 2)

    def test_exact_boundary_feed(self):
        img = Image.new("1", (384, 2), 1)
        payload = IPrintProtocol.generate_payload(img, feed_lines=100, density=8)
        self.assertEqual(self._count_feed_opcodes(payload), 1)

    def test_build_feed_commands_helper(self):
        feed_bytes = IPrintProtocol._build_feed_commands(250)
        packets = IPrintProtocol.parse_stream(feed_bytes)
        self.assertEqual(len(packets), 3)  # 100 + 100 + 50
        self.assertTrue(all(p["opcode"] == IPrintProtocol.CMD_FEED_PAPER for p in packets))

    def test_gray_payload_no_feed(self):
        # Minimal gray data (1 row of 192 bytes).
        gray_rows = bytes(192)
        payload = IPrintProtocol.build_gray_payload(
            gray_rows, energy=4100, speed=40, feed_lines=0
        )
        self.assertEqual(self._count_feed_opcodes(payload), 0)

    def test_gray_payload_with_feed(self):
        gray_rows = bytes(192)
        payload = IPrintProtocol.build_gray_payload(
            gray_rows, energy=4100, speed=40, feed_lines=130
        )
        self.assertGreater(self._count_feed_opcodes(payload), 0)


# ------------------------------------------------------------------ #
# parse_stream round-trip
# ------------------------------------------------------------------ #

class TestParseStream(unittest.TestCase):

    def test_round_trip(self):
        msg = IPrintProtocol.format_message(0xA3, [0x00])
        packets = IPrintProtocol.parse_stream(msg)
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0]["opcode"], 0xA3)
        self.assertTrue(packets[0]["crc_ok"])

    def test_garbage_detected(self):
        stream = b"\xDE\xAD" + IPrintProtocol.format_message(0xA1, [0x10, 0x00])
        packets = IPrintProtocol.parse_stream(stream)
        self.assertEqual(packets[0]["opcode_name"], "garbage")

    def test_truncated_packet(self):
        msg = IPrintProtocol.format_message(0xA2, list(range(48)))
        truncated = msg[:10]  # chop off the end
        packets = IPrintProtocol.parse_stream(truncated)
        self.assertEqual(len(packets), 1)
        self.assertIsNone(packets[0]["crc_ok"])  # can't verify CRC on truncated


# ------------------------------------------------------------------ #
# Settings model
# ------------------------------------------------------------------ #

class TestSettings(unittest.TestCase):

    def test_defaults(self):
        s = AppSettings()
        self.assertEqual(s.printer.tear_bar_feed_dots, 130)
        self.assertEqual(s.printer.auto_feed_mm, 10)
        self.assertEqual(s.printer.density, 8)
        self.assertEqual(s.printer.printable_width_px, 384)

    def test_round_trip(self):
        original = AppSettings()
        data = original.model_dump()
        restored = AppSettings(**data)
        self.assertEqual(original.printer.tear_bar_feed_dots, restored.printer.tear_bar_feed_dots)
        self.assertEqual(original.printer.density, restored.printer.density)
        self.assertEqual(original.image.default_dither, restored.image.default_dither)
        self.assertEqual(original.app.theme, restored.app.theme)

    def test_custom_values_preserved(self):
        s = AppSettings(printer=PrinterConfig(density=5, tear_bar_feed_dots=200))
        data = s.model_dump()
        restored = AppSettings(**data)
        self.assertEqual(restored.printer.density, 5)
        self.assertEqual(restored.printer.tear_bar_feed_dots, 200)


# ------------------------------------------------------------------ #
# Named constants consistency
# ------------------------------------------------------------------ #

class TestNamedConstants(unittest.TestCase):

    def test_width_constants_match(self):
        self.assertEqual(IPrintProtocol.PRINTER_WIDTH_PX, 384)
        self.assertEqual(IPrintProtocol.PRINTER_WIDTH_BYTES, 384 // 8)

    def test_max_feed_chunk(self):
        self.assertEqual(IPrintProtocol.MAX_FEED_CHUNK, 100)

    def test_default_energy(self):
        self.assertEqual(IPrintProtocol.DEFAULT_ENERGY, 17520)
        # ENERGY_MODERATE is the little-endian encoding of 17520 (0x4470)
        le = IPrintProtocol.ENERGY_MODERATE
        self.assertEqual(le[0] | (le[1] << 8), 17520)

    def test_packet_magic(self):
        self.assertEqual(IPrintProtocol.PACKET_MAGIC, bytes([0x51, 0x78]))


if __name__ == "__main__":
    unittest.main()
