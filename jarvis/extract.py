"""Text extraction from uploads. Pure stdlib + pypdf; OCR shells out to tesseract/pdftoppm.

Uploads are processed in memory or in a throwaway temp directory that is deleted on exit.
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".txt", ".md", ".csv"}
_IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
MAX_CHARS = 300_000
MAX_PAGES = 60
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


class ExtractError(Exception):
    """Safe, user-presentable extraction failure."""


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    if shutil.which(cmd[0]) is None:
        raise ExtractError(f"OCR tool '{cmd[0]}' is not installed on the server (see packages.txt).")
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout, check=True)
    except subprocess.TimeoutExpired as exc:
        raise ExtractError("OCR timed out.") from exc
    except subprocess.CalledProcessError as exc:
        raise ExtractError("OCR failed on this file.") from exc


def _ocr_image(path: Path) -> str:
    return _run(["tesseract", str(path), "stdout", "-l", "eng", "--oem", "3", "--psm", "3"]).stdout.decode(
        "utf-8", "replace"
    )


def _pptx(data: bytes) -> str:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        slides = sorted(
            (n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
            key=lambda n: int(re.search(r"(\d+)\.xml", n).group(1)),
        )
        parts: list[str] = []
        for i, name in enumerate(slides[:MAX_PAGES], start=1):
            if zf.getinfo(name).file_size > 5_000_000:  # zip-bomb guard
                continue
            root = ET.fromstring(zf.read(name))
            paras = ["".join(t.text or "" for t in p.iter(f"{_A}t")) for p in root.iter(f"{_A}p")]
            body = "\n".join(p for p in paras if p.strip())
            if body:
                parts.append(f"[Slide {i}]\n{body}")
        return "\n\n".join(parts)
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
        raise ExtractError("Could not read this PowerPoint file.") from exc


def _pdf(data: bytes, workdir: Path) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        n_pages = min(len(reader.pages), MAX_PAGES)
        pages: list[str] = []
        pdf_path = workdir / "in.pdf"
        for i in range(n_pages):
            text = (reader.pages[i].extract_text() or "").strip()
            if len(text) < 20:  # scanned page: rasterize just this page and OCR it
                if not pdf_path.exists():
                    pdf_path.write_bytes(data)
                prefix = workdir / f"p{i}"
                _run(["pdftoppm", "-f", str(i + 1), "-l", str(i + 1), "-r", "200", "-png", str(pdf_path), str(prefix)])
                imgs = sorted(workdir.glob(f"p{i}*.png"))
                text = _ocr_image(imgs[0]).strip() if imgs else ""
            if text:
                pages.append(f"[Page {i + 1}]\n{text}")
            if sum(map(len, pages)) >= MAX_CHARS:
                break
        return "\n\n".join(pages)
    except ExtractError:
        raise
    except Exception as exc:
        raise ExtractError("Could not read this PDF.") from exc


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ExtractError(f"Unsupported file type: {suffix or 'none'}")
    with tempfile.TemporaryDirectory(prefix="jarvis_") as tmp:
        work = Path(tmp)
        if suffix in {".txt", ".md", ".csv"}:
            text = data.decode("utf-8-sig", errors="replace")
        elif suffix == ".pptx":
            text = _pptx(data)
        elif suffix == ".pdf":
            text = _pdf(data, work)
        else:
            img = work / f"img{suffix}"
            img.write_bytes(data)
            text = _ocr_image(img)
    text = text.strip()[:MAX_CHARS]
    if not text:
        raise ExtractError("No readable text was found in this file.")
    return text
