"""Optional local OCR of scanned PDF pages; source PDF is never modified."""
import os
import shutil
import struct
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


def read_png(body):
    """OCR a bounded PNG funding calendar/map. Preserve the original separately."""
    if len(body) < 24 or body[:8] != b"\x89PNG\r\n\x1a\n":
        return "", ["invalid_png_original_retained"]
    width, height = struct.unpack(">II", body[16:24])
    if not width or not height or width*height > 25_000_000:
        return "", ["image_pixel_limit_original_retained"]
    if not shutil.which("tesseract"):
        return "", ["ocr_engine_unavailable"]
    if int(os.environ.get("FUNDING_OCR_MAX_PAGES", "100")) == 0:
        return "", ["ocr_disabled"]
    try:
        languages = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True,
                                   timeout=10, check=True).stdout.splitlines()
        selected = "+".join(lang for lang in ("fin", "swe", "eng") if lang in languages)
        if not selected:
            return "", ["ocr_languages_unavailable"]
        with TemporaryDirectory(prefix="funding-image-ocr-") as temp:
            path = Path(temp)/"source.png"
            path.write_bytes(body)
            result = subprocess.run(["tesseract", str(path), "stdout", "-l", selected],
                                    capture_output=True, timeout=45, check=True)
        return result.stdout.decode("utf-8", errors="replace").strip(), ["ocr_text_requires_human_verification", "ocr_languages:"+selected]
    except (OSError, subprocess.SubprocessError):
        return "", ["image_ocr_failed_original_retained"]


def read_scan_pages(body, pages):
    maximum = min(200, max(0, int(os.environ.get("FUNDING_OCR_MAX_PAGES", "100"))))
    if not pages or maximum == 0:
        return {}, ["ocr_disabled"]
    if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
        return {}, ["ocr_engine_unavailable"]
    flags, texts = [], {}
    if len(pages) > maximum:
        flags.append("ocr_page_limit:"+str(maximum))
    try:
        available = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True,
                                   timeout=10, check=True).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return {}, ["ocr_language_inventory_failed"]
    languages = "+".join(lang for lang in ("fin", "swe", "eng") if lang in available)
    if not languages:
        return {}, ["ocr_languages_unavailable"]
    flags.extend(["ocr_languages:"+languages, "ocr_text_requires_human_verification"])
    with TemporaryDirectory(prefix="funding-ocr-") as temp:
        directory = Path(temp)
        pdf = directory/"source.pdf"
        pdf.write_bytes(body)
        for page in pages[:maximum]:
            try:
                subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-singlefile",
                                "-scale-to", "2400", "-png", str(pdf), str(directory/"page")],
                               capture_output=True, timeout=40, check=True)
                result = subprocess.run(["tesseract", str(directory/"page.png"), "stdout", "-l", languages],
                                        capture_output=True, timeout=45, check=True)
                text = result.stdout.decode("utf-8", errors="replace").strip()
                if text:
                    texts[page] = text
                else:
                    flags.append("ocr_page_has_no_text:"+str(page))
            except (OSError, subprocess.SubprocessError):
                flags.append("ocr_page_failed:"+str(page))
    return texts, flags
