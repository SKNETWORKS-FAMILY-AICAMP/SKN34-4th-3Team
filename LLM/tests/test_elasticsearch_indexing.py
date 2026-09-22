from datetime import UTC, datetime
from fnmatch import fnmatch

import pytest

from src.core.config import Settings
from src.features.elasticsearch_indexing import (
    NORI_SEARCH_STOP_TAGS,
    iter_bulk_actions,
    nori_index_definition,
    reindex_postgres_to_elasticsearch,
)
from src.features import elasticsearch_indexing


def test_nori_index_definition_applies_analyzer_to_searchable_text() -> None:
    definition = nori_index_definition()

    tokenizer = definition["settings"]["analysis"]["tokenizer"]["korean_nori_tokenizer"]
    properties = definition["mappings"]["properties"]

    assert tokenizer == {"type": "nori_tokenizer", "decompound_mode": "mixed"}
    assert "user_dictionary" not in tokenizer
    assert "user_dictionary_rules" not in tokenizer
    pos_filter = definition["settings"]["analysis"]["filter"]["korean_search_pos"]
    assert pos_filter == {
        "type": "nori_part_of_speech",
        "stoptags": list(NORI_SEARCH_STOP_TAGS),
    }
    assert "XPN" not in pos_filter["stoptags"]
    assert "VX" not in pos_filter["stoptags"]
    assert "VCN" not in pos_filter["stoptags"]
    assert "MAG" not in pos_filter["stoptags"]
    assert "MM" not in pos_filter["stoptags"]
    assert "XSN" not in pos_filter["stoptags"]
    assert "XSA" in pos_filter["stoptags"]
    assert "XSV" in pos_filter["stoptags"]
    assert properties["title"]["analyzer"] == "korean_nori_index_analyzer"
    assert properties["title"]["search_analyzer"] == "korean_nori_search_analyzer"
    assert properties["content"]["analyzer"] == "korean_nori_index_analyzer"
    assert properties["content"]["search_analyzer"] == "korean_nori_search_analyzer"
    assert properties["document_id"]["type"] == "keyword"


def test_bulk_action_uses_document_id_as_stable_elasticsearch_id() -> None:
    documents = [
        {
            "document_id": "policy-10",
            "source_type": "policy",
            "source_id": 10,
            "policy_id": 10,
            "title": "청년 창업 지원",
            "source": "db://policies/10",
            "content": "청년 창업자를 지원합니다.",
        }
    ]

    action = next(iter_bulk_actions(documents, "rag-documents-20260919"))

    assert action["_id"] == "policy-10"
    assert action["_index"] == "rag-documents-20260919"
    assert action["_source"]["document_id"] == "policy-10"


class FakeIndices:
    def __init__(self, *, fail_delete: str | None = None) -> None:
        self.data: dict[str, dict] = {}
        self.fail_delete = fail_delete
        self.deleted: list[str] = []

    def create(self, *, index: str, **_kwargs) -> None:
        self.data[index] = {"aliases": {}}

    def refresh(self, *, index: str) -> None:
        assert index in self.data

    def exists_alias(self, *, name: str) -> bool:
        return any(name in entry["aliases"] for entry in self.data.values())

    def get_alias(self, *, name: str) -> dict:
        return {
            index: entry for index, entry in self.data.items()
            if name in entry["aliases"]
        }

    def update_aliases(self, *, actions: list[dict]) -> None:
        for action in actions:
            if "remove" in action:
                item = action["remove"]
                self.data[item["index"]]["aliases"].pop(item["alias"])
            else:
                item = action["add"]
                self.data[item["index"]]["aliases"][item["alias"]] = {}

    def get(self, *, index: str, **_kwargs) -> dict:
        return {
            name: entry for name, entry in self.data.items() if fnmatch(name, index)
        }

    def delete(self, *, index: str) -> None:
        if index == self.fail_delete:
            raise RuntimeError("delete failed")
        self.deleted.append(index)
        del self.data[index]


class FakeElasticsearch:
    def __init__(self, indices: FakeIndices) -> None:
        self.indices = indices

    def options(self, **_kwargs):
        return self


