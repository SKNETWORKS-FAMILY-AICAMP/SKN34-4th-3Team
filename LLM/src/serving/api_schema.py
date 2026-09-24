"""OpenAPI document for the Django HTTP routes."""

from __future__ import annotations

import json

from pydantic import BaseModel

from src.serving import schemas


ROUTES: tuple[tuple[str, str, type[BaseModel] | None, type[BaseModel]], ...] = (
    ("/health", "get", None, schemas.HealthResponse),
    ("/internal/rag/ready", "get", None, schemas.ReadyResponse),
    ("/internal/rag/index", "post", schemas.IndexRequest, schemas.IndexResponse),
    ("/internal/rag/answer", "post", schemas.RagAnswerRequest, schemas.RagAnswerResponse),
    ("/internal/rag/recommendations", "post", schemas.PolicyRecommendationRequest, schemas.PolicyRecommendationResponse),
    ("/rag/ready", "get", None, schemas.ReadyResponse),
    ("/rag/reindex", "post", schemas.RagReindexRequest, schemas.IndexResponse),
    ("/rag/chat", "post", schemas.RagChatRequest, schemas.RagChatResponse),
    ("/rag/legal-basis", "post", schemas.LegalBasisRequest, schemas.LegalBasisResponse),
    ("/rag/deductibility", "post", schemas.DeductibilityRequest, schemas.DeductibilityResponse),
    ("/rag/summarize-announcement", "post", schemas.AnnouncementSummaryRequest, schemas.AnnouncementSummaryResponse),
    ("/rag/business-plan", "post", schemas.BusinessPlanRequest, schemas.BusinessPlanResponse),
    ("/rag/business-plan-refine", "post", schemas.BusinessPlanRefineRequest, schemas.BusinessPlanRefineResponse),
    ("/rag/business-plan-template-inspect", "post", schemas.BusinessPlanTemplateRequest, schemas.BusinessPlanTemplateResponse),
    ("/rag/business-plan-render", "post", schemas.BusinessPlanRenderRequest, schemas.BusinessPlanRenderResponse),
    ("/rag/business-plan-coach", "post", schemas.BizplanCoachRequest, schemas.BizplanCoachResponse),
    ("/rag/business-plan-evaluate", "post", schemas.BusinessPlanEvaluateRequest, schemas.BusinessPlanEvaluateResponse),
    ("/ocr/receipt", "post", None, schemas.ReceiptExtractionResponse),
)


def openapi_document() -> dict:
    components: dict[str, dict] = {}
    paths: dict[str, dict] = {}
    for path, method, request_model, response_model in ROUTES:
        operation: dict = {
            "operationId": f"{method}_{path.strip('/').replace('/', '_').replace('-', '_')}",
            "responses": {
                "200": {
                    "description": "Successful response",
                    "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{response_model.__name__}"}}},
                },
                "default": {
                    "description": "Error response",
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}},
                },
            },
        }
        if request_model is not None:
            operation["requestBody"] = {
                "required": path not in {"/internal/rag/index", "/rag/reindex"},
                "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{request_model.__name__}"}}},
            }
            _add_model(components, request_model)
        elif path == "/ocr/receipt":
            operation["requestBody"] = {
                "required": True,
                "content": {"multipart/form-data": {"schema": {
                    "type": "object", "required": ["image"],
                    "properties": {"image": {"type": "string", "format": "binary"}},
                }}},
            }
        _add_model(components, response_model)
        paths.setdefault(path, {})[method] = operation
    components["ErrorResponse"] = {
        "type": "object", "required": ["error"],
        "properties": {"error": {"type": "object", "required": ["code", "message", "retryable"],
            "properties": {"code": {"type": "string"}, "message": {"type": "string"}, "retryable": {"type": "boolean"}}}},
    }
    return {
        "openapi": "3.1.0",
        "info": {"title": "Policy RAG LLM API", "version": "0.1.0"},
        "paths": paths,
        "components": {"schemas": components},
    }


def _add_model(components: dict[str, dict], model: type[BaseModel]) -> None:
    schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
    schema = json.loads(json.dumps(schema).replace("#/$defs/", "#/components/schemas/"))
    components.update(schema.pop("$defs", {}))
    components[model.__name__] = schema
