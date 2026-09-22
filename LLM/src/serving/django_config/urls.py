"""Preserve the existing LLM HTTP paths while moving the server to Django."""

from django.urls import path

from src.serving import django_views as views


urlpatterns = [
    path("docs", views.docs),
    path("openapi.json", views.openapi),
    path("health", views.health),
    path("internal/rag/ready", views.internal_ready),
    path("internal/rag/index", views.internal_index),
    path("internal/rag/answer", views.internal_answer),
    path("internal/rag/recommendations", views.internal_recommendations),
    path("rag/ready", views.public_ready),
    path("rag/reindex", views.public_reindex),
    path("rag/chat", views.public_chat),
    path("rag/legal-basis", views.public_legal_basis),
    path("rag/deductibility", views.public_deductibility),
    path("rag/summarize-announcement", views.public_summarize_announcement),
    path("rag/business-plan", views.public_business_plan),
    path("rag/business-plan-coach", views.public_business_plan_coach),
    path("rag/business-plan-evaluate", views.public_business_plan_evaluate),
    path("ocr/receipt", views.receipt_ocr),
]

handler404 = views.page_not_found
handler500 = views.server_error
