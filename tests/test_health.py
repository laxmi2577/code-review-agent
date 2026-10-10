from starlette.testclient import TestClient

from src.main import create_app


def test_health_endpoint():
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "index_loaded" in data
    assert isinstance(data["index_loaded"], bool)
    assert "X-Request-ID" in response.headers


def test_health_with_custom_request_id():
    app = create_app()
    client = TestClient(app)

    custom_id = "test-req-id-789"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id


def test_root_endpoint():
    app = create_app()
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "CodeLens"
    assert data["status"] == "online"
    assert data["docs"] == "/docs"

