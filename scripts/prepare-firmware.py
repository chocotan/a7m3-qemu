#!/usr/bin/env python3
"""Read the ILCE-7M3 4.04 update as data and prepare emulator filesystems."""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work'
EXE_SHA256 = '8c356688a70946a855191e99fd4d9096a5c3d4263f3f11065605eaea45639d57'
DAT_SHA256 = '7f5c9597ee8ceb5a80255976a6e8cd8035639b4362dd7bd328ca2f6401846bda'
BACKUP = '0110_backup/SYSASTRA-DSLR/TI/CX62200_ALLLANG.bin'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def extract_update(source, destination):
    if sha256(source) != EXE_SHA256:
        raise ValueError('unsupported update package: expected ILCE-7M3 4.04 SHA256')
    destination.mkdir(parents=True, exist_ok=True)
    # Sony Packman stores a standard CAB with each byte complemented.
    raw = source.read_bytes()
    signature = bytes(value ^ 255 for value in b'MSCF')
    start = raw.find(signature)
    if start < 0:
        raise ValueError('missing complemented CAB header')
    header = bytes(value ^ 255 for value in raw[start:start + 36])
    size = struct.unpack_from('<I', header, 8)[0]
    if size < 36 or start + size > len(raw):
        raise ValueError('truncated CAB payload')
    cabinet = destination / 'payload.cab'
    cabinet.write_bytes(raw[start:start + size].translate(bytes.maketrans(bytes(range(256)), bytes(reversed(range(256))))))
    run('7z', 'x', '-y', cabinet, 'FirmwareData_ILCE7M3V404.dat', f'-o{destination / "cab"}')
    dat = destination / 'cab/FirmwareData_ILCE7M3V404.dat'
    if sha256(dat) != DAT_SHA256:
        raise ValueError('firmware DAT digest mismatch')
    return dat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--update', type=Path, default=ROOT / 'Update_ILCE7M3V404.exe')
    parser.add_argument('--fwtool', type=Path, default=WORK / 'fwtool/fwtool.py')
    parser.add_argument('--fwtool-python', default=sys.executable)
    parser.add_argument('--reuse-unpacked', action='store_true', help='validate and use an existing fwtool output')
    args = parser.parse_args()
    for name in ('rootfs', 'usr', 'boot', 'setting', 'tmp'):
        if (WORK / name).exists():
            parser.error(f'work/{name} exists; preserve or rename it before preparing again')
    if sha256(args.update) != EXE_SHA256:
        parser.error('update digest mismatch')
    if not args.reuse_unpacked:
        dat = extract_update(args.update, WORK / 'update')
        run(args.fwtool_python, args.fwtool, 'unpack', '-f', dat, '-o', WORK / 'unpacked')
    else:
        dat = WORK / 'update/cab/FirmwareData_ILCE7M3V404.dat'
        if sha256(dat) != DAT_SHA256:
            parser.error('existing DAT digest mismatch')
    tree = WORK / 'unpacked/firmware.tar_unpacked'
    for partition, name in [('nflasha7', 'rootfs'), ('nflasha15', 'usr')]:
        target = WORK / name
        target.mkdir(parents=True)
        result = subprocess.run(['debugfs', '-R', f'rdump / {target}', str(tree / '0700_part_image/dev' / partition)], capture_output=True, text=True)
        (WORK / f'extract-{name}.log').write_text(result.stderr)
        result.check_returncode()
    run('7z', 'x', '-y', tree / '0700_part_image/dev/nflasha3', f'-o{WORK / "boot"}')
    for name in ('setting', 'tmp'):
        shutil.copytree(tree / '0800_appli' / name, WORK / name, symlinks=True)
    for name in ('Backup.bin', 'Backup.bak'):
        shutil.copy2(tree / BACKUP, WORK / 'setting' / name)
    required = ['rootfs/bin/busybox', 'rootfs/kmod/devno.ko', 'usr/bin/bootin.elf', 'usr/lib/libObj.so', 'usr/lib/libIMDB.so', 'boot/initrd.img', 'setting/DmmConfig.bin']
    for name in required:
        if not (WORK / name).is_file():
            raise RuntimeError(f'incomplete extraction: {name}')
    manifest = {'update_sha256': sha256(args.update), 'dat_sha256': sha256(dat), 'backup_template': BACKUP, 'files': {name: sha256(WORK / name) for name in required}}
    (WORK / 'firmware-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Prepared A7M3 4.04 firmware under', WORK)


if __name__ == '__main__':
    main()
