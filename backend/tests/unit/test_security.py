"""Unit tests for password, token and canonical-hash helpers."""

from __future__ import annotations

import pytest

from app.core.security import (
    canonical_json,
    generate_api_key,
    generate_token,
    hash_password,
    hash_payload,
    hash_token,
    password_problems,
    tokens_match,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify_roundtrip(self) -> None:
        password_hash = hash_password("Sup3rSecret!2026")
        assert password_hash != "Sup3rSecret!2026"
        assert verify_password("Sup3rSecret!2026", password_hash) is True
        assert verify_password("wrong-password", password_hash) is False

    def test_hashes_are_salted_and_unique(self) -> None:
        first = hash_password("Sup3rSecret!2026")
        second = hash_password("Sup3rSecret!2026")
        assert first != second

    def test_verify_never_raises_on_garbage_hash(self) -> None:
        assert verify_password("whatever", "not-a-hash") is False


class TestPasswordPolicy:
    @pytest.mark.parametrize(
        "password",
        ["short1", "alllowercasepassword", "1234567890123", "  spaces 1  "],
    )
    def test_weak_passwords_are_rejected(self, password: str) -> None:
        assert password_problems(password)

    def test_strong_password_passes(self) -> None:
        assert password_problems("Sup3rSecret!2026") == []

    def test_common_sequence_is_rejected(self) -> None:
        assert password_problems("myPassword2026!")


class TestTokens:
    def test_tokens_are_unique_and_url_safe(self) -> None:
        first = generate_token()
        second = generate_token()
        assert first != second
        assert " " not in first

    def test_hash_token_is_stable_and_non_reversible(self) -> None:
        token = generate_token()
        assert hash_token(token) == hash_token(token)
        assert token not in hash_token(token)

    def test_tokens_match(self) -> None:
        token = generate_token()
        assert tokens_match(token, hash_token(token)) is True
        assert tokens_match("other", hash_token(token)) is False


class TestApiKeys:
    def test_api_key_has_prefix_and_unique_body(self) -> None:
        key, prefix = generate_api_key()
        assert key.startswith(f"{prefix}_")
        assert key != generate_api_key()[0]


class TestCanonicalPayload:
    def test_key_order_does_not_change_the_hash(self) -> None:
        assert hash_payload({"a": 1, "b": 2}) == hash_payload({"b": 2, "a": 1})

    def test_nested_structures_are_normalised(self) -> None:
        left = {"tool": {"name": "x", "args": [1, 2]}}
        right = {"tool": {"args": [1, 2], "name": "x"}}
        assert canonical_json(left) == canonical_json(right)
        assert hash_payload(left) == hash_payload(right)

    def test_different_payloads_hash_differently(self) -> None:
        assert hash_payload({"a": 1}) != hash_payload({"a": 2})
