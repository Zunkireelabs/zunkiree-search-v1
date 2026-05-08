"""
Unit tests for language_detection.detect_language().

Pure unit — no DB, no async, no network. Covers all four return values and
the key boundary cases that matter for the ecommerce DM translation gate.
"""
from app.services.language_detection import detect_language


# ---------------------------------------------------------------------------
# English (no Nepali signal words)
# ---------------------------------------------------------------------------

def test_english_greeting():
    assert detect_language("hi") == "en"


def test_english_greeting_hello():
    assert detect_language("hello there") == "en"


def test_english_product_query():
    assert detect_language("show me some coats") == "en"


def test_english_with_punctuation():
    assert detect_language("Hello, how are you?") == "en"


def test_empty_string():
    assert detect_language("") == "en"


# ---------------------------------------------------------------------------
# Romanized Nepali (≥2 signal words)
# ---------------------------------------------------------------------------

def test_romanized_nepali_product_query():
    # "malai" + "haru" + "dekhaununa" = 3 signals
    assert detect_language("malai coats haru dekhaununa") == "ne_romanized"


def test_romanized_nepali_two_signals():
    # "tapai" + "ho" = 2 signals
    assert detect_language("tapai ko naam k ho") == "ne_romanized"


def test_romanized_nepali_verb_copula():
    # "cha" + "haru" = 2 signals
    assert detect_language("ramro coats haru cha") == "ne_romanized"


def test_romanized_nepali_garnus_haru():
    # "garnus" + "haru" = 2 signals
    assert detect_language("shirts haru dekhaunos garnus") == "ne_romanized"


def test_romanized_nepali_full_sentence():
    # "tapai" + "kasari" + "garchu" = 3 signals
    assert detect_language("tapai lai kasari help garchu") == "ne_romanized"


def test_romanized_nepali_punctuation_stripped():
    # "malai" + "haru?" stripped to "haru" = 2 signals
    assert detect_language("malai coats haru?") == "ne_romanized"


# ---------------------------------------------------------------------------
# Mixed Nepali+English (exactly 1 signal word)
# ---------------------------------------------------------------------------

def test_mixed_ke_cha():
    # "cha" = 1 signal
    assert detect_language("ke cha") == "mixed_ne_en"


def test_mixed_ke_cha_question_mark():
    # Punctuation stripped: "cha?" → "cha" = 1 signal
    assert detect_language("ke cha?") == "mixed_ne_en"


def test_mixed_aru_cha():
    # "cha" = 1 signal
    assert detect_language("aru cha kehi") == "mixed_ne_en"


def test_mixed_garnus_only():
    # "garnus" = 1 signal
    assert detect_language("garnus please") == "mixed_ne_en"


# ---------------------------------------------------------------------------
# Devanagari script
# ---------------------------------------------------------------------------

def test_devanagari_namaste():
    assert detect_language("नमस्ते") == "ne_devanagari"


def test_devanagari_mixed_with_latin():
    # Devanagari takes precedence over any Latin signals
    assert detect_language("hello नमस्ते cha haru") == "ne_devanagari"
