"""API tests for `/users/*` endpoints, including RBAC enforcement."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.api.identity_access.conftest import (
    admin_tokens,
    auth_header,
    register,
    register_and_login,
)


class TestGetMyProfile:
    def test_returns_the_caller_own_profile(self, client: TestClient) -> None:
        tokens = register_and_login(client)

        response = client.get("/api/v1/users/me", headers=auth_header(tokens))

        assert response.status_code == 200
        assert response.json()["email"] == "alice@example.com"


class TestUpdateMyProfile:
    def test_updates_full_name(self, client: TestClient) -> None:
        tokens = register_and_login(client)

        response = client.patch(
            "/api/v1/users/me", json={"full_name": "New Name"}, headers=auth_header(tokens)
        )

        assert response.status_code == 200
        assert response.json()["full_name"] == "New Name"

    def test_change_is_visible_on_subsequent_get(self, client: TestClient) -> None:
        tokens = register_and_login(client)
        client.patch(
            "/api/v1/users/me", json={"full_name": "New Name"}, headers=auth_header(tokens)
        )

        response = client.get("/api/v1/users/me", headers=auth_header(tokens))

        assert response.json()["full_name"] == "New Name"

    def test_empty_full_name_returns_422(self, client: TestClient) -> None:
        tokens = register_and_login(client)

        response = client.patch(
            "/api/v1/users/me", json={"full_name": ""}, headers=auth_header(tokens)
        )

        assert response.status_code == 422

    def test_cannot_update_own_role_via_this_endpoint(self, client: TestClient) -> None:
        """The self-service schema has no `role` field — sending one is simply ignored."""
        tokens = register_and_login(client)

        response = client.patch(
            "/api/v1/users/me",
            json={"full_name": "New Name", "role": "admin"},
            headers=auth_header(tokens),
        )

        assert response.status_code == 200
        assert response.json()["role"] == "member"


class TestListUsersRBAC:
    def test_member_gets_403(self, client: TestClient) -> None:
        tokens = register_and_login(client)

        response = client.get("/api/v1/users", headers=auth_header(tokens))

        assert response.status_code == 403
        assert response.json()["type"].endswith("/insufficient-permissions")

    def test_no_token_gets_401(self, client: TestClient) -> None:
        response = client.get("/api/v1/users")

        assert response.status_code == 401

    def test_admin_can_list_users(self, admin_client: TestClient) -> None:
        register(admin_client, email="bob@example.com")
        tokens = admin_tokens(admin_client)

        response = admin_client.get("/api/v1/users", headers=auth_header(tokens))

        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "has_more" in body
        emails = {u["email"] for u in body["items"]}
        assert "bob@example.com" in emails
        assert "admin@example.com" in emails

    def test_admin_pagination_respects_limit(self, admin_client: TestClient) -> None:
        for i in range(3):
            register(admin_client, email=f"user{i}@example.com")
        tokens = admin_tokens(admin_client)

        response = admin_client.get("/api/v1/users?limit=2", headers=auth_header(tokens))

        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 2
        assert body["has_more"] is True
        assert body["next_cursor"] is not None

    def test_limit_over_max_returns_422(self, admin_client: TestClient) -> None:
        tokens = admin_tokens(admin_client)

        response = admin_client.get("/api/v1/users?limit=1000", headers=auth_header(tokens))

        assert response.status_code == 422


class TestGetUserByIdRBAC:
    def test_member_gets_403(self, client: TestClient) -> None:
        register(client)
        tokens = register_and_login(client, email="viewer@example.com")

        me = client.get("/api/v1/users/me", headers=auth_header(tokens)).json()
        response = client.get(f"/api/v1/users/{me['id']}", headers=auth_header(tokens))

        assert response.status_code == 403

    def test_admin_can_get_a_user_by_id(self, admin_client: TestClient) -> None:
        register(admin_client, email="bob@example.com")
        tokens = admin_tokens(admin_client)
        items = admin_client.get("/api/v1/users?limit=10", headers=auth_header(tokens)).json()[
            "items"
        ]
        bob_id = next(u["id"] for u in items if u["email"] == "bob@example.com")

        response = admin_client.get(f"/api/v1/users/{bob_id}", headers=auth_header(tokens))

        assert response.status_code == 200
        assert response.json()["email"] == "bob@example.com"

    def test_admin_get_unknown_id_returns_404(self, admin_client: TestClient) -> None:
        tokens = admin_tokens(admin_client)

        response = admin_client.get(f"/api/v1/users/{uuid.uuid4()}", headers=auth_header(tokens))

        assert response.status_code == 404
        assert response.json()["type"].endswith("/user-not-found")


class TestUpdateUserRBAC:
    def test_member_gets_403(self, client: TestClient) -> None:
        tokens = register_and_login(client)
        me = client.get("/api/v1/users/me", headers=auth_header(tokens)).json()

        response = client.patch(
            f"/api/v1/users/{me['id']}", json={"role": "admin"}, headers=auth_header(tokens)
        )

        assert response.status_code == 403

    def test_admin_can_promote_a_user(self, admin_client: TestClient) -> None:
        register(admin_client, email="bob@example.com")
        tokens = admin_tokens(admin_client)
        items = admin_client.get("/api/v1/users?limit=10", headers=auth_header(tokens)).json()[
            "items"
        ]
        bob_id = next(u["id"] for u in items if u["email"] == "bob@example.com")

        response = admin_client.patch(
            f"/api/v1/users/{bob_id}", json={"role": "admin"}, headers=auth_header(tokens)
        )

        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    def test_admin_can_deactivate_a_user(self, admin_client: TestClient) -> None:
        register(admin_client, email="bob@example.com")
        tokens = admin_tokens(admin_client)
        items = admin_client.get("/api/v1/users?limit=10", headers=auth_header(tokens)).json()[
            "items"
        ]
        bob_id = next(u["id"] for u in items if u["email"] == "bob@example.com")

        response = admin_client.patch(
            f"/api/v1/users/{bob_id}", json={"is_active": False}, headers=auth_header(tokens)
        )

        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_empty_body_returns_422(self, admin_client: TestClient) -> None:
        register(admin_client, email="bob@example.com")
        tokens = admin_tokens(admin_client)
        items = admin_client.get("/api/v1/users?limit=10", headers=auth_header(tokens)).json()[
            "items"
        ]
        bob_id = next(u["id"] for u in items if u["email"] == "bob@example.com")

        response = admin_client.patch(
            f"/api/v1/users/{bob_id}", json={}, headers=auth_header(tokens)
        )

        assert response.status_code == 422
        assert response.json()["type"].endswith("/validation-error")


class TestDeactivatedUserCannotAuthenticate:
    def test_deactivated_user_login_fails(self, admin_client: TestClient) -> None:
        register(admin_client, email="bob@example.com")
        admin = admin_tokens(admin_client)
        items = admin_client.get("/api/v1/users?limit=10", headers=auth_header(admin)).json()[
            "items"
        ]
        bob_id = next(u["id"] for u in items if u["email"] == "bob@example.com")
        admin_client.patch(
            f"/api/v1/users/{bob_id}", json={"is_active": False}, headers=auth_header(admin)
        )

        response = admin_client.post(
            "/api/v1/auth/login", data={"username": "bob@example.com", "password": "AlicePass123"}
        )

        assert response.status_code == 401
