#!/usr/bin/env python3
"""A7M3 UI port map. Check real ELFs or apply the same map to copied test fixtures.

python3 scripts/relocate-ui.py --check --reference /path/to/zve10/usr/lib --report work/relocation-report.json
python3 scripts/relocate-ui.py --rewrite tests/test-a7m3-headless.c
Requires the already installed pyelftools and capstone for --check only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
CODE = {
    0x616fe4: 0x5e5dc0,  # WidgetSystem::sys_getInstance, exported anchor
    0x6196b8: 0x5e8490,  # WidgetSystem framebuffer draw
    0x7d5bb0: 0x799790, 0x7d5bd0: 0x7997b0,  # DMP init/exit
    0x7d5bf0: 0x7997d0, 0x7d5c80: 0x799860,  # DMP fill/blit
    0x774ef0: 0x73a100, 0x775120: 0x73a330,  # prepared present/engine wait
    0x775260: 0x73a470, 0x776ad0: 0x73bce0,  # RM executor/scheduler
    0x6fb28c: 0x6bf350, 0x63e170: 0x60ec64,  # VDF update/LZ decoder
    0x848478: 0x80ad58, 0x848160: 0x80aa40,  # Gemini solid/textured rect
    0x847e78: 0x80a758, 0x8485fc: 0x80aedc,  # Gemini quad/line
    0x7c9ba0: 0x78d780,  # GL slow clear
    0x69d145: 0x669dcd, 0x684e6d: 0x64f9b9,  # BMP bpp/physical getter
    0x69b901: 0x668589, 0x69b29d: 0x667f25,  # BitmapImpl read/unlock
    0x6f6cf7: 0x6badbb, 0x6fafb9: 0x6bf07d,  # native display callback/complete
    0x7bbb31: 0x77f711, 0x7bbb41: 0x77f721,  # thread/current GL
    0x7bbbe1: 0x77f7c1, 0x7bbc21: 0x77f801,  # current EGL context/surface
    0x7c0d31: 0x784911, 0x791e91: 0x755a71,  # GL finish/invalidate
    0x862a69: 0x825349, 0x863889: 0x826169,  # image bpp/output lock
    0x86389b: 0x82617b, 0x644df1: 0x6158e1,  # output unlock/image event
}
DATA = {
    0x13ba5a0: 0x124e600,  # N3grm3bmp10BitmapImplE vptr
    0x13bbde0: 0x124f9b0,  # dmpNative::WindowImpl vptr (fixture/reference)
    0x13bf150: 0x1252f90,  # gemini::PlaneTextureMusashi vptr
    0x13bf2e0: 0x1253120,  # gemini::GraphicsContext3DShaderMusashi vptr
    0x13bf558: 0x1253398,  # gemini::GraphicsContext3DMusashi vptr
    0x13bf9b8: 0x12537f8,  # gemini::RenderTargetOGL vptr (fixture/reference)
    0x145cbc8: 0x12f3394,  # graphics singleton pointer, direct native PC reference
    0x145d0f0: 0x12f38b8,  # inline DisplayManager, original GOT getter
    0x145dbb8: 0x12f4380,  # VDF completion callback argument
    0x145dbc0: 0x12f4388,  # VDF completion callback
    0x145dbc4: 0x12f438c,  # VDF completion semaphore
    0x149221c: 0x13289f4,  # exported pViewManager
}
VIEWS = {0x41b6a8: 0x2839a4, 0xbacc50: 0x87d738, 0xbace80: 0x87d930}
MAP = dict(CODE)
MAP.update(DATA)
MAP.update(VIEWS)


def rewrite(path):
    text = path.read_text()
    def replace(match):
        value = int(match[0], 16)
        return hex(MAP[value]) if value in MAP else match[0]
    updated = re.sub(r'0x[0-9a-fA-F]+', replace, text)
    if updated != text:
        path.write_text(updated)
    return {'file': str(path), 'changed': updated != text}


def check(reference, target):
    from elftools.elf.elffile import ELFFile
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_GRP_JUMP, CS_GRP_CALL, CS_GRP_RET
    from capstone.arm import ARM_OP_MEM, ARM_OP_REG, ARM_REG_PC
    class Elf:
        def __init__(self, path):
            self.path = path
            self.stream = path.open('rb')
            self.elf = ELFFile(self.stream)
            assert self.elf.elfclass == 32 and self.elf['e_machine'] == 'EM_ARM'
            self.sections = list(self.elf.iter_sections())
        def read(self, address, size):
            for s in self.sections:
                if s['sh_type'] != 'SHT_NOBITS' and s['sh_addr'] <= address and address + size <= s['sh_addr'] + s['sh_size']:
                    self.stream.seek(s['sh_offset'] + address - s['sh_addr'])
                    return self.stream.read(size)
            raise ValueError(f'unbacked VA {address:#x}')
        def u32(self, address):
            return struct.unpack('<I', self.read(address, 4))[0]
        def typename(self, vptr):
            ti = self.u32(vptr - 4)
            return self.read(self.u32(ti + 4), 160).split(b'\0', 1)[0].decode()
        def symbols(self):
            return {s.name: s['st_value'] for s in self.elf.get_section_by_name('.dynsym').iter_symbols() if s['st_value']}
    old, new = Elf(reference / 'libObj.so'), Elf(target / 'libObj.so')
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    md.detail = True
    findings = []
    for old_v, new_v in DATA.items():
        if 0x13ba000 <= old_v <= 0x13c0000:
            assert old.typename(old_v) == new.typename(new_v)
            findings.append({'old': hex(old_v), 'new': hex(new_v), 'rtti': new.typename(new_v)})
    osym, nsym = old.symbols(), new.symbols()
    for name in ['_ZN2ux6wgtsys12WidgetSystem15sys_getInstanceEv', 'pViewManager', 'GRM_bitmapGetPhysicalAddress']:
        old_v = osym[name]
        actual = nsym[name]
        expected = MAP.get(old_v, MAP.get(old_v & ~1, -1) | (old_v & 1))
        assert actual == expected, (name, hex(actual), hex(expected))
    # Independent native references, not a guessed .bss section delta.
    assert (old.u32(0x63d218) + 0x63d1f6) & 0xffffffff == 0x145cbc8
    assert (new.u32(0x60dd0c) + 0x60dcea) & 0xffffffff == DATA[0x145cbc8]
    assert new.u32(new.u32(0x6b911c) + 0x6b90e0 + new.u32(0x6b9124)) == DATA[0x145d0f0]
    assert new.u32(0x6bf0c4) + 0x6bf0a6 == DATA[0x145dbc0]
    assert new.u32(0x6bf0c8) + 0x6bf0ae == DATA[0x145dbb8]
    assert new.u32(0x6bf3cc) + 0x6bf36e == DATA[0x145dbc4]
    assert new.u32(0x124e600 + 0x44) == CODE[0x69b901]
    assert new.u32(0x124e600 + 0x48) == CODE[0x69b29d]
    assert new.u32(0x1272d84) == CODE[0x6f6cf7]
    source = '\n'.join((ROOT / 'source/ui' / n).read_text() for n in ['ui-observe.c', 'ui-draw-probe.h', 'ui-font-probe.h'])
    hook_re = r'\{(0x[0-9a-f]+),\s*\{((?:\s*0x[0-9a-f]+,?){8})\},\s*([^,]+),\s*([^}]+)\}'
    hooks = []
    for match in re.finditer(hook_re, source):
        address = int(match[1], 16)
        expected = bytes(int(s, 16) for s in re.findall(r'0x[0-9a-f]+', match[2]))
        assert address % 4 == 0 and new.read(address, 8) == expected, hex(address)
        instructions = list(md.disasm(expected, address))
        assert sum(i.size for i in instructions) == 8, f'split Thumb instruction at {address:#x}'
        copied = match[4].strip() != 'NULL'
        if copied:
            for i in instructions:
                assert not any(g in i.groups for g in [CS_GRP_JUMP, CS_GRP_CALL, CS_GRP_RET]), i.op_str
                assert not any((op.type == ARM_OP_MEM and op.mem.base == ARM_REG_PC) or (op.type == ARM_OP_REG and op.reg == ARM_REG_PC) for op in i.operands), i.op_str
        hooks.append({'address': hex(address), 'replacement': match[3].strip(), 'prologue': expected.hex(), 'copies_to_trampoline': copied, 'instructions': [i.mnemonic + ' ' + i.op_str for i in instructions]})
    assert len(hooks) == 14, len(hooks)
    # RM's 12-byte prefix has one literal LDR at +6; pool moves to trampoline+20.
    address = 0x73a470
    expected = bytes.fromhex('2de9f04f87b0c64d04af0446')
    assert new.read(address, 12) == expected
    load = struct.unpack_from('<H', expected, 6)[0]
    assert load & 0xf800 == 0x4800
    literal = new.u32(((address + 10) & ~3) + (load & 255) * 4)
    code = bytearray(expected + bytes.fromhex('dff800f0') + struct.pack('<I', (address + 12) | 1) + struct.pack('<I', literal))
    struct.pack_into('<H', code, 6, (load & 0xff00) | 3)
    relocated = next(md.disasm(code[6:8], 0x100006))
    assert relocated.operands[1].mem.disp + 0x100008 == 0x100014
    assert struct.unpack_from('<I', code, 20)[0] == literal
    ov, nv = Elf(reference / 'viewUnified2.so'), Elf(target / 'viewUnified2.so')
    assert nv.symbols()['ViewRootSelectorToInstance'] & ~1 == VIEWS[0x41b6a8]
    for address in [0xbacc50, 0xbace80]:
        assert ov.typename(address) == nv.typename(VIEWS[address]) == '16ViewRootSelector'
    assert ov.u32(0xbace80 - 8) == (-0x154 & 0xffffffff)
    assert nv.u32(0x87d930 - 8) == (-0x124 & 0xffffffff)
    return {'status': 'static ELF/prologue/trampoline checks passed', 'runtime_verified': False,
        'sha256': {str(e.path): hashlib.sha256(e.path.read_bytes()).hexdigest() for e in [old, new, ov, nv]},
        'code_entries': len(CODE), 'data_entries': len(DATA), 'view_entries': len(VIEWS),
        'map': {hex(k): hex(v) for k, v in sorted(MAP.items())}, 'rtti': findings,
        'hooks': hooks, 'rm_trampoline': {'address': '0x73a470', 'literal': hex(literal), 'bytes': code.hex()}}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--reference', type=Path, help='ZV-E10 reference ELF library directory; required for --check')
    ap.add_argument('--target', type=Path, default=ROOT / 'work/usr/lib')
    ap.add_argument('--rewrite', type=Path, nargs='+', default=[])
    ap.add_argument('--report', type=Path)
    args = ap.parse_args()
    result = {'map': {hex(k): hex(v) for k, v in sorted(MAP.items())}}
    if args.check:
        if args.reference is None:
            ap.error('--check requires --reference pointing to your ZV-E10 ELF libraries')
        result = check(args.reference, args.target)
    if args.rewrite:
        result['rewritten'] = [rewrite(p) for p in args.rewrite]
    output = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.write_text(output)
    else:
        print(output, end='')


if __name__ == '__main__':
    main()
