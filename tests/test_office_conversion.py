"""Offline conversion contract and real LibreOffice smoke tests.

The app runtime does not depend on python-docx or any fixture-generation library.
"""
import hashlib
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from office_conversion import (
    ConversionCancelled, ConversionError, OFFICE_EXTENSIONS,
    _mount_type, _validate_source, cleanup_preview, convert_office_document,
    ram_temp_root,
)

FIXTURES = Path(__file__).parent / 'fixtures' / 'office_library'
LO_AVAILABLE = bool(shutil.which('libreoffice') or shutil.which('soffice'))


class OfficeConversionTests(unittest.TestCase):
    def setUp(self):
        self.root = str(FIXTURES.resolve())
        self.original = str((FIXTURES / 'Office-Demo.docx').resolve())

    def test_supported_types_are_exactly_four(self):
        self.assertEqual(OFFICE_EXTENSIONS, {'.doc', '.docx', '.rtf', '.odt'})
        for extension in OFFICE_EXTENSIONS:
            self.assertTrue((FIXTURES / ('Office-Demo' + extension)).is_file())

    def test_allows_only_current_disc_directory(self):
        self.assertEqual(_validate_source(self.original, self.root), Path(self.original))
        with self.assertRaises(ConversionError):
            _validate_source(self.original, tempfile.gettempdir())

    def test_symlink_disallowed(self):
        with tempfile.TemporaryDirectory() as folder:
            link = Path(folder) / 'Linked.docx'
            link.symlink_to(self.original)
            with self.assertRaises(ConversionError):
                _validate_source(str(link), folder)

    def test_ram_temp_root_is_tmpfs(self):
        self.assertEqual(_mount_type(ram_temp_root()), 'tmpfs')

    def test_stops_if_cancelled_before_start(self):
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(ConversionCancelled):
            convert_office_document(self.original, self.root, cancelled)

    def test_no_disk_fallback(self):
        with patch('office_conversion.ram_temp_root', side_effect=ConversionError('No tmpfs')):
            with self.assertRaisesRegex(ConversionError, 'No tmpfs'):
                convert_office_document(self.original, self.root, binary='/bin/true')

    def test_cancellation_kills_child_and_cleans_ram(self):
        if os.name != 'posix':
            self.skipTest('Linux process groups required')
        with tempfile.TemporaryDirectory() as folder:
            sleeper = Path(folder) / 'pretend-soffice'
            sleeper.write_text('#!/bin/sh\nsleep 10\n')
            sleeper.chmod(0o755)
            before = set(ram_temp_root().glob('discshelf-office-*'))
            cancel = threading.Event()
            def trigger():
                time.sleep(0.35)
                cancel.set()
            thread = threading.Thread(target=trigger, daemon=True)
            thread.start()
            start = time.monotonic()
            with self.assertRaises(ConversionCancelled):
                convert_office_document(self.original, self.root, cancel, binary=str(sleeper))
            self.assertLess(time.monotonic() - start, 4)
            thread.join(2)
            self.assertEqual(set(ram_temp_root().glob('discshelf-office-*')) - before, set())

    @unittest.skipUnless(LO_AVAILABLE, 'LibreOffice required for integration test')
    def test_all_four_format_previews_from_real_writer(self):
        for suffix in ('.docx', '.doc', '.rtf', '.odt'):
            with self.subTest(format=suffix):
                source = FIXTURES / ('Office-Demo' + suffix)
                original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
                result = convert_office_document(str(source.resolve()), self.root)
                try:
                    self.assertTrue(Path(result.pdf_path).is_file())
                    self.assertEqual(Path(result.pdf_path).read_bytes()[:5], b'%PDF-')
                    self.assertEqual(_mount_type(Path(result.pdf_path)), 'tmpfs')
                    self.assertEqual(original_hash, hashlib.sha256(source.read_bytes()).hexdigest())
                finally:
                    cleanup_preview(result.temp_directory)
                self.assertFalse(Path(result.temp_directory).exists())


if __name__ == '__main__':
    unittest.main()
