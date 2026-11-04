"""Voice answers (English and Hindi): speech -> text through Groq Whisper. These tests never call Groq."""
import logging

import pytest

from backend.app import main
from backend.app.voice import MAX_AUDIO_BYTES, VoiceUnavailable
from tests.test_api import client  # noqa: F401  (pytest fixture)

AUDIO = b"\x1aE\xdf\xa3" + b"\x00" * 4000   # looks like a short webm recording


class FakeTranscriber:
    available = True

    def __init__(self, text="मेरी दवाई की दुकान है", fail=False):
        self.text, self.fail, self.calls = text, fail, []

    def transcribe(self, audio, content_type, language):
        self.calls.append((len(audio), content_type, language))
        if self.fail:
            raise VoiceUnavailable("RateLimitError")
        return self.text


def start(client, lang, gst="none"):
    app_id = client.post("/api/applications", json={"language": lang}).json()["id"]
    if gst:
        client.post(f"/api/applications/{app_id}/message", json={"slot": "gstin", "value": gst})
    return app_id


def say(client, app_id, audio=AUDIO, kind="audio/webm"):
    return client.post(f"/api/applications/{app_id}/voice", files={"file": ("answer.webm", audio, kind)})


@pytest.fixture()
def fake(monkeypatch):
    f = FakeTranscriber()
    monkeypatch.setattr(main, "transcriber", f)
    return f


def test_hindi_answer_comes_back_as_text_to_check(client, fake):
    app_id = start(client, "hi")
    r = say(client, app_id)
    assert r.status_code == 200 and r.json()["text"] == "मेरी दवाई की दुकान है"
    assert fake.calls == [(len(AUDIO), "audio/webm", "hi")]          # language hint for Whisper
    profile = client.get(f"/api/applications/{app_id}").json()["profile"]
    assert profile["kind"] is None                                      # nothing is answered until the owner sends it


def test_voice_only_in_english_and_hindi(client, fake):
    assert say(client, start(client, "en")).status_code == 200
    for lang in ("mr", "gu", "ta", "te", "kn"):
        assert say(client, start(client, lang)).status_code == 404
    assert client.get("/api/health").json()["voice_languages"] == ["en", "hi"]


def test_gst_number_can_never_be_spoken(client, fake):
    r = say(client, start(client, "hi", gst=None))                      # GST question still on screen
    assert r.status_code == 409 and "GST" in r.json()["detail"] and not fake.calls


def test_bad_recordings(client, fake):
    app_id = start(client, "en")
    assert say(client, app_id, audio=b"x" * 10).status_code == 422                      # a tap without speech
    assert say(client, app_id, audio=b"x" * (MAX_AUDIO_BYTES + 1)).status_code == 413
    fake.text = ""
    assert say(client, app_id).status_code == 422                                       # nothing heard
    assert not [c for c in fake.calls if c[0] > MAX_AUDIO_BYTES]


def test_groq_failure_asks_to_try_again_or_type(client, monkeypatch):
    monkeypatch.setattr(main, "transcriber", FakeTranscriber(fail=True))
    r = say(client, start(client, "hi"))
    assert r.status_code == 503 and "लिखें" in r.json()["detail"]      # "...or type your answer", in Hindi


def test_no_voice_without_an_ai_key(client, monkeypatch):
    monkeypatch.setattr(main, "transcriber", type("Off", (), {"available": False})())
    r = say(client, start(client, "hi"))
    assert r.status_code == 503 and "switched off" in r.json()["detail"]   # off, not "wrong language"
    assert client.get("/api/health").json()["voice_languages"] == []


def test_words_spoken_are_never_logged(client, fake, caplog):
    fake.text = "my number is 9876543210"
    with caplog.at_level(logging.DEBUG):
        say(client, start(client, "en"))
    assert "9876543210" not in caplog.text and "my number" not in caplog.text
