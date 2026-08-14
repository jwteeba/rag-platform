"""Unit tests for `rag_platform.core.security`."""

from __future__ import annotations

import time
from datetime import timedelta

import pytest

from rag_platform.core.security import (
    TokenError,
    TokenType,
    decode_token,
    encode_token,
    hash_password,
    verify_password,
)

SECRET = "WeE8VSaoAGUWStOGeYkkNZE0rsXYVXW/qa9ObtFZIqk="
ALGORITHM = "HS256"


class TestPasswordHashing:
    def test_hash_is_not_the_plaintext(self) -> None:
        hashed = hash_password("correct horse battery staple")

        assert hashed != "correct horse battery staple"

    def test_verify_succeeds_for_correct_password(self) -> None:
        hashed = hash_password("correct horse battery staple")

        assert verify_password("correct horse battery staple", hashed) is True

    def test_verify_fails_for_wrong_password(self) -> None:
        hashed = hash_password("correct horse battery staple")

        assert verify_password("wrong password", hashed) is False

    def test_verify_returns_false_for_malformed_hash_instead_of_raising(self) -> None:
        assert verify_password("anything", "not-a-real-bcrypt-hash") is False

    def test_two_hashes_of_same_password_differ(self) -> None:
        # bcrypt salts each hash independently.
        first = hash_password("same password")
        second = hash_password("same password")

        assert first != second


class TestTokenEncodeDecode:
    def test_round_trip_access_token(self) -> None:
        token, claims = encode_token(
            subject="user-123",
            token_type=TokenType.ACCESS,
            expires_in=timedelta(minutes=5),
            secret_key=SECRET,
            algorithm=ALGORITHM,
        )

        decoded = decode_token(
            token, expected_type=TokenType.ACCESS, secret_key=SECRET, algorithm=ALGORITHM
        )

        assert decoded.subject == "user-123"
        assert decoded.token_type is TokenType.ACCESS
        assert decoded.jti == claims.jti

    def test_each_token_gets_a_unique_jti(self) -> None:
        _, claims_a = encode_token(
            subject="user-123",
            token_type=TokenType.ACCESS,
            expires_in=timedelta(minutes=5),
            secret_key=SECRET,
            algorithm=ALGORITHM,
        )
        _, claims_b = encode_token(
            subject="user-123",
            token_type=TokenType.ACCESS,
            expires_in=timedelta(minutes=5),
            secret_key=SECRET,
            algorithm=ALGORITHM,
        )

        assert claims_a.jti != claims_b.jti

    def test_decode_rejects_wrong_token_type(self) -> None:
        token, _ = encode_token(
            subject="user-123",
            token_type=TokenType.REFRESH,
            expires_in=timedelta(minutes=5),
            secret_key=SECRET,
            algorithm=ALGORITHM,
        )

        with pytest.raises(TokenError, match="Expected a access token"):
            decode_token(
                token, expected_type=TokenType.ACCESS, secret_key=SECRET, algorithm=ALGORITHM
            )

    def test_decode_rejects_expired_token(self) -> None:
        token, _ = encode_token(
            subject="user-123",
            token_type=TokenType.ACCESS,
            expires_in=timedelta(milliseconds=1),
            secret_key=SECRET,
            algorithm=ALGORITHM,
        )
        time.sleep(0.05)

        with pytest.raises(TokenError, match="expired"):
            decode_token(
                token, expected_type=TokenType.ACCESS, secret_key=SECRET, algorithm=ALGORITHM
            )

    def test_decode_rejects_bad_signature(self) -> None:
        token, _ = encode_token(
            subject="user-123",
            token_type=TokenType.ACCESS,
            expires_in=timedelta(minutes=5),
            secret_key=SECRET,
            algorithm=ALGORITHM,
        )

        with pytest.raises(TokenError, match="invalid"):
            decode_token(
                token,
                expected_type=TokenType.ACCESS,
                secret_key="a-different-secret",
                algorithm=ALGORITHM,
            )

    def test_decode_rejects_garbage_string(self) -> None:
        with pytest.raises(TokenError):
            decode_token(
                "not.a.jwt", expected_type=TokenType.ACCESS, secret_key=SECRET, algorithm=ALGORITHM
            )

    def test_decode_rejects_token_with_malformed_payload(self) -> None:
        """A token that verifies cryptographically but is missing required
        claims (e.g. hand-crafted or from an incompatible signer sharing the
        same secret) must fail closed, not raise a raw KeyError."""
        import jwt as pyjwt

        # no type/jti/iat/exp claims
        token = pyjwt.encode({"sub": "user-123"}, SECRET, algorithm=ALGORITHM)

        with pytest.raises(TokenError, match="malformed"):
            decode_token(
                token, expected_type=TokenType.ACCESS, secret_key=SECRET, algorithm=ALGORITHM
            )
