"""
Utilities for normalizing OCR messages, filtering obvious noise, and
computing stable fingerprints for deduplication.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable

# System fragments that often come from OCR noise rather than chat content.
_UI_NOISE = {
    "微信",
    "qq",
    "搜索",
    "发送",
    "关闭",
    "最小化",
    "最大化",
    "聊天信息",
}


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    text = text.replace("\ufeff", "").replace("\u200b", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_semantic_message(text: str, min_len: int = 2) -> bool:
    text = normalize_text(text)
    if len(text) < min_len:
        return False

    lower = text.lower()
    if lower in _UI_NOISE:
        return False

    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", text))
    has_word = bool(re.search(r"[A-Za-z]{2,}", text))
    has_digits = bool(re.search(r"\d{3,}", text))
    has_many_symbols = bool(re.fullmatch(r"[\W_]+", text))

    if has_many_symbols:
        return False

    return has_cjk or has_word or has_digits


def normalize_messages(
    messages: Iterable[dict],
    min_len: int = 2,
    include_system: bool = False,
) -> list[dict]:
    cleaned: list[dict] = []
    for msg in messages or []:
        role = str(msg.get("role", "System"))
        text = normalize_text(msg.get("text", ""))
        conf = float(msg.get("conf", 0.0))

        if not include_system and role == "System":
            continue
        if not is_semantic_message(text, min_len=min_len):
            continue

        cleaned.append({
            "role": role,
            "text": text,
            "conf": conf,
        })
    return cleaned


def fingerprint_messages(messages: Iterable[dict], limit: int = 20) -> str:
    payload = [
        {
            "role": str(m.get("role", "")),
            "text": normalize_text(str(m.get("text", ""))),
        }
        for m in list(messages or [])[-limit:]
    ]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()
