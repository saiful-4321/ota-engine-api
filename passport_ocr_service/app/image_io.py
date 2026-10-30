"""Decodes uploaded bytes (JPEG / PNG / WEBP / TIFF / HEIC / PDF) into OpenCV images, in memory only."""

import io
import warnings
from typing import List

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

# Reject decompression bombs (tiny file, gigantic pixel count): 60 MP covers any real passport photo
Image.MAX_IMAGE_PIXELS = 60_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)

MAX_PDF_PAGES = 3
_MAX_SIDE = 4000  # downscale huge camera images before processing


class UnsupportedFile(ValueError):
    pass


def _from_pil(img: Image.Image) -> np.ndarray:
    img = ImageOps.exif_transpose(img)  # honour phone camera orientation
    img = img.convert("RGB")
    if max(img.size) > _MAX_SIDE:
        img.thumbnail((_MAX_SIDE, _MAX_SIDE))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def load_images(data: bytes) -> List[np.ndarray]:
    if not data:
        raise UnsupportedFile("Empty file")

    if data[:5] == b"%PDF-":
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise UnsupportedFile(f"Unreadable PDF: {exc}") from exc
        pages = []
        if doc.is_encrypted:
            raise UnsupportedFile("Password-protected PDFs are not supported")
        for page in list(doc)[:MAX_PDF_PAGES]:
            pix = page.get_pixmap(dpi=300)
            pages.append(_from_pil(Image.open(io.BytesIO(pix.tobytes("png")))))
        if not pages:
            raise UnsupportedFile("PDF has no pages")
        return pages

    try:
        return [_from_pil(Image.open(io.BytesIO(data)))]
    except Exception as exc:
        raise UnsupportedFile("Unsupported or corrupt image. Use JPEG, PNG, WEBP, TIFF, HEIC or PDF.") from exc
