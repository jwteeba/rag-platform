"""API tests for `/users/me/sessions/*` — session management (Phase 4, ADR-0007)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.identity_access.conftest import auth_header, login, register, register_and_login


class TestListSessions:
    def test_new_login_creates_one_session(self, client: TestClient) -> None:
        tokens = register_and_login(client)

        response = client.get("/api/v1/users/me/sessions", headers=auth_header(tokens))

        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        assert "session_id" in body["items"][0]
        assert "expires_at" in body["items"][0]

    def test_second_login_adds_a_second_session(self, client: TestClient) -> None:
        register(client)
        tokens = login(client, email="alice@example.com", password="AlicePass123").json()
        # log in again — a second "device"
        login(client, email="alice@example.com", password="AlicePass123")

        response = client.get("/api/v1/users/me/sessions", headers=auth_header(tokens))

        assert len(response.json()["items"]) == 2

    def test_no_token_returns_401(self, client: TestClient) -> None:
        response = client.get("/api/v1/users/me/sessions")

        assert response.status_code == 401

    def test_only_sees_own_sessions(self, client: TestClient) -> None:
        alice = register_and_login(client, email="alice@example.com")
        register_and_login(client, email="bob@example.com")

        response = client.get("/api/v1/users/me/sessions", headers=auth_header(alice))

        assert len(response.json()["items"]) == 1


class TestRevokeOneSession:
    def test_revoking_own_session_returns_204(self, client: TestClient) -> None:
        tokens = register_and_login(client)
        sessions = client.get("/api/v1/users/me/sessions", headers=auth_header(tokens)).json()
        session_id = sessions["items"][0]["session_id"]

        response = client.delete(
            f"/api/v1/users/me/sessions/{session_id}", headers=auth_header(tokens)
        )

        assert response.status_code == 204

    def test_revoked_session_no_longer_appears_in_list(self, client: TestClient) -> None:
        tokens = register_and_login(client)
        sessions = client.get("/api/v1/users/me/sessions", headers=auth_header(tokens)).json()
        session_id = sessions["items"][0]["session_id"]

        client.delete(f"/api/v1/users/me/sessions/{session_id}", headers=auth_header(tokens))

        response = client.get("/api/v1/users/me/sessions", headers=auth_header(tokens))
        assert response.json()["items"] == []

    def test_revoked_sessions_refresh_token_is_rejected(self, client: TestClient) -> None:
        tokens = register_and_login(client)
        sessions = client.get("/api/v1/users/me/sessions", headers=auth_header(tokens)).json()
        session_id = sessions["items"][0]["session_id"]
        client.delete(f"/api/v1/users/me/sessions/{session_id}", headers=auth_header(tokens))

        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

        assert response.status_code == 401

    def test_revoking_unknown_session_returns_404(self, client: TestClient) -> None:
        tokens = register_and_login(client)

        response = client.delete(
            "/api/v1/users/me/sessions/not-a-real-session-id", headers=auth_header(tokens)
        )

        assert response.status_code == 404
        assert response.json()["type"].endswith("/session-not-found")

    def test_cannot_revoke_another_users_session(self, client: TestClient) -> None:
        alice = register_and_login(client, email="alice@example.com")
        bob = register_and_login(client, email="bob@example.com")
        bob_sessions = client.get("/api/v1/users/me/sessions", headers=auth_header(bob)).json()
        bob_session_id = bob_sessions["items"][0]["session_id"]

        response = client.delete(
            f"/api/v1/users/me/sessions/{bob_session_id}", headers=auth_header(alice)
        )

        assert response.status_code == 404

        # And Bob's session is still intact.
        still_there = client.get("/api/v1/users/me/sessions", headers=auth_header(bob))
        assert len(still_there.json()["items"]) == 1

    def test_no_token_returns_401(self, client: TestClient) -> None:
        response = client.delete("/api/v1/users/me/sessions/some-id")

        assert response.status_code == 401


class TestRevokeAllSessions:
    def test_returns_204(self, client: TestClient) -> None:
        tokens = register_and_login(client)

        response = client.post("/api/v1/users/me/sessions/revoke-all", headers=auth_header(tokens))

        assert response.status_code == 204

    def test_clears_every_session(self, client: TestClient) -> None:
        register(client)
        tokens = login(client, email="alice@example.com", password="AlicePass123").json()
        login(client, email="alice@example.com", password="AlicePass123")  # second device
        before = client.get("/api/v1/users/me/sessions", headers=auth_header(tokens))
        assert len(before.json()["items"]) == 2

        client.post("/api/v1/users/me/sessions/revoke-all", headers=auth_header(tokens))

        response = client.get("/api/v1/users/me/sessions", headers=auth_header(tokens))
        assert response.json()["items"] == []

    def test_all_refresh_tokens_rejected_afterward(self, client: TestClient) -> None:
        tokens_a = register_and_login(client)
        tokens_b = login(client, email="alice@example.com", password="AlicePass123").json()

        client.post("/api/v1/users/me/sessions/revoke-all", headers=auth_header(tokens_a))

        response_a = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens_a["refresh_token"]}
        )
        response_b = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens_b["refresh_token"]}
        )
        assert response_a.status_code == 401
        assert response_b.status_code == 401

    def test_does_not_affect_other_users_sessions(self, client: TestClient) -> None:
        alice = register_and_login(client, email="alice@example.com")
        bob = register_and_login(client, email="bob@example.com")

        client.post("/api/v1/users/me/sessions/revoke-all", headers=auth_header(alice))

        bob_sessions = client.get("/api/v1/users/me/sessions", headers=auth_header(bob))
        assert len(bob_sessions.json()["items"]) == 1

    def test_no_token_returns_401(self, client: TestClient) -> None:
        response = client.post("/api/v1/users/me/sessions/revoke-all")

        assert response.status_code == 401
