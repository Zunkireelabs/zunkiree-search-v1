"""Argon2id wrapper tests (Z6).

The hash output is non-deterministic (built-in salt), so tests verify the
round-trip and that verify rejects any tampered plaintext.
"""
from app.services.admin_token_hash import hash_token, verify_token


def test_hash_round_trip_accepts_original():
    plaintext = "zka_sec_abc123def456ghi789jkl012mno345pqr678stu901vw"
    stored = hash_token(plaintext)
    assert stored != plaintext
    assert stored.startswith("$argon2id$")
    assert verify_token(plaintext, stored) is True


def test_verify_rejects_tampered_plaintext():
    plaintext = "zka_sec_abc123def456ghi789jkl012mno345pqr678stu901vw"
    stored = hash_token(plaintext)

    assert verify_token(plaintext + "x", stored) is False
    assert verify_token(plaintext[:-1], stored) is False
    assert verify_token("", stored) is False
    assert verify_token("zka_sec_completely_different_value_here_padded____", stored) is False


def test_verify_rejects_malformed_hash():
    assert verify_token("anything", "not-an-argon2-hash") is False
    assert verify_token("anything", "") is False


def test_two_hashes_of_same_input_differ_but_both_verify():
    """Salt randomisation means each call yields a different stored hash; both
    must still verify the original plaintext."""
    plaintext = "zka_sec_repeat_test_input_padded_to_realistic_length_x"
    a = hash_token(plaintext)
    b = hash_token(plaintext)
    assert a != b
    assert verify_token(plaintext, a)
    assert verify_token(plaintext, b)
