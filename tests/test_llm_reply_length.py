"""OpenAI-style servers: the reply-length limit is sent, and a reply cut off at that limit gives a
clear error instead of broken JSON (pipeline/llm.py _call_openai). A fake client: no AI is called."""
import sys
import types

import pytest

from pipeline import llm


def fake_openai(monkeypatch, finish_reason, content='{"facts": []}'):
    sent = {}

    class Completions:
        def create(self, **kwargs):
            sent.update(kwargs)
            message = types.SimpleNamespace(content=content)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(finish_reason=finish_reason, message=message)])

    class OpenAI:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(completions=Completions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=OpenAI))
    return sent


def test_the_reply_limit_is_sent(monkeypatch):
    sent = fake_openai(monkeypatch, "stop")
    assert llm._call_openai("prompt") == '{"facts": []}'
    assert sent["max_tokens"] == llm.MAX_REPLY_TOKENS


def test_a_cut_off_reply_is_a_clear_error_not_bad_json(monkeypatch):
    fake_openai(monkeypatch, "length", content='{"facts": [{"type": "medica')
    with pytest.raises(llm.ReplyTooLong, match="LLM_MAX_TOKENS"):
        llm._call_openai("prompt")
