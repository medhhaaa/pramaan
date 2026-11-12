"""Make handwritten-style prescriptions, for testing handwriting reading. (Ashil)

Like a real prescription pad: the clinic letterhead is PRINTED, everything else
(patient details, diagnosis, Rx, advice, signature) is HANDWRITTEN, using Windows
handwriting fonts with wobble, uneven size and blue ink. Then it is "photographed" on a
desk, the same way as make_scans.py --photos.

The content comes from the same document descriptions as the answer keys
(data/generate_docs.py), so results can be scored against data/answer_keys/pN.json.
Real doctors' handwriting is much harder than these fonts: treat the scores as a best case.

Output:  data/handwritten/pN/<prescription filename>.jpg   (only prescriptions)
Run:     python data/make_handwritten.py
Needs Windows fonts: Ink Free, Segoe Print, Bradley Hand, Arial.
"""
import importlib.util
import os
import random
import zlib

from PIL import Image, ImageDraw, ImageFilter, ImageFont

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = "C:/Windows/Fonts"
HANDS = ["Inkfree.ttf", "segoepr.ttf", "BRADHITC.TTF"]  # one "doctor" handwriting per document
PRINTED, PRINTED_BOLD = "arial.ttf", "arialbd.ttf"
DPI = 200
WIDTH, HEIGHT = int(8.27 * DPI), int(11.69 * DPI)  # A4
INK = (25, 45, 140)
MARGIN = 110


def _generator():
    spec = importlib.util.spec_from_file_location("generate_docs", os.path.join(DATA_DIR, "generate_docs.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def _write(page, xy, text, hand, rng):
    """Draw one handwritten line: own size, slight slope, blue ink."""
    font = _font(hand, rng.randint(36, 42))
    box = font.getbbox(text)
    line = Image.new("RGBA", (box[2] + 20, box[3] + 30), (0, 0, 0, 0))
    ImageDraw.Draw(line).text((10, 10), text, font=font, fill=INK + (255,))
    line = line.rotate(rng.uniform(-1.2, 1.2), resample=Image.BICUBIC, expand=True)
    page.paste(line, (xy[0] + rng.randint(-6, 6), xy[1] + rng.randint(-4, 4)), line)


def draw_prescription(doc, hospital, rng):
    page = Image.new("RGB", (WIDTH, HEIGHT), (252, 251, 247))
    draw = ImageDraw.Draw(page)
    hand = rng.choice(HANDS)

    # printed letterhead
    y = 90
    draw.text((MARGIN, y), hospital["name"], font=_font(PRINTED_BOLD, 46), fill=(15, 90, 110))
    y += 64
    for line in hospital["lines"]:
        draw.text((MARGIN, y), line, font=_font(PRINTED, 25), fill=(80, 80, 80))
        y += 34
    draw.line((MARGIN, y + 10, WIDTH - MARGIN, y + 10), fill=(15, 90, 110), width=4)
    y += 50

    # handwritten body
    for item in doc["lines"]:
        kind = item["kind"]
        if kind == "gap":
            y += 25
        elif kind == "rule":
            y += 20
        else:
            _write(page, (MARGIN, y), item["text"], hand, rng)
            if item.get("right"):
                _write(page, (WIDTH // 2 + 60, y), item["right"], hand, rng)
            y += rng.randint(68, 78)

    y += 60
    for line in doc.get("signature", hospital["signature"])[:1]:
        _write(page, (WIDTH - MARGIN - 520, y), line, hand, rng)
    draw.text((MARGIN, HEIGHT - 70), "SYNTHETIC TEST DOCUMENT - generated for the Pramaan demo. Not a real patient.",
              font=_font(PRINTED, 20), fill=(120, 120, 120))
    if y > HEIGHT - 120:
        raise ValueError(f"{doc['filename']} does not fit on the page")
    return page


def photograph(page, rng):
    """Same phone-photo look as make_scans.py: desk, tilt, shadow (kept upright here)."""
    desk = Image.new("RGB", (int(page.width * 1.12), int(page.height * 1.1)), (92, 74, 58))
    page = page.rotate(rng.uniform(-2.5, 2.5), resample=Image.BICUBIC, expand=True, fillcolor=(92, 74, 58))
    desk.paste(page, ((desk.width - page.width) // 2, (desk.height - page.height) // 2))
    shadow = Image.new("L", desk.size, 0)
    ImageDraw.Draw(shadow).ellipse((-desk.width // 2, desk.height // 2, desk.width, desk.height * 2), fill=60)
    desk = Image.composite(Image.new("RGB", desk.size, (0, 0, 0)), desk, shadow.filter(ImageFilter.GaussianBlur(120)))
    return desk.filter(ImageFilter.GaussianBlur(0.5))


def main():
    gen = _generator()
    for patient in gen.PATIENTS:
        pid = patient["patient_id"]
        out_dir = os.path.join(DATA_DIR, "handwritten", pid)
        os.makedirs(out_dir, exist_ok=True)
        for doc in patient["documents"]:
            if doc["doc_type"] != "prescription":
                continue
            rng = random.Random(zlib.crc32(("hand" + pid + doc["filename"]).encode()))
            image = photograph(draw_prescription(doc, gen.HOSPITALS[doc["hospital"]], rng), rng)
            path = os.path.join(out_dir, doc["filename"].replace(".pdf", ".jpg"))
            image.save(path, format="JPEG", quality=85)
            print(f"{pid}_{doc['key']}: {path}")


if __name__ == "__main__":
    main()
