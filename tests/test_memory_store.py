import json

from src.memory_store import MemoryStore


def test_update_contact_merges_and_increments(tmp_path):
    memory_file = tmp_path / "memory.json"
    store = MemoryStore(str(memory_file))

    store.update_contact("Alice", {"relationship": "friend", "notes": "loves music"})
    store.update_contact("Alice", {"notes": "loves music"})
    store.update_contact("Alice", {"notes": "plays guitar"})

    contact = store.get_contact("Alice")
    assert contact["relationship"] == "friend"
    assert "loves music" in contact["notes"]
    assert "plays guitar" in contact["notes"]
    assert contact["interaction_count"] == 3


def test_update_user_profile_dedupes_topics(tmp_path):
    memory_file = tmp_path / "memory.json"
    store = MemoryStore(str(memory_file))

    store.update_user_profile({"common_topics": ["AI", "music"]})
    store.update_user_profile({"common_topics": ["music", "sports"]})

    profile = store.get_user_profile()
    assert profile["common_topics"] == ["AI", "music", "sports"]


def test_save_is_valid_json(tmp_path):
    memory_file = tmp_path / "memory.json"
    store = MemoryStore(str(memory_file))
    store.update_contact("Bob", {"relationship": "colleague"})

    payload = json.loads(memory_file.read_text(encoding="utf-8"))
    assert "contacts" in payload
    assert payload["contacts"]["Bob"]["relationship"] == "colleague"

