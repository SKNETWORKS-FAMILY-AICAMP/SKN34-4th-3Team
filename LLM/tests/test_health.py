from tests.django_client import DjangoTestClient


def test_health_endpoint() -> None:
    response = DjangoTestClient().get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "policy-rag-llm"
    assert body["components"]["data_source"] == "postgres"


def test_test_ui_origin_is_allowed() -> None:
    response = DjangoTestClient().options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
