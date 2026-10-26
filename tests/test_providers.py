"""Uji pemanggil API lewat HTTP sungguhan ke server tiruan (format wire asli)."""

import pytest

import gem_visibility_auditor as gva


def opts(srv, **kw):
    base = {"base_urls": {"anthropic": srv.base, "gemini": srv.base + "/v1beta", "openai": srv.base + "/v1",
                          "groq": srv.base + "/openai/v1", "ollama": srv.base + "/v1"},
            "claude_effort": "low", "timeout": 10}
    base.update(kw)
    return base


def test_anthropic_request_shape(mock_server):
    text, meta = gva.call_anthropic("claude-opus-5-5", "Halo?", "sk-test", opts(mock_server))
    assert "Danau Toba" in text and meta["stop_reason"] == "end_turn" and meta["output_tokens"] == 55
    req = mock_server.state.requests[-1]
    assert req["path"] == "/v1/messages"
    h, b = req["headers"], req["body"]
    assert h["x-api-key"] == "sk-test"
    assert h["anthropic-version"] == "2026-10-21"
    assert h["anthropic-beta"] == "server-side-fallback-2026-07-01"
    assert b["fallbacks"] == "default"
    assert b["output_config"] == {"effort": "low"}
    assert b["max_tokens"] == 4000
    assert b["messages"] == [{"role": "user", "content": "Halo?"}]
    for banned in ("temperature", "top_p", "top_k", "thinking"):
        assert banned not in b


def test_anthropic_older_model_has_no_effort_or_fallback(mock_server):
    gva.call_anthropic("claude-haiku-4-5", "Halo?", "k", opts(mock_server))
    req = mock_server.state.requests[-1]
    assert "output_config" not in req["body"] and "fallbacks" not in req["body"]
    assert "anthropic-beta" not in req["headers"]


def test_anthropic_retries_without_fallbacks_on_400(mock_server):
    mock_server.state.reject_fallbacks = True
    text, _ = gva.call_anthropic("claude-opus-5-5", "Halo?", "k", opts(mock_server))
    assert text
    first, second = mock_server.state.requests[-2:]
    assert "fallbacks" in first["body"] and "fallbacks" not in second["body"]


def test_anthropic_refusal_is_error(mock_server):
    mock_server.state.refuse = True
    with pytest.raises(gva.ProviderError, match="refusal"):
        gva.call_anthropic("claude-opus-5-5", "x", "k", opts(mock_server))


def test_retry_on_429(mock_server):
    mock_server.state.fail_first = 2
    text, _ = gva.call_anthropic("claude-opus-5-5", "x", "k", opts(mock_server))
    assert text and len(mock_server.state.requests) == 3


def test_401_not_retried_and_message_kept(mock_server):
    mock_server.state.unauthorized = True
    with pytest.raises(gva.ProviderError) as ei:
        gva.call_gemini("gemini-flash-latest", "x", "bad", opts(mock_server))
    assert "401" in str(ei.value) and "invalid x-api-key" in str(ei.value)
    assert len(mock_server.state.requests) == 1


def test_gemini_request_and_thought_parts_skipped(mock_server):
    text, meta = gva.call_gemini("gemini-flash-latest", "Halo?", "g-key", opts(mock_server))
    req = mock_server.state.requests[-1]
    assert req["path"] == "/v1beta/models/gemini-flash-latest:generateContent"
    assert req["headers"]["x-goog-api-key"] == "g-key"
    assert req["body"]["contents"][0]["parts"][0]["text"] == "Halo?"
    assert "pikiran internal" not in text and "Raja Ampat" in text
    assert meta["output_tokens"] == 35


def test_openai_and_compat_token_param(mock_server):
    text, _ = gva.call_openai_compat("openai", "gpt-5-mini", "Halo?", "o-key", opts(mock_server, max_tokens=500))
    req = mock_server.state.requests[-1]
    assert req["path"] == "/v1/chat/completions"
    assert req["headers"]["authorization"] == "Bearer o-key"
    assert req["body"]["max_completion_tokens"] == 500 and "max_tokens" not in req["body"]
    assert "Lake Toba" in text
    gva.call_openai_compat("groq", "llama", "Halo?", "q-key", opts(mock_server, max_tokens=500))
    req = mock_server.state.requests[-1]
    assert req["path"] == "/openai/v1/chat/completions" and req["body"]["max_tokens"] == 500
    gva.call_openai_compat("ollama", "llama3.1", "Halo?", None, opts(mock_server))
    assert "authorization" not in mock_server.state.requests[-1]["headers"]


def test_run_audit_mixed_providers(mock_server, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k1")
    monkeypatch.setenv("GEMINI_API_KEY", "k2")
    cfg = gva.load_config()
    models = [("anthropic", "claude-opus-5-5"), ("gemini", "gemini-flash-latest"), ("openai", "gpt-5-mini")]
    seen = []
    recs = gva.run_audit(models, cfg, ["id", "en"], max_questions=2, opts=opts(mock_server), workers=3,
                         progress=lambda d, t, r: seen.append(d))
    assert len(recs) == 3 * 2 * 2 and sorted(seen) == list(range(1, 13))
    by = {}
    for r in recs:
        by.setdefault(r["provider"], set()).add(r["status"])
    assert by["anthropic"] == {"ok"} and by["gemini"] == {"ok"}
    assert by["openai"] == {"error"}  # tanpa OPENAI_API_KEY: dicatat sebagai error, audit lanjut
    assert all(r["error"] == "kunci API tidak ditemukan" for r in recs if r["provider"] == "openai")
    res = gva.analyze(gva.records_to_df(recs), cfg)
    assert res["headline"]["responses_ok"] == 8
