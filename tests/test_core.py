"""Tests for the dependency-free modules (no Streamlit, MySQL, or network needed)."""
import io
import sys
import types
import unittest
import zipfile

# jarvis.ai imports jarvis.config, which only touches streamlit lazily; nothing to stub.
from jarvis.ai import anonymize_text
from jarvis.extract import ExtractError, extract_text
from jarvis.security import AuthError, hash_password, normalize_email, verify_password


class SecurityTests(unittest.TestCase):
    def test_hash_roundtrip(self):
        h = hash_password("correct horse battery")
        self.assertTrue(verify_password("correct horse battery", h))
        self.assertFalse(verify_password("wrong password!!", h))
        self.assertFalse(verify_password("x", "garbage"))

    def test_short_password_rejected(self):
        with self.assertRaises(AuthError):
            hash_password("short")

    def test_email(self):
        self.assertEqual(normalize_email("  A@B.co "), "a@b.co")
        with self.assertRaises(AuthError):
            normalize_email("nope")


class ExtractTests(unittest.TestCase):
    def test_text(self):
        self.assertEqual(extract_text("a.txt", b"hello"), "hello")

    def test_empty_and_bad_type(self):
        with self.assertRaises(ExtractError):
            extract_text("a.txt", b"   ")
        with self.assertRaises(ExtractError):
            extract_text("a.exe", b"x")

    def test_pptx(self):
        ns = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        slide = f'<p {ns}><a:p><a:r><a:t>Mitosis</a:t></a:r></a:p><a:p><a:r><a:t>Phases</a:t></a:r></a:p></p>'
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("ppt/slides/slide2.xml", slide.replace("Mitosis", "Second"))
            z.writestr("ppt/slides/slide1.xml", slide)
        out = extract_text("d.pptx", buf.getvalue())
        self.assertTrue(out.startswith("[Slide 1]\nMitosis\nPhases"))
        self.assertIn("[Slide 2]\nSecond", out)

    def test_bad_pptx(self):
        with self.assertRaises(ExtractError):
            extract_text("d.pptx", b"not a zip")


class AnonymizerTests(unittest.TestCase):
    def test_redacts(self):
        out = anonymize_text("Mail me at a.b@c.com or +91 98765 43210. Name: Asha Rao\nPhoton energy.")
        self.assertNotIn("a.b@c.com", out)
        self.assertNotIn("98765", out)
        self.assertNotIn("Asha", out)
        self.assertIn("Photon energy.", out)


if __name__ == "__main__":
    unittest.main()
