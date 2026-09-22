from langchain_core.embeddings import DeterministicFakeEmbedding

import pytest

from src.features import (
    build_vector_index,
)


def test_empty_chunk_collection_is_rejected_before_embedding() -> None:
    with pytest.raises(ValueError, match="At least one RAG chunk"):
        build_vector_index([], embedding=DeterministicFakeEmbedding(size=16))
