"""Provenance registry — loads and validates data/sources.yaml.

Fail-closed by design: an unregistered PDF aborts ingestion before any parsing
(FR-002). That is what makes Constitution Principle III enforceable rather than
aspirational.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from backend.app.config import Settings, get_settings
from backend.app.errors import ConfigurationError, UnregisteredSourceError
from backend.app.models import SourceDocument


def load_registry(settings: Settings | None = None) -> list[SourceDocument]:
    """Parse and validate the source registry."""
    settings = settings or get_settings()
    path = settings.sources_path

    if not path.exists():
        raise ConfigurationError(f"Source registry not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Could not parse {path}: {exc}") from exc

    entries = raw.get("sources")
    if not entries:
        raise ConfigurationError(f"{path} declares no sources.")

    documents: list[SourceDocument] = []
    for i, entry in enumerate(entries):
        try:
            documents.append(SourceDocument(**entry))
        except ValidationError as exc:
            name = (entry or {}).get("doc_id", f"entry #{i + 1}")
            raise ConfigurationError(f"Invalid registry entry '{name}': {exc}") from exc

    seen: set[str] = set()
    for doc in documents:
        if doc.doc_id in seen:
            raise ConfigurationError(f"Duplicate doc_id in registry: {doc.doc_id}")
        seen.add(doc.doc_id)

    return documents


def list_corpus_pdfs(settings: Settings | None = None) -> list[Path]:
    """Every PDF currently sitting in the corpus directory."""
    settings = settings or get_settings()
    corpus = settings.corpus_path
    if not corpus.exists():
        raise ConfigurationError(f"Corpus directory not found: {corpus}")
    return sorted(p for p in corpus.iterdir() if p.suffix.lower() == ".pdf")


def validate_corpus(settings: Settings | None = None) -> list[SourceDocument]:
    """Load the registry and refuse to proceed if the corpus contains a stranger.

    Raises:
        UnregisteredSourceError: a corpus PDF has no registry entry (FR-002).
        ConfigurationError: a registered document's file is missing.
    """
    settings = settings or get_settings()
    documents = load_registry(settings)

    registered = {doc.filename for doc in documents}
    present = {p.name for p in list_corpus_pdfs(settings)}

    unregistered = sorted(present - registered)
    if unregistered:
        listed = "\n".join(f"  - {name}" for name in unregistered)
        raise UnregisteredSourceError(
            "Unregistered PDF(s) in the corpus directory:\n"
            f"{listed}\n"
            f"Add an entry to {settings.sources_path} or remove the file.\n"
            "Every source must be documented before it can be indexed "
            "(Constitution Principle III)."
        )

    missing = sorted(registered - present)
    if missing:
        listed = "\n".join(f"  - {name}" for name in missing)
        raise ConfigurationError(
            f"Registered document(s) not found in {settings.corpus_path}:\n{listed}"
        )

    return documents
