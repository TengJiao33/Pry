from src.llm_client import LLMClient


def test_parse_response_text_accepts_markdown_json():
    text = """```json
    {"action":"suggest","content":"回他一个具体时间","memory_updates":{"user":{"communication_style":"直接"}}}
    ```"""
    parsed = LLMClient.parse_response_text(text)
    assert parsed is not None
    assert parsed["action"] == "suggest"
    assert parsed["content"] == "回他一个具体时间"
    assert parsed["memory_updates"]["user"]["communication_style"] == "直接"


def test_parse_response_text_handles_wrapped_text():
    text = "这是你的结果：\n{\"action\":\"none\",\"content\":\"\"}\n请参考。"
    parsed = LLMClient.parse_response_text(text)
    assert parsed is not None
    assert parsed["action"] == "none"
    assert parsed["content"] == ""


def test_parse_response_text_invalid_action_falls_back_to_none():
    text = "{\"action\":\"unknown\",\"content\":\"hello\",\"memory_updates\":[]}"
    parsed = LLMClient.parse_response_text(text)
    assert parsed is not None
    assert parsed["action"] == "none"
    assert parsed["content"] == ""
    assert parsed["memory_updates"] == {}

