from src.message_utils import fingerprint_messages, normalize_messages, normalize_text


def test_normalize_text_strips_spaces_and_zero_width():
    assert normalize_text("  a\u200b b  ") == "a b"


def test_normalize_messages_filters_noise_and_system():
    raw = [
        {"role": "System", "text": "微信", "conf": 0.99},
        {"role": "Other", "text": "  好的   ", "conf": 0.95},
        {"role": "Other", "text": "...", "conf": 0.95},
        {"role": "Self", "text": "ok", "conf": 0.92},
    ]
    cleaned = normalize_messages(raw, include_system=False)
    assert cleaned == [
        {"role": "Other", "text": "好的", "conf": 0.95},
        {"role": "Self", "text": "ok", "conf": 0.92},
    ]


def test_fingerprint_messages_stable_for_same_payload():
    msgs = [
        {"role": "Other", "text": "你好"},
        {"role": "Self", "text": "在吗"},
    ]
    fp1 = fingerprint_messages(msgs)
    fp2 = fingerprint_messages(list(msgs))
    assert fp1 == fp2

