"""The photo a person uploaded, kept as evidence next to the working PDF. (Ashil)

original_image(data) -> (bytes, mime) | None
    For a photo upload (JPG, PNG, WEBP): the same picture with its hidden metadata removed.
    For a PDF or anything else: None (the stored PDF already is the original).

The upload pipeline turns a photo into a searchable PDF (pipeline/ocr.py image_to_pdf: rotated,
maybe shrunk, re-saved as JPEG) because line numbers, quote checks and search work on that PDF.
A doctor verifying a handwritten prescription needs the photo itself, so it is kept too
(backend/ingest.py, encrypted like every stored file) and shown in Source.

What is removed: everything a phone writes about the photo, not the picture: GPS location,
phone make / model, time taken, owner name, XMP / IPTC / comments, the embedded thumbnail
(it can still show the uncropped image). The rotation tag is kept, so the photo still shows
upright, matching the PDF page and the line boxes drawn on it.

JPEG (almost every phone photo): done byte by byte, so the image data is NOT re-compressed;
the decoded pixels are identical. PNG / WEBP: saved again without metadata, losslessly (same
pixels). If a JPEG's structure can't be walked, it is saved again at quality 95 (rare).
"""
import io
import struct

from PIL import Image, ImageOps, UnidentifiedImageError

ORIENTATION = 0x0112
MIME = {"JPEG": "image/jpeg", "MPO": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
EXTENSION = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def original_image(data):
    if data.startswith(b"%PDF"):
        return None
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        orientation = img.getexif().get(ORIENTATION, 1)
    except (UnidentifiedImageError, OSError):
        return None
    if fmt not in MIME:
        return None
    if fmt in ("JPEG", "MPO"):
        try:
            return jpeg_without_metadata(data, orientation), "image/jpeg"
        except (ValueError, IndexError, struct.error):
            pass  # not a structure we can walk: save it again below
    img.load()
    img = ImageOps.exif_transpose(img)  # the rotation is applied, so no tag is needed
    out = io.BytesIO()
    if fmt == "PNG":
        img.save(out, format="PNG")
    elif fmt == "WEBP":
        img.save(out, format="WEBP", lossless=True)
    else:
        img.convert("RGB").save(out, format="JPEG", quality=95)
    return out.getvalue(), MIME[fmt]


def _orientation_segment(orientation):
    exif = Image.Exif()
    exif[ORIENTATION] = orientation
    payload = exif.tobytes()  # b"Exif\0\0" + a TIFF block holding only the rotation
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def jpeg_without_metadata(data, orientation=1):
    """Copy a JPEG segment by segment, leaving out APP1-APP15 (EXIF, XMP, IPTC, maker notes)
    and comments, but keeping the colour profile (APP2 ICC_PROFILE). The compressed image
    data after the start-of-scan marker is copied unchanged, up to the end-of-image marker
    (an iPhone MPO's second picture, with its own metadata, comes after it and is dropped)."""
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("not a JPEG")
    kept = []
    i = 2
    while True:
        if data[i] != 0xFF:
            raise ValueError("bad JPEG marker")
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker == 0xDA:  # start of scan: from here on it is image data
            end = data.find(b"\xff\xd9", i)
            if end < 0:
                raise ValueError("JPEG has no end marker")
            scan = data[i:end + 2]
            break
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:  # markers without a length
            kept.append(data[i:i + 2])
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        segment = data[i:i + 2 + length]
        if len(segment) < 2 + length:
            raise ValueError("JPEG segment cut short")
        icc = marker == 0xE2 and segment[4:16] == b"ICC_PROFILE\x00"
        if not (0xE1 <= marker <= 0xEF or marker == 0xFE) or icc:
            kept.append(segment)
        i += 2 + length

    if orientation and orientation != 1:
        # after the JFIF header (APP0) if there is one, where readers expect EXIF
        at = 1 if kept and kept[0][:2] == b"\xff\xe0" else 0
        kept.insert(at, _orientation_segment(orientation))
    return b"\xff\xd8" + b"".join(kept) + scan
