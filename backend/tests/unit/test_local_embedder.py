"""Unit tests for LocalEmbedder."""

from unittest.mock import MagicMock, patch

import pytest

from backend.app.config import Settings
from backend.app.embeddings.local import LocalEmbedder
from backend.app.errors import EmbeddingProviderError


class TestLocalEmbedder:
    """Tests for LocalEmbedder functionality and error handling."""

    def test_init_properties(self, tmp_path, monkeypatch):
        monkeypatch.delenv("LOCAL_EMBEDDING_MODEL", raising=False)
        monkeypatch.delenv("FALLBACK_EMBEDDING_MODEL", raising=False)
        settings = Settings(
            local_embedding_model="test/dummy-model",
            index_dir=tmp_path,
            _env_file=None,
        )
        embedder = LocalEmbedder(settings=settings)
        assert embedder.model_id == "test/dummy-model"

    def test_embed_documents_empty(self, tmp_path):
        settings = Settings(index_dir=tmp_path)
        embedder = LocalEmbedder(settings=settings)
        assert embedder.embed_documents([]) == []

    def test_embed_documents_mocked(self, tmp_path):
        settings = Settings(index_dir=tmp_path, embedding_batch_size=2)
        embedder = LocalEmbedder(settings=settings, model_name="mock-model")

        mock_st = MagicMock()
        mock_st.get_sentence_embedding_dimension.return_value = 384
        # encode returns list/array
        mock_st.encode.return_value = MagicMock(
            tolist=lambda: [[0.1] * 384, [0.2] * 384]
        )

        with patch.dict("backend.app.embeddings.local._LOCAL_MODEL_CACHE", {"mock-model": mock_st}):
            vectors = embedder.embed_documents(["doc 1", "doc 2"])
            assert len(vectors) == 2
            assert len(vectors[0]) == 384
            assert embedder.dimensions == 384
            assert mock_st.encode.called

    def test_embed_query_with_cache(self, tmp_path):
        settings = Settings(index_dir=tmp_path)
        embedder = LocalEmbedder(settings=settings, model_name="mock-model")

        mock_st = MagicMock()
        mock_st.get_sentence_embedding_dimension.return_value = 384
        mock_st.encode.return_value = MagicMock(
            __getitem__=lambda self, idx: MagicMock(tolist=lambda: [0.5] * 384)
        )

        with patch.dict("backend.app.embeddings.local._LOCAL_MODEL_CACHE", {"mock-model": mock_st}):
            vec1 = embedder.embed_query("What is the hydrocortisone dosage?")
            assert len(vec1) == 384

            # Repeat query should hit cache and not call encode again
            call_count = mock_st.encode.call_count
            vec2 = embedder.embed_query("what is the hydrocortisone dosage?  ")
            assert vec2 == vec1
            assert mock_st.encode.call_count == call_count

    def test_model_load_failure_raises_error(self, tmp_path):
        settings = Settings(index_dir=tmp_path)
        embedder = LocalEmbedder(settings=settings, model_name="non-existent-model")

        mock_module = MagicMock()
        mock_module.SentenceTransformer.side_effect = RuntimeError("Model download blocked")
        with patch.dict("backend.app.embeddings.local._LOCAL_MODEL_CACHE", {}, clear=True):
            with patch.dict("sys.modules", {"sentence_transformers": mock_module}):
                with pytest.raises(EmbeddingProviderError, match="Could not load local embedding model"):
                    embedder.embed_documents(["test text"])
