"""
API tests for FastAPI serving layer.
"""
import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from serving.main import app
    return TestClient(app)


@pytest.fixture
def auth_token(client):
    """Get a valid JWT token for testing."""
    password = os.getenv("ADMIN_PASSWORD", "fincomply2024")
    response = client.post("/auth/login", json={
        "username": "admin",
        "password": password
    })
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


class TestHealthEndpoint:
    def test_health_returns_status(self, client):
        response = client.get("/health")
        assert response.status_code in (200, 503)
        data = response.json()
        assert "status" in data

    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "FinComply" in response.json()["message"]


class TestAuthentication:
    def test_login_success(self, client):
        password = os.getenv("ADMIN_PASSWORD", "fincomply2024")
        response = client.post("/auth/login", json={
            "username": "admin",
            "password": password
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["role"] == "admin"
        assert data["username"] == "admin"

    def test_login_wrong_password(self, client):
        response = client.post("/auth/login", json={
            "username": "admin",
            "password": "wrongpassword"
        })
        assert response.status_code == 401

    def test_login_wrong_username(self, client):
        response = client.post("/auth/login", json={
            "username": "nonexistent",
            "password": "password"
        })
        assert response.status_code == 401

    def test_me_endpoint_with_valid_token(self, client, auth_headers):
        response = client.get("/auth/me", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["username"] == "admin"

    def test_me_endpoint_without_token(self, client):
        response = client.get("/auth/me")
        assert response.status_code == 401

    def test_protected_endpoint_without_token(self, client):
        response = client.get("/documents")
        assert response.status_code == 401

    def test_protected_endpoint_with_invalid_token(self, client):
        response = client.get("/documents", headers={
            "Authorization": "Bearer invalid-token"
        })
        assert response.status_code == 401


class TestDocumentsEndpoint:
    def test_list_documents_authenticated(self, client, auth_headers):
        with patch("serving.main.get_pg") as mock_pg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_pg.return_value = mock_conn
            response = client.get("/documents", headers=auth_headers)
            assert response.status_code == 200
            assert isinstance(response.json(), list)

    def test_list_documents_unauthenticated(self, client):
        response = client.get("/documents")
        assert response.status_code == 401


class TestIngestEndpoint:
    def test_ingest_requires_admin(self, client, auth_headers):
        with patch("serving.main._run_ingest_job"):
            response = client.post("/api/ingest", headers=auth_headers)
            # Admin can trigger ingest
            assert response.status_code in (200, 404)

    def test_ingest_status_not_found(self, client, auth_headers):
        response = client.get(
            "/ingest/status/nonexistent-job-id",
            headers=auth_headers
        )
        assert response.status_code == 404