"""PaddleOCR as an alternative OCR engine. (Trial: OCR_ENGINE=paddleocr in .env; default tesseract)

paddle_lines(page) -> [{"text", "rect", "confs", "words", "boxes"}]
    The same shape as handwriting.tesseract_lines(), so detection, masking, the invisible
    text layer, click-to-proof highlighting and quote verification work unchanged:
      text   the line's text            rect   its box in PDF points (pymupdf.Rect)
      confs  one 0-100 score per word   words / boxes   the words and their boxes
    PaddleOCR reads whole lines, not words: every word of a line gets the line's score, and
    word boxes are the line box split in proportion to word length (close enough for masking).

warm_up()  load the model now (main.py calls it at startup), not on the first upload.

Settings: PaddleOCR 3.x (predict() -> rec_texts, rec_scores, rec_polys), English mobile
models, document-orientation + text-line-orientation correction for tilted phone photos.
enable_mkldnn=False: PaddlePaddle 3.3's oneDNN CPU path crashes on these models.
"""
import os

import numpy as np
import pymupdf

RENDER_WIDTH_PX = 1600  # big enough for small print, ~10x faster than full resolution
DET_MODEL = "PP-OCRv5_mobile_det"
REC_MODEL = "en_PP-OCRv5_mobile_rec"

_ocr = None


def _model():
    global _ocr
    if _ocr is None:
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")  # models are cached
        from paddleocr import PaddleOCR

        _ocr = PaddleOCR(
            text_detection_model_name=DET_MODEL,
            text_recognition_model_name=REC_MODEL,
            use_doc_orientation_classify=True,  # page rotated 90/180/270
            use_doc_unwarping=False,            # slow, and not needed for flat pages
            use_textline_orientation=True,      # upside-down / tilted lines
            enable_mkldnn=False,
        )
    return _ocr


def warm_up():
    _model()


def _row_order(lines):
    """Reading order: top to bottom, and left to right for lines on the same row
    ("Patient: ..." and "Date: ..." side by side), even when a photo is a little tilted."""
    lines = sorted(lines, key=lambda l: (l["rect"].y0 + l["rect"].y1) / 2)
    rows = []
    for line in lines:
        mid = (line["rect"].y0 + line["rect"].y1) / 2
        if rows and abs(mid - rows[-1]["mid"]) < line["rect"].height / 2:
            rows[-1]["lines"].append(line)
        else:
            rows.append({"mid": mid, "lines": [line]})
    return [l for row in rows for l in sorted(row["lines"], key=lambda l: l["rect"].x0)]


def _word_boxes(rect, words):
    """Split a line box into one box per word, in proportion to word length."""
    total = sum(len(w) for w in words) + len(words) - 1
    boxes, x = [], rect.x0
    for w in words:
        width = rect.width * len(w) / total
        boxes.append(pymupdf.Rect(x, rect.y0, x + width, rect.y1))
        x += width + rect.width / total  # the space after the word
    return boxes


def paddle_lines(page):
    zoom = RENDER_WIDTH_PX / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csRGB, alpha=False)
    rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    result = _model().predict(rgb[:, :, ::-1].copy())[0]  # PaddleOCR expects BGR

    lines = []
    for text, score, poly in zip(result["rec_texts"], result["rec_scores"], result["rec_polys"]):
        words = text.split()
        if not words:
            continue
        pts = np.asarray(poly, dtype=float) / zoom  # 4-point polygon, pixels -> PDF points
        x, y = pts[:, 0].min(), pts[:, 1].min()
        w, h = pts[:, 0].max() - x, pts[:, 1].max() - y   # x, y, width, height box
        rect = pymupdf.Rect(x, y, x + w, y + h)
        conf = round(float(score) * 100, 1)                 # 0-1 -> 0-100, like Tesseract
        lines.append({"text": " ".join(words), "rect": rect, "confs": [conf] * len(words),
                      "words": words, "boxes": _word_boxes(rect, words)})
    return _row_order(lines)
