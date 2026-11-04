#!/usr/bin/env python3
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('prepare', Path(__file__).resolve().parents[1] / 'scripts/prepare-firmware.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class FirmwarePreparation(unittest.TestCase):
    def test_digest_mismatch_preserves_input(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'update.exe'
            source.write_bytes(b'unexpected revision')
            with self.assertRaisesRegex(ValueError, 'unsupported update'):
                prepare.extract_update(source, Path(temp) / 'out')
            self.assertEqual(source.read_bytes(), b'unexpected revision')
            self.assertFalse((Path(temp) / 'out').exists())

    def test_complemented_cab_and_dat_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            header = bytearray(36)
            header[:4] = b'MSCF'
            struct.pack_into('<I', header, 8, len(header))
            source = root / 'update.exe'
            source.write_bytes(b'MZprefix' + bytes(value ^ 255 for value in header) + b'footer')
            def extract(*args):
                (root / 'out/cab').mkdir()
                (root / 'out/cab/FirmwareData_ILCE7M3V404.dat').write_bytes(b'dat')
            with patch.object(prepare, 'EXE_SHA256', prepare.sha256(source)), patch.object(prepare, 'DAT_SHA256', hashlib.sha256(b'dat').hexdigest()), patch.object(prepare, 'run', side_effect=extract):
                result = prepare.extract_update(source, root / 'out')
            self.assertEqual(result.read_bytes(), b'dat')
            self.assertEqual((root / 'out/payload.cab').read_bytes(), header)

    def test_truncated_cab_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'update.exe'
            header = bytearray(36)
            header[:4] = b'MSCF'
            struct.pack_into('<I', header, 8, 4096)
            source.write_bytes(bytes(value ^ 255 for value in header))
            with patch.object(prepare, 'EXE_SHA256', prepare.sha256(source)):
                with self.assertRaisesRegex(ValueError, 'truncated CAB'):
                    prepare.extract_update(source, Path(temp) / 'out')


if __name__ == '__main__':
    unittest.main()
