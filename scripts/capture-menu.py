#!/usr/bin/env python3
"""Validate native frame snapshots; run the main/MENU capture when invoked directly."""
from PIL import Image

SPAN = 640 * 480 * 2


def validate_segments(meta, pages, ready):
    expected = {'width': 640, 'height': 480, 'format': 1, 'bpp': 2,
                'stride': 1280, 'byte_length': SPAN}
    if not all(type(meta.get(k)) is int and meta[k] == v for k, v in expected.items()):
        raise ValueError('Unsupported native capture layout')
    fingerprint = meta.get('fingerprint_fnv1a64')
    if (not isinstance(fingerprint, str) or len(fingerprint) != 16 or
            any(c not in '0123456789abcdef' for c in fingerprint)):
        raise ValueError('Missing native frame fingerprint')
    frame, count = meta.get('frame'), meta.get('segments')
    physical = meta.get('source_physical')
    if (type(frame) is not int or frame <= 0 or type(count) is not int or not 1 <= count <= 151 or
            type(physical) is not int or not 0x20000000 <= physical <= 0x40000000 - SPAN or
            type(ready.get('frame')) is not int or type(ready.get('segments')) is not int or
            ready.get('frame') != frame or ready.get('segments') != count or len(pages) != count):
        raise ValueError('Incomplete native capture publication')
    if any(type(p.get(k)) is not int for p in pages
           for k in ('frame', 'index', 'physical', 'capture_offset', 'length')):
        raise ValueError('Noninteger capture segment')
    ordered = sorted(pages, key=lambda p: p['index'])
    offset = 0
    for index, page in enumerate(ordered):
        physical, length = page['physical'], page['length']
        if (page['frame'] != frame or page['index'] != index or page['capture_offset'] != offset or
                not 0 < length <= 4096 or not 0 <= physical <= 0x40000000 - length or
                (physical & 4095) + length > 4096 or offset + length > SPAN):
            raise ValueError('Invalid, duplicated, or noncontiguous capture segment')
        offset += length
    if offset != SPAN:
        raise ValueError('Truncated capture')
    return ordered


def fingerprint(raw):
    value = 0xcbf29ce484222325
    for byte in raw:
        value = ((value ^ byte) * 0x100000001b3) & 0xffffffffffffffff
    return f'{value:016x}'


def decode_image(raw):
    if len(raw) != SPAN:
        raise ValueError('Truncated RGBA4444 frame')
    if raw == raw[:2] * (SPAN // 2):
        raise ValueError('Published nonuniform frame is uniform')
    rgba = bytearray(SPAN * 2)
    for offset in range(0, SPAN, 2):
        word = raw[offset] | raw[offset + 1] << 8
        rgba[offset * 2:offset * 2 + 4] = bytes(((word >> 12) * 17,
            ((word >> 8) & 15) * 17, ((word >> 4) & 15) * 17, (word & 15) * 17))
    return Image.frombytes('RGBA', (640, 480), bytes(rgba))


if __name__ == '__main__':
    from camera import smoke
    smoke()
