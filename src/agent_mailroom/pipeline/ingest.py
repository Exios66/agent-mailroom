from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


def read_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix == ".docx":
        return _read_docx(path)
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raw = path.read_bytes()
        if raw.startswith(b"%PDF"):
            raise RuntimeError("PDF ingest needs pypdf — pip install 'agent-mailroom[pdf]'")
        return raw.decode("utf-8", errors="replace")
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


def _read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    parts = [node.text or "" for node in root.findall(".//w:t", ns)]
    return " ".join(part for part in parts if part).strip()
