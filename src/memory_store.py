"""
长期记忆存储模块 — 基于JSON文件的轻量级记忆系统
存储联系人画像、关系推断和用户社交风格等信息。
"""
import json
import logging
import os
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

# 默认记忆文件路径
DEFAULT_MEMORY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "memory.json")


class MemoryStore:
    """JSON文件记忆存储"""

    def __init__(self, memory_path: str = None):
        self.memory_path = memory_path or DEFAULT_MEMORY_PATH
        self._lock = threading.RLock()
        self._data = self._load()

    # ========== 文件 I/O ==========

    def _load(self) -> dict:
        """从文件加载记忆"""
        if os.path.exists(self.memory_path):
            try:
                with open(self.memory_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("memory data is not a JSON object")
                logger.info(f"已加载记忆文件: {self.memory_path} "
                            f"({len(data.get('contacts', {}))} 个联系人)")
                return data
            except (ValueError, json.JSONDecodeError, IOError) as e:
                logger.error(f"记忆文件读取失败: {e}")

        # 初始化空记忆
        return self._default_data()

    def _default_data(self) -> dict:
        return {
            "user_profile": {
                "communication_style": "",
                "common_topics": [],
                "personality_notes": "",
                "updated_at": ""
            },
            "contacts": {},
            "meta": {
                "created_at": datetime.now().isoformat(),
                "version": "1.0"
            }
        }

    def save(self):
        """持久化记忆到文件"""
        os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
        tmp_path = f"{self.memory_path}.tmp"
        try:
            with self._lock:
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.memory_path)
            logger.debug("记忆已保存")
        except OSError as e:
            logger.error(f"记忆保存失败: {e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

    # ========== 联系人操作 ==========

    def get_contact(self, name: str) -> dict:
        """获取联系人记忆，不存在则返回空字典"""
        with self._lock:
            return dict(self._data.get("contacts", {}).get(name, {}))

    def update_contact(self, name: str, info: dict):
        """
        更新联系人信息（增量合并）。
        info 示例: {"relationship": "导师", "notes": "性格严谨"}
        """
        if not name or not info:
            return

        with self._lock:
            contacts = self._data.setdefault("contacts", {})
            if name not in contacts:
                contacts[name] = {
                    "first_seen": datetime.now().isoformat(),
                    "interaction_count": 0
                }

            contact = contacts[name]

            # 增量合并字段
            for key, value in info.items():
                if key == "notes" and key in contact and value:
                    # notes 追加而非覆盖（避免丢失历史记录）
                    existing = contact.get("notes", "")
                    if value not in existing:
                        merged = f"{existing}; {value}" if existing else value
                        contact["notes"] = merged[:500]
                elif value:  # 非空值才更新
                    contact[key] = value

            contact["last_seen"] = datetime.now().isoformat()
            contact["interaction_count"] = contact.get("interaction_count", 0) + 1

            logger.info(f"联系人记忆已更新: {name} -> {contact}")
        self.save()

    # ========== 用户画像 ==========

    def get_user_profile(self) -> dict:
        """获取用户画像"""
        with self._lock:
            return dict(self._data.get("user_profile", {}))

    def update_user_profile(self, info: dict):
        """
        更新用户画像（增量合并）。
        info 示例: {"communication_style": "正式", "common_topics": ["技术"]}
        """
        if not info:
            return

        with self._lock:
            profile = self._data.setdefault("user_profile", {})

            for key, value in info.items():
                if key == "common_topics" and isinstance(value, list):
                    # 话题列表：合并去重
                    existing = set(profile.get("common_topics", []))
                    existing.update(v for v in value if v)
                    profile["common_topics"] = sorted(existing)
                elif key == "personality_notes" and key in profile and value:
                    existing = profile.get("personality_notes", "")
                    if value not in existing:
                        merged = f"{existing}; {value}" if existing else value
                        profile["personality_notes"] = merged[:500]
                elif value:
                    profile[key] = value

            profile["updated_at"] = datetime.now().isoformat()

            logger.info(f"用户画像已更新: {profile}")
        self.save()

    # ========== LLM 上下文组装 ==========

    def get_context_for_llm(self, contact_name: str = None) -> str:
        """
        组装记忆上下文，注入到 LLM 的 system prompt 中。
        :param contact_name: 当前聊天对象名称
        :return: 格式化的记忆上下文字符串
        """
        parts = []

        # 用户画像
        profile = self.get_user_profile()
        if profile.get("communication_style") or profile.get("personality_notes"):
            parts.append("=== 用户画像 ===")
            if profile.get("communication_style"):
                parts.append(f"沟通风格: {profile['communication_style']}")
            if profile.get("personality_notes"):
                parts.append(f"性格特点: {profile['personality_notes']}")
            if profile.get("common_topics"):
                parts.append(f"常聊话题: {', '.join(profile['common_topics'])}")

        # 当前联系人记忆
        if contact_name:
            contact = self.get_contact(contact_name)
            if contact:
                parts.append(f"\n=== 关于「{contact_name}」的记忆 ===")
                if contact.get("relationship"):
                    parts.append(f"关系: {contact['relationship']}")
                if contact.get("notes"):
                    parts.append(f"备注: {contact['notes']}")
                if contact.get("interaction_count"):
                    parts.append(f"交互次数: {contact['interaction_count']}")

        return "\n".join(parts) if parts else ""

    # ========== 批量应用 LLM 输出的记忆更新 ==========

    def apply_memory_updates(self, updates: dict, contact_name: str = None):
        """
        应用 LLM 返回的 memory_updates 字段。
        updates 格式: {
            "contact": {"relationship": "...", "notes": "..."},
            "user": {"communication_style": "..."}
        }
        """
        if not isinstance(updates, dict) or not updates:
            return

        if contact_name and updates.get("contact"):
            self.update_contact(contact_name, updates["contact"])

        if updates.get("user"):
            self.update_user_profile(updates["user"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    store = MemoryStore()

    # 测试联系人更新
    store.update_contact("彭宏刚", {
        "relationship": "导师",
        "notes": "关心项目进度"
    })

    # 测试用户画像更新
    store.update_user_profile({
        "communication_style": "半正式",
        "common_topics": ["深度学习", "项目管理"]
    })

    # 测试上下文组装
    ctx = store.get_context_for_llm("彭宏刚")
    print("=== LLM 上下文 ===")
    print(ctx)

    print(f"\n记忆文件位置: {store.memory_path}")
