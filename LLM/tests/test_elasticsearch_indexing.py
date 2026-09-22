from src.features.elasticsearch_indexing import (
    NORI_SEARCH_STOP_TAGS,
    iter_bulk_actions,
    nori_index_definition,
)


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
