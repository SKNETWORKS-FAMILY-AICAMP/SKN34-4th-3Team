from src.features.elasticsearch_indexing import iter_bulk_actions, nori_index_definition


def test_nori_index_definition_applies_analyzer_to_searchable_text() -> None:
    definition = nori_index_definition()

    tokenizer = definition["settings"]["analysis"]["tokenizer"]["korean_nori_tokenizer"]
    properties = definition["mappings"]["properties"]

    assert tokenizer == {"type": "nori_tokenizer", "decompound_mode": "mixed"}
    assert properties["title"]["analyzer"] == "korean_nori_analyzer"
    assert properties["content"]["analyzer"] == "korean_nori_analyzer"
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