def _run_reindex(monkeypatch, indices: FakeIndices):
    documents = [{"document_id": "policy-1", "content": "정책"}]
    monkeypatch.setattr(
        elasticsearch_indexing, "load_elasticsearch_source_documents",
        lambda _settings: documents,
    )
    monkeypatch.setattr(
        elasticsearch_indexing.helpers,
        "bulk",
        lambda _client, actions, **_kwargs: (len(list(actions)), []),
    )
    return reindex_postgres_to_elasticsearch(
        Settings(_env_file=None), client=FakeElasticsearch(indices),
    )


def test_reindex_removes_previous_and_old_orphan_but_keeps_active_and_other_aliases(
    monkeypatch,
) -> None:
    indices = FakeIndices()
    prefix = "rag-documents-nori-v3-xsv-xsa-"
    previous = f"{prefix}20260919000000000000"
    orphan = f"{prefix}20260918000000000000"
    protected = f"{prefix}20260917000000000000"
    recent = f"{prefix}{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
    indices.data = {
        previous: {"aliases": {"rag-documents": {}}},
        orphan: {"aliases": {}},
        protected: {"aliases": {"evaluation-copy": {}}},
        recent: {"aliases": {}},
        "other-service-index": {"aliases": {}},
    }

    result = _run_reindex(monkeypatch, indices)

    assert set(indices.deleted) == {previous, orphan}
    assert result["index"] in indices.data
    assert indices.get_alias(name="rag-documents") == {
        result["index"]: {"aliases": {"rag-documents": {}}}
    }
    assert protected in indices.data
    assert recent in indices.data
    assert "other-service-index" in indices.data


def test_failed_bulk_keeps_previous_alias_and_removes_incomplete_index(monkeypatch) -> None:
    indices = FakeIndices()
    previous = "rag-documents-nori-v3-xsv-xsa-20260919000000000000"
    orphan = "rag-documents-nori-v3-xsv-xsa-20260918000000000000"
    indices.data[previous] = {"aliases": {"rag-documents": {}}}
    indices.data[orphan] = {"aliases": {}}
    monkeypatch.setattr(
        elasticsearch_indexing, "load_elasticsearch_source_documents",
        lambda _settings: [{"document_id": "policy-1", "content": "정책"}],
    )

    def fail_bulk(_client, _actions, **_kwargs):
        raise RuntimeError("bulk failed")

    monkeypatch.setattr(elasticsearch_indexing.helpers, "bulk", fail_bulk)

    with pytest.raises(RuntimeError, match="bulk failed"):
        reindex_postgres_to_elasticsearch(
            Settings(_env_file=None), client=FakeElasticsearch(indices),
        )

    assert indices.get_alias(name="rag-documents") == {
        previous: {"aliases": {"rag-documents": {}}}
    }
    assert orphan in indices.deleted
    assert len(indices.deleted) == 2
    assert previous not in indices.deleted


def test_cleanup_failure_does_not_fail_successful_alias_switch(monkeypatch, caplog) -> None:
    previous = "rag-documents-nori-v3-xsv-xsa-20260919000000000000"
    indices = FakeIndices(fail_delete=previous)
    indices.data[previous] = {"aliases": {"rag-documents": {}}}

    result = _run_reindex(monkeypatch, indices)

    assert result["index"] in indices.get_alias(name="rag-documents")
    assert previous in indices.data
    assert "Failed to delete unused Elasticsearch index" in caplog.text


def test_ambiguous_alias_update_error_does_not_delete_active_index(monkeypatch) -> None:
    class AmbiguousIndices(FakeIndices):
        def update_aliases(self, *, actions: list[dict]) -> None:
            super().update_aliases(actions=actions)
            raise RuntimeError("response lost after alias update")

    indices = AmbiguousIndices()
    previous = "rag-documents-nori-v3-xsv-xsa-20260919000000000000"
    indices.data[previous] = {"aliases": {"rag-documents": {}}}
    monkeypatch.setattr(
        elasticsearch_indexing, "load_elasticsearch_source_documents",
        lambda _settings: [{"document_id": "policy-1", "content": "정책"}],
    )
    monkeypatch.setattr(
        elasticsearch_indexing.helpers,
        "bulk",
        lambda _client, actions, **_kwargs: (len(list(actions)), []),
    )

    with pytest.raises(RuntimeError, match="response lost"):
        reindex_postgres_to_elasticsearch(
            Settings(_env_file=None), client=FakeElasticsearch(indices),
        )

    active = indices.get_alias(name="rag-documents")
    assert len(active) == 1
    assert next(iter(active)) in indices.data
    assert next(iter(active)) not in indices.deleted
