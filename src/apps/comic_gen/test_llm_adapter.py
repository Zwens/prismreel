from unittest.mock import MagicMock, patch


def _mock_openai_response(content: str, usage=None):
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    resp.usage = usage
    return resp


def test_chat_with_usage_returns_content_and_usage(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from src.apps.comic_gen.llm_adapter import LLMAdapter

    adapter = LLMAdapter()
    usage_obj = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    mock_response = _mock_openai_response("hello", usage=usage_obj)

    with patch.object(adapter, "_get_client") as get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        get_client.return_value = mock_client

        content, usage, model_used = adapter.chat_with_usage(messages=[{"role": "user", "content": "hi"}])

    assert content == "hello"
    assert usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert model_used == "qwen3.7-plus"  # first DashScope fallback candidate, succeeded on first try


def test_chat_with_usage_handles_missing_usage(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from src.apps.comic_gen.llm_adapter import LLMAdapter

    adapter = LLMAdapter()
    mock_response = _mock_openai_response("hello", usage=None)

    with patch.object(adapter, "_get_client") as get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        get_client.return_value = mock_client

        content, usage, model_used = adapter.chat_with_usage(messages=[{"role": "user", "content": "hi"}])

    assert content == "hello"
    assert usage is None
    assert model_used == "qwen3.7-plus"


def test_chat_with_usage_reports_actual_fallback_model(monkeypatch):
    """When the first candidate is unavailable and the chain falls back,
    the returned model_used must be the one that actually succeeded —
    not _get_default_model()'s static first-candidate guess."""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from src.apps.comic_gen.llm_adapter import LLMAdapter

    adapter = LLMAdapter()
    usage_obj = MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    ok_response = _mock_openai_response("hello", usage=usage_obj)

    call_count = {"n": 0}

    def fake_create(**kwargs):
        call_count["n"] += 1
        if kwargs["model"] == "qwen3.7-plus":
            raise Exception("Model not found: qwen3.7-plus")
        return ok_response

    with patch.object(adapter, "_get_client") as get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = fake_create
        get_client.return_value = mock_client

        content, usage, model_used = adapter.chat_with_usage(messages=[{"role": "user", "content": "hi"}])

    assert model_used == "qwen3.6-plus"
    assert call_count["n"] == 2


def test_chat_unchanged_string_return(monkeypatch):
    """chat() must still return a bare string — existing 9 call sites in
    llm.py rely on this (some via `.strip()` chaining)."""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from src.apps.comic_gen.llm_adapter import LLMAdapter

    adapter = LLMAdapter()
    mock_response = _mock_openai_response("  hello  ")

    with patch.object(adapter, "_get_client") as get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        get_client.return_value = mock_client

        result = adapter.chat(messages=[{"role": "user", "content": "hi"}])

    assert isinstance(result, str)
    assert result.strip() == "hello"
