"""Provenance registry fail-closed behaviour (T042, FR-002, Principle III)."""

from __future__ import annotations

import shutil

import pytest
import yaml

from backend.app.config import get_settings
from backend.app.errors import ConfigurationError, UnregisteredSourceError
from backend.app.ingestion.registry import load_registry, validate_corpus
from backend.app.models import SourceDocument

VALID_ENTRY = {
    "doc_id": "nice_ng243",
    "document_name": "NICE NG243 - Adrenal insufficiency",
    "filename": "ng243.pdf",
    "publisher": "NICE",
    "publication_year": 2024,
    "source_url": "https://www.nice.org.uk/guidance/ng243",
    "document_type": "guideline",
    "credibility_note": "Statutory NHS guidance body; published openly.",
    "license_note": "(c) NICE 2024, non-commercial educational use.",
}


@pytest.fixture
def corpus(tmp_path):
    """A throwaway corpus with one registered PDF."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "ng243.pdf").write_bytes(b"%PDF-1.4 stub")

    sources = tmp_path / "sources.yaml"
    sources.write_text(yaml.safe_dump({"sources": [VALID_ENTRY]}), encoding="utf-8")

    return get_settings().model_copy(
        update={"corpus_dir": corpus_dir, "sources_file": sources}
    )


class TestFailClosed:
    def test_unregistered_pdf_is_rejected(self, corpus):
        (corpus.corpus_path / "random-download.pdf").write_bytes(b"%PDF-1.4 stub")

        with pytest.raises(UnregisteredSourceError) as exc:
            validate_corpus(corpus)

        assert "random-download.pdf" in str(exc.value)

    def test_registered_corpus_validates(self, corpus):
        documents = validate_corpus(corpus)
        assert [d.doc_id for d in documents] == ["nice_ng243"]

    def test_missing_registered_file_is_reported(self, corpus):
        (corpus.corpus_path / "ng243.pdf").unlink()

        with pytest.raises(ConfigurationError) as exc:
            validate_corpus(corpus)

        assert "ng243.pdf" in str(exc.value)

    def test_missing_registry_file_is_reported(self, corpus):
        corpus.sources_path.unlink()
        with pytest.raises(ConfigurationError):
            load_registry(corpus)

    def test_duplicate_doc_ids_are_rejected(self, corpus):
        corpus.sources_path.write_text(
            yaml.safe_dump({"sources": [VALID_ENTRY, dict(VALID_ENTRY)]}),
            encoding="utf-8",
        )
        with pytest.raises(ConfigurationError, match="Duplicate"):
            load_registry(corpus)


class TestCredibilityValidation:
    @pytest.mark.parametrize("placeholder", ["", "   ", "TODO", "tbd", "n/a", "xxx"])
    def test_placeholder_credibility_note_is_rejected(self, placeholder):
        with pytest.raises(ValueError):
            SourceDocument(**{**VALID_ENTRY, "credibility_note": placeholder})

    def test_doc_id_must_be_a_slug(self):
        with pytest.raises(ValueError):
            SourceDocument(**{**VALID_ENTRY, "doc_id": "NICE NG243!"})


class TestCautionFlagging:
    """FR-003: non-guideline or dated sources must be flagged."""

    def test_current_guideline_needs_no_caution(self):
        doc = SourceDocument(**VALID_ENTRY)
        assert doc.requires_caution(now_year=2026) is False

    def test_non_guideline_type_is_flagged(self):
        doc = SourceDocument(**{**VALID_ENTRY, "document_type": "bulletin"})
        assert doc.requires_caution(now_year=2026) is True

    def test_document_older_than_ten_years_is_flagged(self):
        doc = SourceDocument(**{**VALID_ENTRY, "publication_year": 2003})
        assert doc.requires_caution(now_year=2026) is True

    def test_boundary_exactly_ten_years_is_not_flagged(self):
        doc = SourceDocument(**{**VALID_ENTRY, "publication_year": 2016})
        assert doc.requires_caution(now_year=2026) is False
