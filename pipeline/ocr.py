"""OCR for scanned PDFs and photographed documents. (Ashil)

A scanned PDF is only pictures: it has no text layer, so read_pdf() would find nothing.
We use Tesseract (free, runs on our own machine, so no document leaves the server) through
PyMuPDF, which we already use for reading PDFs.

page_has_text(page) -> bool          False for a scanned page
ocr_page_text(page) -> str           the page's text, read by OCR
is_scanned(pdf_path) -> bool         True if any page needs OCR
make_searchable(pdf_bytes) -> bytes  scanned pages get an invisible OCR text layer (like a
                                     scanner app's "searchable PDF"), so click-to-proof can
                                     highlight lines exactly as in a digital PDF. Pages that
                                     already have text are copied unchanged.
image_to_pdf(image_bytes) -> bytes   a photo of a document (JPG/PNG/WEBP...) as a one-page PDF
prepare_document(data) -> bytes      what upload calls: PDF, scanned PDF or photo in, a
                                     searchable PDF out. Anything else raises ValueError.

OCR can misread characters. That is why nothing here is trusted blindly: quote
verification refuses any fact whose numbers differ from the document text, and the
de-identification check is run on OCR output too.

Needs Tesseract installed (Windows: winget install UB-Mannheim.TesseractOCR).
"""
import io

import pymupdf
from PIL import Image, ImageOps, UnidentifiedImageError

OCR_DPI = 300      # Tesseract reads small print best at about 300 dpi
LANGUAGE = "eng"   # add "+kan" for Kannada once its language pack is installed
PAGE_WIDTH = 595   # A4 width in points; a photo's page gets its own height
MAX_IMAGE_SIDE = 4000  # bigger phone photos are shrunk (keeps OCR fast, files small)
UNSUPPORTED = "Please upload a PDF or a photo of the document (JPG, PNG or WEBP)."


def page_has_text(page):
    return bool(page.get_text().strip())


def ocr_page_text(page):
    textpage = page.get_textpage_ocr(language=LANGUAGE, dpi=OCR_DPI, full=True)
    return page.get_text(textpage=textpage)


def is_scanned(pdf_path):
    with pymupdf.open(pdf_path) as doc:
        return any(not page_has_text(page) for page in doc)


def make_searchable(pdf_bytes):
    """Return a PDF that looks the same but has an OCR text layer on scanned pages.
    A PDF that already has text everywhere is returned unchanged."""
    src = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    if all(page_has_text(page) for page in src):
        return pdf_bytes

    out = pymupdf.open()
    for page in src:
        if page_has_text(page):
            out.insert_pdf(src, from_page=page.number, to_page=page.number)
            continue
        # picture of the page + Tesseract's invisible text on top, at the same page size
        # must be RGB: from a greyscale image Tesseract's PDF output silently has no text
        pix = page.get_pixmap(dpi=OCR_DPI, colorspace=pymupdf.csRGB)
        pix.set_dpi(OCR_DPI, OCR_DPI)  # so the new page gets the original size in points
        ocr_pdf = pymupdf.open("pdf", pix.pdfocr_tobytes(language=LANGUAGE, tessdata=pymupdf.get_tessdata()))
        out.insert_pdf(ocr_pdf)
    return out.tobytes(garbage=3, deflate=True)


def image_to_pdf(image_bytes):
    """A photo or scan saved as an image -> a one-page, image-only PDF."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise ValueError(UNSUPPORTED)
    img = ImageOps.exif_transpose(img)  # phones store "rotate me" in EXIF; apply it
    img = img.convert("RGB")
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))  # only ever shrinks

    jpeg = io.BytesIO()
    img.save(jpeg, format="JPEG", quality=90)
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_WIDTH * img.height / img.width)
    page.insert_image(page.rect, stream=jpeg.getvalue())
    return doc.tobytes(garbage=3, deflate=True)


def prepare_document(data):
    """Upload entry point: returns a searchable PDF for a PDF, scanned PDF or photo."""
    if data.startswith(b"%PDF"):
        try:
            pymupdf.open(stream=data, filetype="pdf").close()
        except Exception:
            raise ValueError("This PDF could not be opened. It may be damaged.")
        return make_searchable(data)
    return make_searchable(image_to_pdf(data))
