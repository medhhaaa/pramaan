"""Make "scanned" copies of the synthetic PDFs, for testing OCR. (Ashil)

Each page is turned into a picture the way a scanner or phone would: lower resolution,
greyscale, a slight tilt, some grain and blur, JPEG compression. The result is an
image-only PDF: it has NO text layer, so the pipeline must OCR it.

The same document always gives the same scan (the random tilt/grain is seeded from the
file name), so test results are repeatable.

Output:  data/scanned/pN/<same filename>.pdf
Run:     python data/make_scans.py            all patients
         python data/make_scans.py p1         only p1
"""
import io
import os
import random
import sys
import zlib

import pymupdf
from PIL import Image, ImageFilter

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
SCAN_DPI = 150          # a typical office scan
JPEG_QUALITY = 70


def scan_page(page, rng):
    """Render one PDF page and make it look scanned. Returns JPEG bytes."""
    pix = page.get_pixmap(dpi=SCAN_DPI, colorspace=pymupdf.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)

    img = img.rotate(rng.uniform(-1.2, 1.2), resample=Image.BICUBIC, expand=False, fillcolor=255)
    grain = Image.effect_noise(img.size, rng.uniform(18, 30))
    img = Image.blend(img, grain, 0.08)
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 0.6)))

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


def make_scan(src_path, dst_path):
    rng = random.Random(zlib.crc32(os.path.basename(src_path).encode()))
    src = pymupdf.open(src_path)
    dst = pymupdf.open()
    for page in src:
        new_page = dst.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, stream=scan_page(page, rng))
    dst.save(dst_path, garbage=3, deflate=True)


def main(patient_ids):
    for pid in patient_ids:
        src_dir = os.path.join(DATA_DIR, "patients", pid)
        dst_dir = os.path.join(DATA_DIR, "scanned", pid)
        os.makedirs(dst_dir, exist_ok=True)
        for name in sorted(os.listdir(src_dir)):
            if name.endswith(".pdf"):
                make_scan(os.path.join(src_dir, name), os.path.join(dst_dir, name))
        size_kb = sum(os.path.getsize(os.path.join(dst_dir, n)) for n in os.listdir(dst_dir)) // 1024
        print(f"{pid}: scanned copies in {dst_dir} ({size_kb} KB)")


if __name__ == "__main__":
    main(sys.argv[1:] or ["p1", "p2", "p3", "p4", "p5"])
