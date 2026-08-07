"""API tests for `/auth/*` endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.identity_access.conftest import auth_header, login, register, register_and_login


class TestRegister:
    def test_returns_201_with_user_shape(self, client: TestClient) -> None:
        response = register(client)

        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "alice@example.com"
        assert body["full_name"] == "Alice Example"
        assert body["role"] == "member"
        assert body["is_active"] is True
        assert "id" in body

    def test_never_returns_the_password(self, client: TestClient) -> None:
        response = register(client)

        assert "password" not in response.json()
        assert "hashed_password" not in response.json()

    def test_duplicate_email_returns_409_rfc7807(self, client: TestClient) -> None:
        register(client)

        response = register(client)

        assert response.status_code == 409
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["type"].endswith("/user-already-exists")

    def test_invalid_email_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "ValidPass123", "full_name": "X"},
        )

        assert response.status_code == 422
        assert "errors" in response.json()

    def test_short_password_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "x@example.com", "password": "short", "full_name": "X"},
        )

        assert response.status_code == 422


class TestLogin:
    def test_correct_credentials_return_token_pair(self, client: TestClient) -> None:
        register(client)

        response = login(client, email="alice@example.com", password="AlicePass123")

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["expires_in"] > 0

    def test_wrong_password_returns_401_rfc7807(self, client: TestClient) -> None:
        register(client)

        response = login(client, email="alice@example.com", password="WrongPassword")

        assert response.status_code == 401
        assert response.json()["type"].endswith("/invalid-credentials")
        assert response.headers["www-authenticate"] == "Bearer"

    def test_unknown_email_returns_401(self, client: TestClient) -> None:
        response = login(client, email="nobody@example.com", password="Whatever123")

        assert response.status_code == 401


class TestRefresh:
    def test_valid_refresh_token_returns_new_pair(self, client: TestClient) -> None:
        tokens = register_and_login(client)

        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

        assert response.status_code == 200
        new_tokens = response.json()
        assert new_tokens["refresh_token"] != tokens["refresh_token"]

    def test_reusing_a_rotated_token_returns_401(self, client: TestClient) -> None:
        tokens = register_and_login(client)
        client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

        assert response.status_code == 401
        assert response.json()["type"].endswith("/token-revoked")

    def test_garbage_token_returns_401(self, client: TestClient) -> None:
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage"})

        assert response.status_code == 401

    def test_access_token_used_as_refresh_returns_401(self, client: TestClient) -> None:
        tokens = register_and_login(client)

        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
        )

        assert response.status_code == 401


class TestLogout:
    def test_logout_returns_204(self, client: TestClient) -> None:
        tokens = register_and_login(client)

        response = client.post(
            "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        )

        assert response.status_code == 204

    def test_logged_out_refresh_token_can_no_longer_refresh(self, client: TestClient) -> None:
        tokens = register_and_login(client)
        client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})

        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

        assert response.status_code == 401

    def test_logout_with_unknown_token_still_returns_204(self, client: TestClient) -> None:
        response = client.post("/api/v1/auth/logout", json={"refresh_token": "unknown"})

        assert response.status_code == 204


class TestAuthenticatedFlowSmoke:
    def test_full_flow_register_login_me(self, client: TestClient) -> None:
        tokens = register_and_login(client)

        response = client.get("/api/v1/users/me", headers=auth_header(tokens))

        assert response.status_code == 200
        assert response.json()["email"] == "alice@example.com"

    def test_no_token_returns_401_rfc7807(self, client: TestClient) -> None:
        response = client.get("/api/v1/users/me")

        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        assert response.headers["www-authenticate"] == "Bearer"

    def test_garbage_bearer_token_returns_401(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/users/me", headers={"Authorization": "Bearer not-a-real-token"}
        )

        assert response.status_code == 401
