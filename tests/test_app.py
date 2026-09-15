"""
Unit tests for app.py.

These tests cover the pure/mockable logic (AI calls, Telegram sending,
HTML generation). The Playwright-based scraping functions (get_chmi_forecast,
get_dhv_forecasts, get_austro_forecasts, get_slovenia_forecast) hit live
external websites and are intentionally NOT covered here - they would need
a browser and network access, and would be flaky/slow in CI. Consider
covering them with a small set of recorded-HTML fixture tests if the
scraping logic grows more complex.
"""
import inspect

import pytest

import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, response_text=None, exc=None):
        self._response_text = response_text
        self._exc = exc
        self.calls = []

    def generate_content(self, model, contents):
        self.calls.append({"model": model, "contents": contents})
        if self._exc is not None:
            raise self._exc
        return FakeResponse(self._response_text)


class FakeClient:
    def __init__(self, response_text=None, exc=None):
        self.models = FakeModels(response_text=response_text, exc=exc)


def install_fake_genai(monkeypatch, response_text=None, exc=None):
    """Patches app.genai.Client to avoid any real network/API calls."""
    fake_client = FakeClient(response_text=response_text, exc=exc)
    monkeypatch.setattr(app.genai, "Client", lambda api_key: fake_client)
    return fake_client


class FakeRequests:
    """Records calls made through app.requests.post without hitting the network."""

    def __init__(self, status_code=200):
        self.calls = []
        self.status_code = status_code

    def post(self, url, json=None):
        self.calls.append({"url": url, "json": json})
        return FakeHttpResponse(self.status_code)


class FakeHttpResponse:
    def __init__(self, status_code):
        self.status_code = status_code
        self.text = ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise app.requests.HTTPError(f"status {self.status_code}")


# ---------------------------------------------------------------------------
# get_ai_evaluation
# ---------------------------------------------------------------------------

def test_get_ai_evaluation_without_api_key_returns_placeholder(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = app.get_ai_evaluation("Česko", "forecast text")

    assert result == "AI hodnocení není dostupné (chybí API klíč)."


def test_get_ai_evaluation_returns_stripped_model_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    fake_client = install_fake_genai(monkeypatch, response_text="  Dobré podmínky.  ")

    result = app.get_ai_evaluation("Česko", "forecast text")

    assert result == "Dobré podmínky."
    assert fake_client.models.calls[0]["model"] == app.AI_PROMPT_MODEL_INSTUCT
    assert "Česko" in fake_client.models.calls[0]["contents"]
    assert "forecast text" in fake_client.models.calls[0]["contents"]


def test_get_ai_evaluation_returns_fallback_on_exception(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    install_fake_genai(monkeypatch, exc=RuntimeError("boom"))

    result = app.get_ai_evaluation("Rakousko", "forecast text")

    assert result == "Nepodařilo se vygenerovat AI hodnocení."


# ---------------------------------------------------------------------------
# translate_and_format_weather
# ---------------------------------------------------------------------------

def test_translate_without_api_key_returns_original_text(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = app.translate_and_format_weather("original text", "German")

    assert result == "original text"


def test_translate_returns_stripped_translated_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    install_fake_genai(monkeypatch, response_text="  Přeložený text  ")

    result = app.translate_and_format_weather("original text", "German")

    assert result == "Přeložený text"


def test_translate_returns_original_text_on_exception(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    install_fake_genai(monkeypatch, exc=RuntimeError("boom"))

    result = app.translate_and_format_weather("original text", "German")

    assert result == "original text"


# ---------------------------------------------------------------------------
# send_to_telegram
# ---------------------------------------------------------------------------

def _processed_data(ai_text="Hodnocení počasí."):
    return {
        "Česko": {"raw": "raw forecast", "ai": ai_text},
        "Rakousko": {"raw": {"Day 1": "..."}, "ai": ai_text},
    }


def test_send_to_telegram_without_credentials_sends_nothing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    fake_requests = FakeRequests()
    monkeypatch.setattr(app, "requests", fake_requests)

    app.send_to_telegram(_processed_data())

    assert fake_requests.calls == []


def test_send_to_telegram_sends_one_message_per_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", " 111 , 222 ,, 333")
    fake_requests = FakeRequests()
    monkeypatch.setattr(app, "requests", fake_requests)

    app.send_to_telegram(_processed_data())

    # Empty entries in the comma-separated list must be skipped.
    sent_chat_ids = [call["json"]["chat_id"] for call in fake_requests.calls]
    assert sent_chat_ids == ["111", "222", "333"]

    for call in fake_requests.calls:
        assert call["url"] == "https://api.telegram.org/bot fake-token/sendMessage".replace(" ", "")
        assert call["json"]["parse_mode"] == "Markdown"
        assert call["json"]["disable_web_page_preview"] is True
        assert len(call["json"]["text"]) <= 4000


def test_send_to_telegram_truncates_long_briefing(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    fake_requests = FakeRequests()
    monkeypatch.setattr(app, "requests", fake_requests)

    app.send_to_telegram(_processed_data(ai_text="x" * 10000))

    assert len(fake_requests.calls) == 1
    assert len(fake_requests.calls[0]["json"]["text"]) == 4000


# ---------------------------------------------------------------------------
# create_html_page
# ---------------------------------------------------------------------------

def test_create_html_page_writes_expected_sections(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    processed_data = {
        "Česko": {"raw": "raw forecast text", "ai": "AI hodnocení Česka"},
        "Rakousko": {
            "raw": {"Day 1": "raw day 1 text"},
            "ai": "AI hodnocení Rakouska",
        },
    }

    app.create_html_page(processed_data)

    output = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Česko" in output
    assert "AI hodnocení Česka" in output
    assert "raw forecast text" in output
    assert 'href="#Rakousko"' in output
    assert "Day 1" in output
    assert "raw day 1 text" in output


def test_create_html_page_skips_regions_missing_from_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    processed_data = {"Slovinsko": {"raw": "raw", "ai": "ai"}}

    app.create_html_page(processed_data)

    output = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Slovinsko" in output
    # Regions absent from processed_data must not appear as broken nav links.
    assert 'href="#Rakousko"' not in output


# ---------------------------------------------------------------------------
# Regression guard: the region key used for Slovenian translation must match
# the key actually used elsewhere in the module ("Slovinsko"), not the
# English name "Slovenia" - a previous version of this file had that typo,
# which silently disabled translation for Slovenia.
# ---------------------------------------------------------------------------

def test_slovenia_region_key_is_consistent():
    source = inspect.getsource(app)

    assert '"Slovenia"' not in source
    assert 'region == "Slovinsko"' in source
