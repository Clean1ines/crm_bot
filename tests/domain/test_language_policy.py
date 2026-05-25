from src.domain.runtime.language_policy import detect_language_hint


def test_detect_language_hint_detects_spanish_without_diacritics() -> None:
    text = "hola necesito ayuda con el pedido y quiero informacion"
    assert detect_language_hint(text) == "es"


def test_detect_language_hint_detects_german_without_diacritics() -> None:
    text = "hallo ich brauche hilfe und bitte senden sie details"
    assert detect_language_hint(text) == "de"


def test_detect_language_hint_detects_english_for_plain_latin_text() -> None:
    text = "hello i need help with pricing and support details"
    assert detect_language_hint(text) == "en"
