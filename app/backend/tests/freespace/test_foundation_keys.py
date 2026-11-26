"""Foundation: key generation/hashing and device-id helpers (BF-10a, D3, D5)."""

from __future__ import annotations

import re

from src.services.freespace.keys import (
    device_id_suffix,
    generate_app_key,
    generate_ingest_key,
    hash_device_id,
    hash_key,
    is_valid_device_id,
    is_valid_key_format,
    key_hint,
    keys_equal,
)


PARKIT_KEY_RE = re.compile(r"^[\x21-\x7e]{1,512}$")


class TestIngestKeys:
    def test_format(self):
        key = generate_ingest_key()
        assert key.startswith("fsk_")
        assert len(key) == 4 + 43  # 256 bits base64url
        assert PARKIT_KEY_RE.fullmatch(key)
        assert re.fullmatch(r"fsk_[A-Za-z0-9_-]{43}", key)

    def test_unique(self):
        assert len({generate_ingest_key() for _ in range(200)}) == 200

    def test_app_key_prefix(self):
        key = generate_app_key()
        assert key.startswith("fsa_") and len(key) == 47

    def test_hash_is_sha256_hex_and_deterministic(self):
        key = generate_ingest_key()
        digest = hash_key(key)
        assert re.fullmatch(r"[0-9a-f]{64}", digest)
        assert digest == hash_key(key)
        assert digest != hash_key(key + "x")
        assert hash_key("abc") == (
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )

    def test_hint(self):
        assert key_hint("fsk_abcdWXYZ") == "WXYZ"

    def test_keys_equal(self):
        assert keys_equal("a" * 64, "a" * 64)
        assert not keys_equal("a" * 64, "b" * 64)


class TestKeyFormat:
    def test_accepts_printable_ascii(self):
        assert is_valid_key_format("fsk_" + "A" * 43)
        assert is_valid_key_format("!~")

    def test_rejects_space_control_empty_and_long(self):
        assert not is_valid_key_format("")
        assert not is_valid_key_format("has space")
        assert not is_valid_key_format("tab\tkey")
        assert not is_valid_key_format("é")
        assert not is_valid_key_format("a" * 513)
        assert is_valid_key_format("a" * 512)


class TestDeviceIds:
    def test_valid(self):
        assert is_valid_device_id("A" * 22)
        assert is_valid_device_id("abc-DEF_123" * 2 + "xy")
        assert is_valid_device_id("a" * 64)

    def test_invalid(self):
        assert not is_valid_device_id("short")
        assert not is_valid_device_id("a" * 65)
        assert not is_valid_device_id("a" * 21 + "!")
        assert not is_valid_device_id("a" * 22 + " ")

    def test_hash_and_suffix(self):
        device_id = "Zr4f8Qk1mP0sLx9vB2nC7d"
        assert hash_device_id(device_id) == hash_key(device_id)
        assert device_id not in hash_device_id(device_id)
        assert device_id_suffix(device_id) == "B2nC7d"
