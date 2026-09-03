import zipfile
from xml.etree.ElementTree import Element, SubElement, tostring

from agent_mailroom.pipeline.intake import read_document
from agent_mailroom.pipeline.runner import run_document


NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _write_docx(path, paragraphs: list[str]) -> None:
    document = Element("{%s}document" % NS)
    body = SubElement(document, "{%s}body" % NS)
    for line in paragraphs:
        para = SubElement(body, "{%s}p" % NS)
        run = SubElement(para, "{%s}r" % NS)
        text = SubElement(run, "{%s}t" % NS)
        text.text = line
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", tostring(document))


def test_read_plain_text(samples):
    text = read_document(samples / "harborpoint_msa.txt")
    assert "MASTER SERVICES AGREEMENT" in text


def test_read_docx(tmp_path):
    path = tmp_path / "brief.docx"
    _write_docx(
        path,
        [
            "MASTER SERVICES AGREEMENT",
            "NOW, THEREFORE, the parties agree.",
            "Governing Law. Delaware.",
            "IN WITNESS WHEREOF the parties sign.",
        ],
    )
    text = read_document(path)
    assert "MASTER SERVICES AGREEMENT" in text
    assert "Delaware" in text


def test_docx_runs_pipeline(tmp_path):
    path = tmp_path / "msa.docx"
    _write_docx(
        path,
        [
            "MASTER SERVICES AGREEMENT",
            "This Master Services Agreement is dated January 1, 2026",
            "by HarborPoint Holdings, Inc. and Northwind Logistics Corporation.",
            "NOW, THEREFORE, in consideration of the mutual covenants herein,",
            "Governing Law. This Agreement is governed by the laws of the State of Delaware.",
            "IN WITNESS WHEREOF the parties have executed this Agreement.",
        ],
    )
    state = run_document(path, matter_id="DOCX-1")
    assert state.doc_type == "contract"
    assert state.stage == "archived"


def test_pdf_ingest_path(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
    try:
        import pypdf  # noqa: F401
    except ImportError:
        try:
            read_document(path)
        except RuntimeError as exc:
            assert "pypdf" in str(exc)
        else:
            raise AssertionError("expected RuntimeError when pypdf is missing")
    else:
        assert isinstance(read_document(path), str)
