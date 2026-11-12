"""Make "scanned" copies of the synthetic PDFs, for testing OCR. (Ashil)

Each page is turned into a picture the way a scanner or phone would: lower resolution,
greyscale, a slight tilt, some grain and blur, JPEG compression. The result is an
image-only PDF: it has NO text layer, so the pipeline must OCR it.

The same document always gives the same scan (the random tilt/grain is seeded from the
file name), so test results are repeatable.

Output:  data/scanned/pN/<same filename>.pdf
Run:     python data/make_scans.py            all patients
         python data/make_scans.py p1         only p1
         python data/make_scans.py --photos   phone-style JPG photos of p1's documents in
                                              data/photos/p1/ (page on a desk, tilted, uneven
                                              light, stored sideways with the EXIF rotation
                                              flag phones use)
"""
import io
import os
import random
import sys
import zlib

import pymupdf
from PIL import Image, ImageDraw, ImageFilter

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


PHOTO_DPI = 200
EXIF_ORIENTATION = 0x0112
ROTATE_90_CLOCKWISE_TO_VIEW = 6  # what a phone writes when it was held sideways


def make_photo(src_path, dst_path):
    """A phone photo of the first page: on a desk, tilted, with a shadow across it."""
    rng = random.Random(zlib.crc32(("photo" + os.path.basename(src_path)).encode()))
    pix = pymupdf.open(src_path)[0].get_pixmap(dpi=PHOTO_DPI)
    page = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    desk = Image.new("RGB", (int(page.width * 1.15), int(page.height * 1.12)), (92, 74, 58))
    page = page.rotate(rng.uniform(-3, 3), resample=Image.BICUBIC, expand=True, fillcolor=(92, 74, 58))
    desk.paste(page, ((desk.width - page.width) // 2, (desk.height - page.height) // 2))

    shadow = Image.new("L", desk.size, 0)  # darker towards one corner, like a hand's shadow
    ImageDraw.Draw(shadow).ellipse((-desk.width // 2, desk.height // 2, desk.width, desk.height * 2), fill=70)
    desk = Image.composite(Image.new("RGB", desk.size, (0, 0, 0)), desk, shadow.filter(ImageFilter.GaussianBlur(120)))
    desk = desk.filter(ImageFilter.GaussianBlur(0.6))

    sideways = desk.rotate(90, expand=True)  # the pixels as a phone held sideways stores them
    exif = Image.Exif()
    exif[EXIF_ORIENTATION] = ROTATE_90_CLOCKWISE_TO_VIEW
    sideways.save(dst_path, format="JPEG", quality=82, exif=exif)


def main_photos():
    src_dir = os.path.join(DATA_DIR, "patients", "p1")
    dst_dir = os.path.join(DATA_DIR, "photos", "p1")
    os.makedirs(dst_dir, exist_ok=True)
    for name in sorted(os.listdir(src_dir)):
        if name.endswith(".pdf"):
            make_photo(os.path.join(src_dir, name), os.path.join(dst_dir, name.replace(".pdf", ".jpg")))
    size_kb = sum(os.path.getsize(os.path.join(dst_dir, n)) for n in os.listdir(dst_dir)) // 1024
    print(f"p1: phone-style photos in {dst_dir} ({size_kb} KB)")


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
    if "--photos" in sys.argv:
        main_photos()
    else:
        main(sys.argv[1:] or ["p1", "p2", "p3", "p4", "p5"])
