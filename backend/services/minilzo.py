"""
Pure-Python MiniLZO (LZO1X) port.

The iPrint Android app sends grayscale image rows LZO-compressed inside
0xCF chunks; the printer firmware decompresses them with a standard
LZO1X (minilzo) decoder. This module provides:

  * compress(data)  — a clean, valid LZO1X-1 encoder producing streams any
    minilzo decoder accepts (verified against the reference C minilzo)
  * decompress(data) — faithful port of minilzo's lzo1x_decompress
    (reference: minilzo-2.10, LZO1X variant, non-dict path)

LZO1X item layout:
  * leading literal run: first byte > 17 → (b-17) literals
  * control byte < 16            → literal run of (b+3) bytes (long if b==0)
  * control byte 0x10..0x1F      → match, offset = ((b&8)<<11)+(o0>>2)+(o1<<6)+0x4000,
                                    length (b&7)+2 (long form)
  * control byte 0x20..0x3F      → match, 2-byte offset, length (b&31)+2 (long form)
  * control byte >= 0x40         → short match: offset = 1+((b>>2)&7)+(o<<3),
                                    length (b>>5)+1
  * after every match, ip[-2]&3  → 0-3 trailing literal bytes; the next item
    then continues in the match loop (0 trailing just falls through to the
    outer loop, NOT end-of-stream)
  * end-of-stream: match control 0x11 with offset bytes 0x00 0x00
"""

D_BITS = 14
D_SIZE = 1 << D_BITS
D_MASK = D_SIZE - 1

M2_MAX_OFFSET = 0x0800
M3_MAX_OFFSET = 0x4000
M4_MAX_OFFSET = 0xBFFF
M2_MAX_LEN = 8
M3_MAX_LEN = 33
M4_MAX_LEN = 9

M3_MARKER = 32
M4_MARKER = 16


# ── Decompression ────────────────────────────────────────────────────────

def decompress(data: bytes) -> bytes:
    """lzo1x_decompress — faithful port of the reference minilzo C function
    (LZO1X non-dict path). Raises ValueError on malformed input."""
    n = len(data)
    if n == 0:
        raise ValueError("empty LZO input")
    ip = 0
    out = bytearray()

    def need_ip(k: int):
        if ip + k > n:
            raise ValueError("truncated LZO input")

    def long_length(base: int):
        """t += 255 per 0x00 byte, then t += base + final byte."""
        nonlocal ip
        t = 0
        while True:
            need_ip(1)
            b = data[ip]
            ip += 1
            if b != 0:
                break
            t += 255
        return t + base + b

    # Leading literal run (first byte > 17 → t-17 literals).
    need_ip(1)
    t = data[ip]
    ip += 1
    if t > 17:
        t -= 17
        if t < 4:
            # 1..3 leading literals → match_next path: copy, then continue
            # directly with the next control byte in the match loop.
            need_ip(t)
            out += data[ip:ip + t]
            ip += t
            need_ip(1)
            t = data[ip]
            ip += 1
        else:
            need_ip(t)
            out += data[ip:ip + t]
            ip += t
            # first_literal_run: next control byte
            need_ip(1)
            t = data[ip]
            ip += 1
            if t < 16:
                # short first match (offset with 0x800 base, length 3)
                need_ip(1)
                m_pos = len(out) - (1 + M2_MAX_OFFSET) - (t >> 2) - (data[ip] << 2)
                ip += 1
                if m_pos < 0 or m_pos + 3 > len(out):
                    raise ValueError("LZO lookbehind overrun")
                out += out[m_pos:m_pos + 3]
                # match_done: trailing literals
                need_ip(1)
                tr = data[ip - 2] & 3
                if tr:
                    need_ip(tr)
                    out += data[ip:ip + tr]
                    ip += tr
                    need_ip(1)
                    t = data[ip]
                    ip += 1
                else:
                    need_ip(1)
                    t = data[ip]
                    ip += 1
    else:
        # first byte <= 17: no leading run; the outer loop reads it as an item
        pass

    while True:
        # ---- outer loop: literal runs / hand-off to the match loop -------
        if t < 16:
            if t == 0:
                t = long_length(15)
            t += 3
            need_ip(t)
            out += data[ip:ip + t]
            ip += t
            # first_literal_run: next control byte
            need_ip(1)
            t = data[ip]
            ip += 1
            if t < 16:
                # short first match
                need_ip(1)
                m_pos = len(out) - (1 + M2_MAX_OFFSET) - (t >> 2) - (data[ip] << 2)
                ip += 1
                if m_pos < 0 or m_pos + 3 > len(out):
                    raise ValueError("LZO lookbehind overrun")
                out += out[m_pos:m_pos + 3]
                # match_done: trailing literals
                need_ip(1)
                tr = data[ip - 2] & 3
                if tr:
                    need_ip(tr)
                    out += data[ip:ip + tr]
                    ip += tr
                    need_ip(1)
                    t = data[ip]
                    ip += 1
                    continue  # inner loop handles the next control byte
                need_ip(1)
                t = data[ip]
                ip += 1
                continue  # outer loop (t may be a literal run)

        # ---- inner loop: matches -----------------------------------------
        while True:
            if t < 16:
                # 2-byte short match (only appears after trailing literals)
                need_ip(1)
                m_pos = len(out) - 1 - (t >> 2) - (data[ip] << 2)
                ip += 1
                if m_pos < 0 or m_pos + 2 > len(out):
                    raise ValueError("LZO lookbehind overrun")
                out += out[m_pos:m_pos + 2]
                break
            if t >= 64:
                # short match
                need_ip(1)
                m_pos = len(out) - 1 - ((t >> 2) & 7) - (data[ip] << 3)
                ip += 1
                t = (t >> 5) - 1
            elif t >= 32:
                # M3
                t &= 31
                if t == 0:
                    t = long_length(31)
                need_ip(2)
                m_pos = len(out) - 1 - ((data[ip] >> 2) + (data[ip + 1] << 6))
                ip += 2
            else:
                # M4
                m_pos = len(out) - ((t & 8) << 11)
                t &= 7
                if t == 0:
                    t = long_length(7)
                need_ip(2)
                m_pos -= (data[ip] >> 2) + (data[ip + 1] << 6)
                ip += 2
                if m_pos == len(out):
                    # EOF marker (0x11 0x00 0x00)
                    return bytes(out)
                m_pos -= 0x4000
            if m_pos < 0 or m_pos >= len(out):
                raise ValueError("LZO lookbehind overrun")
            for _ in range(t + 2):
                out.append(out[m_pos])
                m_pos += 1
            break

        # ---- match_done: trailing literals --------------------------------
        need_ip(1)
        t = data[ip - 2] & 3
        if t == 0:
            # no trailing literals: back to the outer loop with a new ctrl
            need_ip(1)
            t = data[ip]
            ip += 1
            continue
        need_ip(t)
        out += data[ip:ip + t]
        ip += t
        need_ip(1)
        t = data[ip]
        ip += 1
        # t is the next control byte — the inner loop continues


