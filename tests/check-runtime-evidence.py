#!/usr/bin/env python3
"""Verify a saved main/MENU run against its native bytes and original guest log."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('capture', ROOT/'scripts/capture-menu.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('run', type=Path, help='output directory produced by start.sh --smoke')
args = parser.parse_args()
log = (args.run/'serial.log').read_text(errors='replace')
for marker in ['native.main.instance=', 'native.menu.request.return=0x1',
        'input.menu.press=0x15010111', 'input.menu.release=0x15010112',
        'input.key.press=0x15010061', 'input.key.release=0x15010062',
        'GPE.present.completed=0x40000000']:
    assert marker in log, marker
for marker in ['headless.error.', 'UNSUPPORTED', 'unsupported.prologue', 'Kernel panic', 'BUG: Bad page map']:
    assert marker not in log, marker
frames = {}
for label in ['main', 'menu']:
    meta = json.loads((args.run/f'{label}.json').read_text())
    pages = meta['segments']
    capture.validate_segments(dict(meta, segments=len(pages)), pages,
        {'frame': meta['frame'], 'segments': len(pages)})
    raw = (args.run/f'{label}.rgba4444').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == meta['raw_sha256']
    assert capture.fingerprint(raw) == meta['fingerprint_fnv1a64']
    expected = Image.new('RGBA', (640, 480), (0, 0, 0, 255))
    expected.alpha_composite(capture.decode_image(raw))
    png = args.run/f'{label}.png'
    with Image.open(png) as actual:
        assert actual.size == (640, 480)
        assert actual.convert('RGB').tobytes() == expected.convert('RGB').tobytes()
    frames[label] = {key: meta[key] for key in ['frame', 'source_physical', 'raw_sha256', 'fingerprint_fnv1a64']}
    frames[label].update(png_sha256=hashlib.sha256(png.read_bytes()).hexdigest(), segments=len(pages))
assert frames['main']['raw_sha256'] != frames['menu']['raw_sha256']
shutdown = json.loads((args.run/'shutdown.json').read_text())
assert shutdown['process_exited'] is True and type(shutdown['qemu_exit_code']) is int and shutdown['qemu_exit_code'] == 0
print(json.dumps({'native_pixels_verified': True, 'frames': frames, 'qemu_exit_code': 0,
    'shooting_view_created': True, 'complete_shooting_parameters_verified': False,
    'menu_content_requires_visual_review': True, 'capture_verified': False}, indent=2))
