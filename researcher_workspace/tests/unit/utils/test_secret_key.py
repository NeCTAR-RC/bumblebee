import os
import tempfile
from unittest import TestCase

from researcher_workspace.utils import secret_key


class SecretKeyTests(TestCase):

    def test_generate_key_default_length(self):
        key = secret_key.generate_key()
        self.assertEqual(64, len(key))

    def test_generate_key_custom_length(self):
        key = secret_key.generate_key(key_length=10)
        self.assertEqual(10, len(key))
        # only digits and ASCII letters
        for ch in key:
            self.assertTrue(ch.isalnum())

    def test_generate_or_read_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".secret")
            key = secret_key.generate_or_read_from_file(
                key_file=path, key_length=32)
            self.assertEqual(32, len(key))
            self.assertTrue(os.path.exists(path))
            # mode is 0600
            mode = os.stat(path).st_mode & 0o777
            self.assertEqual(0o600, mode)

    def test_generate_or_read_reuses_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".secret")
            first = secret_key.generate_or_read_from_file(key_file=path)
            second = secret_key.generate_or_read_from_file(key_file=path)
            self.assertEqual(first, second)

    def test_read_from_file_bad_perms(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".secret")
            with open(path, "w") as f:
                f.write("abcdefg")
            os.chmod(path, 0o644)
            with self.assertRaises(secret_key.FilePermissionError):
                secret_key.read_from_file(key_file=path)

    def test_read_from_file_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".secret")
            with open(path, "w") as f:
                f.write("secretvalue")
            os.chmod(path, 0o600)
            self.assertEqual("secretvalue",
                             secret_key.read_from_file(key_file=path))
