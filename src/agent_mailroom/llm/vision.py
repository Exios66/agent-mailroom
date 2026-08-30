from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

from agent_mailroom.config.loader import agent_config, taxonomy

log = logging.getLogger(__name__)

IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}


def _vision_config() -> dict:
    cfg = taxonomy().get("vision", {}) or {}
    enabled = bool(cfg.get("enabled", True))
    max_pages = int(cfg.get("max_pages", 10))
    dpi = int(cfg.get("dpi", 150))
    if os.environ.get("MAILROOM_VISION_ENABLED") is not None:
        enabled = os.environ["MAILROOM_VISION_ENABLED"].lower() in ("1", "true", "yes", "on")
    if os.environ.get("MAILROOM_VISION_MAX_PAGES") is not None:
        max_pages = int(os.environ["MAILROOM_VISION_MAX_PAGES"])
    if os.environ.get("MAILROOM_VISION_DPI") is not None:
        dpi = int(os.environ["MAILROOM_VISION_DPI"])
    return {
        "enabled": enabled,
        "max_pages": max_pages,
        "dpi": dpi,
        "models": list(cfg.get("models", []) or []),
    }


def vision_enabled() -> bool:
    return _vision_config()["enabled"]


def max_pages() -> int:
    return _vision_config()["max_pages"]


def is_vision_capable(model: str) -> bool:
    if not vision_enabled() or not model:
        return False
    lowered = model.lower()
    return any(pat.lower() in lowered for pat in _vision_config()["models"])


def agent_uses_vision(agent_name: str) -> bool:
    try:
        cfg = agent_config(agent_name)
        return is_vision_capable(cfg.get("model", ""))
    except Exception:
        return False


def render_pdf_pages(file_path: Path, cap: int | None = None, dpi: int | None = None) -> list[str]:
    if dpi is None:
        dpi = _vision_config()["dpi"]
    try:
        import fitz  # PyMuPDF
    except ImportError:
        log.debug("pymupdf_missing")
        return []
    try:
        doc = fitz.open(str(file_path))
    except Exception:
        log.exception("pdf_open_failed_for_vision", extra={"file": str(file_path)})
        return []
    try:
        page_count = doc.page_count
        limit = page_count if cap is None or cap <= 0 else min(cap, page_count)
        pages: list[str] = []
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        for idx in range(limit):
            try:
                page = doc.load_page(idx)
                pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
                uri = "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode("ascii")
                pages.append(uri)
            except Exception:
                log.exception("pdf_page_render_failed", extra={"page": idx})
        return pages
    finally:
        doc.close()


def render_image(file_path: Path) -> list[str]:
    ext = file_path.suffix.lower()
    mime = IMAGE_MIME.get(ext, "image/jpeg")
    try:
        b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
        return [f"data:{mime};base64,{b64}"]
    except Exception:
        return []


def render_document_pages(file_path: Path) -> list[str]:
    if not vision_enabled():
        return []
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return render_pdf_pages(file_path, cap=_vision_config()["max_pages"])
    if ext in IMAGE_MIME:
        return render_image(file_path)
    return []
