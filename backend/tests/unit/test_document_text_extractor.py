"""Проверки гибридного извлечения: текстовый слой PDF + OCR сканов."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import document_text_extractor as extractor


class _PdfContext:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_ocr_reconstructs_lines_and_calculates_confidence(monkeypatch):
    data = {
        "text": ["ООО", "Регистр", "ИНН"],
        "block_num": [1, 1, 1],
        "par_num": [1, 1, 1],
        "line_num": [1, 1, 2],
        "conf": ["95", "85", "90"],
    }
    fake_tesseract = SimpleNamespace(
        Output=SimpleNamespace(DICT="dict"),
        pytesseract=SimpleNamespace(tesseract_cmd="tesseract"),
        TesseractNotFoundError=RuntimeError,
        image_to_data=lambda *_args, **_kwargs: data,
    )
    monkeypatch.setattr(extractor, "_OCR_IMPORTS_AVAILABLE", True)
    monkeypatch.setattr(extractor, "pytesseract", fake_tesseract, raising=False)
    monkeypatch.setattr(extractor, "_prepare_image", lambda image: image)
    monkeypatch.setattr(extractor.settings, "OCR_ENABLED", True)

    text, confidence = extractor._ocr_image(object())

    assert text == "ООО Регистр\nИНН"
    assert confidence == pytest.approx(0.885, abs=0.001)


def test_scanned_pdf_page_uses_ocr(monkeypatch):
    page = SimpleNamespace(
        extract_text=lambda: "",
        to_image=lambda **_kwargs: SimpleNamespace(original=object()),
    )
    fake_pdfplumber = SimpleNamespace(open=lambda *_args: _PdfContext([page]))
    monkeypatch.setattr(extractor, "_PDFPLUMBER_AVAILABLE", True)
    monkeypatch.setattr(extractor, "pdfplumber", fake_pdfplumber)
    monkeypatch.setattr(
        extractor, "_ocr_image", lambda _image: ("Распознанный текст", 0.93)
    )

    pages = extractor.extract_pages_from_bytes(b"pdf", "scan.pdf")

    assert pages == [
        extractor.ExtractedPage(
            page_number=1,
            text="Распознанный текст",
            method="ocr",
            ocr_confidence=0.93,
        )
    ]


def test_digital_pdf_does_not_run_ocr(monkeypatch):
    page = SimpleNamespace(extract_text=lambda: "Цифровой текст " * 10)
    fake_pdfplumber = SimpleNamespace(open=lambda *_args: _PdfContext([page]))
    monkeypatch.setattr(extractor, "_PDFPLUMBER_AVAILABLE", True)
    monkeypatch.setattr(extractor, "pdfplumber", fake_pdfplumber)
    monkeypatch.setattr(
        extractor,
        "_ocr_image",
        lambda _image: pytest.fail("OCR не должен запускаться для текстового PDF"),
    )

    pages = extractor.extract_pages_from_bytes(b"pdf", "digital.pdf")

    assert pages[0].method == "pdf_text_layer"
    assert pages[0].ocr_confidence is None


def test_short_text_layer_survives_unavailable_ocr(monkeypatch):
    page = SimpleNamespace(
        extract_text=lambda: "Короткая подпись",
        to_image=lambda **_kwargs: SimpleNamespace(original=object()),
    )
    fake_pdfplumber = SimpleNamespace(open=lambda *_args: _PdfContext([page]))
    monkeypatch.setattr(extractor, "_PDFPLUMBER_AVAILABLE", True)
    monkeypatch.setattr(extractor, "pdfplumber", fake_pdfplumber)
    monkeypatch.setattr(
        extractor,
        "_ocr_image",
        lambda _image: (_ for _ in ()).throw(extractor.NoTextLayerError("нет OCR")),
    )

    pages = extractor.extract_pages_from_bytes(b"pdf", "short.pdf")

    assert pages[0].text == "Короткая подпись"
    assert pages[0].method == "pdf_text_layer"