# ── Compression ──────────────────────────────────────────────────────────

def _hash(p: bytes, pos: int) -> int:
    """LZO-style hash of the 4 bytes at p[pos..pos+3]."""
    d = (p[pos] << 11) ^ ((p[pos + 1] << 5) ^ p[pos + 2]) ^ (p[pos + 3] << 6)
    return (0x21 * d) >> 5 & D_MASK


def compress(data: bytes) -> bytes:
    """
    LZO1X-1 compression. Greedy hash-table matching; output is a valid
    LZO1X stream (verified byte-compatible with the reference minilzo
    lzo1x_decompress, which is what the printer firmware runs).
    """
    n = len(data)
    if n == 0:
        return b"\x11\x00\x00"  # minilzo emits just the EOF marker
    dict_tab = [0] * D_SIZE
    out = bytearray()
    ip = 0
    ii = 0  # start of the pending literal run
    first = True

    def emit_literals(start: int, end: int, first: bool):
        nonlocal out
        t = end - start
        if t <= 0:
            return
        if first and t <= 238:
            out.append(17 + t)
            out += data[start:end]
        elif not first and t <= 3:
            out[-2] |= t  # piggyback on the previous match's control byte
            out += data[start:end]
        elif t <= 18:
            out.append(t - 3)
            out += data[start:end]
        else:
            out.append(0)
            tt = t - 18
            while tt > 255:
                out.append(0)
                tt -= 255
            out.append(tt)
            out += data[start:end]

    def emit_match(m_pos: int, m_len: int):
        nonlocal out
        m_off = ip - m_pos
        if m_len <= M2_MAX_LEN and m_off <= M2_MAX_OFFSET:
            mo = m_off - 1
            out.append(((m_len - 1) << 5) | ((mo & 7) << 2))
            out.append(mo >> 3)
        elif m_off <= M3_MAX_OFFSET:
            mo = m_off - 1
            if m_len <= M3_MAX_LEN:
                out.append(M3_MARKER | (m_len - 2))
            else:
                out.append(M3_MARKER)
                rem = m_len - M3_MAX_LEN
                while rem > 255:
                    out.append(0)
                    rem -= 255
                out.append(rem)
            out.append((mo << 2) & 0xFF)
            out.append((mo >> 6) & 0xFF)
        else:
            mo = m_off - 0x4000
            if m_len <= M4_MAX_LEN:
                out.append(M4_MARKER | ((mo >> 11) & 8) | (m_len - 2))
            else:
                out.append(M4_MARKER | ((mo >> 11) & 8))
                rem = m_len - M4_MAX_LEN
                while rem > 255:
                    out.append(0)
                    rem -= 255
                out.append(rem)
            out.append((mo << 2) & 0xFF)
            out.append((mo >> 6) & 0xFF)

    ip_end = n - 20  # matching loop only while >= 20 bytes remain
    while ip < ip_end:
        dindex = _hash(data, ip)
        # 1-based positions: 0 = empty slot; position 0 stays matchable.
        m_pos = dict_tab[dindex] - 1
        dict_tab[dindex] = ip + 1
        matched = False
        if m_pos >= 0 and 0 < ip - m_pos <= M4_MAX_OFFSET:
            if data[m_pos:m_pos + 4] == data[ip:ip + 4]:
                matched = True
                m_len = 4
                while ip + m_len < n and data[m_pos + m_len] == data[ip + m_len]:
                    m_len += 1
                emit_literals(ii, ip, first)
                first = False
                emit_match(m_pos, m_len)
                ip += m_len
                ii = ip
        if not matched:
            ip += 1

    # tail: remaining bytes become the final literal run
    emit_literals(ii, n, first)
    # EOF marker
    out.append(M4_MARKER | 1)
    out.append(0)
    out.append(0)
    return bytes(out)
