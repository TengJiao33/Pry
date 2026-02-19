"""
LLM 客户端模块 — 连接豆包/DeepSeek，分析聊天上下文并返回建议。
支持接收记忆上下文和联系人信息，输出包含 memory_updates 的增强响应。
"""
import json
import logging
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

try:
    from .personality import PersonalityEngine
except ImportError:
    from personality import PersonalityEngine

load_dotenv()

logger = logging.getLogger(__name__)
VALID_ACTIONS = {"suggest", "roast", "think", "vibe", "warn", "none"}


class LLMClient:
    def __init__(self):
        self.provider = "unknown"
        self.api_key = None
        self.base_url = None
        self.model = None

        # 优先豆包
        if os.getenv("DOUBAO_API_KEY") and os.getenv("DOUBAO_ENDPOINT_ID"):
            self.provider = "doubao"
            self.api_key = os.getenv("DOUBAO_API_KEY")
            self.base_url = "https://ark.cn-beijing.volces.com/api/v3"
            self.model = os.getenv("DOUBAO_ENDPOINT_ID")
            logger.info(f"LLM: 使用豆包 (Endpoint: {self.model})")

        # 其次 DeepSeek
        elif os.getenv("DEEPSEEK_API_KEY"):
            self.provider = "deepseek"
            self.api_key = os.getenv("DEEPSEEK_API_KEY")
            self.base_url = "https://api.deepseek.com"
            self.model = "deepseek-chat"
            logger.info("LLM: 使用 DeepSeek")

        if not self.api_key:
            logger.warning("未找到 API Key (DOUBAO_API_KEY 或 DEEPSEEK_API_KEY)，LLM 已禁用")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        
        self.personality = PersonalityEngine()

    @staticmethod
    def _extract_json_block(text: str) -> str:
        if not text:
            return ""

        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # Fast path: full string is valid JSON object.
        if cleaned.startswith("{") and cleaned.endswith("}"):
            return cleaned

        # Fallback: find first balanced JSON object.
        start = cleaned.find("{")
        if start < 0:
            return ""

        depth = 0
        for idx, ch in enumerate(cleaned[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return cleaned[start: idx + 1]

        # Last chance: a permissive regex block (for malformed wrappers).
        match = re.search(r"\{[\s\S]*\}", cleaned)
        return match.group(0) if match else ""

    @staticmethod
    def _normalize_result(parsed: dict) -> dict:
        if not isinstance(parsed, dict):
            return {"action": "none", "content": "", "memory_updates": {}}

        action = str(parsed.get("action", "none")).lower().strip()
        if action not in VALID_ACTIONS:
            action = "none"

        content = str(parsed.get("content", "")).strip()
        if action == "none":
            content = ""
        elif not content:
            action = "none"

        memory_updates = parsed.get("memory_updates", {})
        if not isinstance(memory_updates, dict):
            memory_updates = {}

        # Keep known sections only and ensure each is a dict.
        contact_updates = memory_updates.get("contact")
        user_updates = memory_updates.get("user")
        normalized_updates = {}
        if isinstance(contact_updates, dict):
            normalized_updates["contact"] = contact_updates
        if isinstance(user_updates, dict):
            normalized_updates["user"] = user_updates

        return {
            "action": action,
            "content": content,
            "memory_updates": normalized_updates,
        }

    @classmethod
    def parse_response_text(cls, result_text: str) -> dict | None:
        json_block = cls._extract_json_block(result_text)
        if not json_block:
            return None
        parsed = json.loads(json_block)
        return cls._normalize_result(parsed)

    def analyze_chat(self, chat_history, contact_name: str = None, memory_context: str = ""):
        """
        分析聊天上下文，返回建议和记忆更新。

        :param chat_history: 消息列表 [{"role": "Self"/"Other", "text": "..."}]
        :param contact_name: 当前聊天对象名称（OCR 识别）
        :param memory_context: 记忆系统提供的上下文字符串
        :return: {
            "action": "suggest" | "none",
            "content": "建议内容",
            "memory_updates": {
                "contact": {"relationship": "...", "notes": "..."},
                "user": {"communication_style": "..."}
            }
        } 或 None
        """
        if not self.client or not chat_history:
            return None

        # 格式化消息上下文
        context_str = ""
        if contact_name:
            context_str += f"当前聊天对象: {contact_name}\n\n"

        for msg in chat_history[-10:]:
            label = msg['role']
            if contact_name and msg['role'] == "Other":
                label = contact_name
            context_str += f"{label}: {msg['text']}\n"

        # 更新情绪
        self.personality.update_mood(chat_history)
        
        # 决定是否强制触发某种 Action (自发性)
        forced_action = self.personality.decide_spontaneous_action(chat_history)

        # 构建 System Prompt
        system_prompt = self._build_system_prompt(memory_context, forced_action)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"当前对话上下文:\n{context_str}"}
                ],
                temperature=0.7,
                timeout=30,
            )

            result_text = response.choices[0].message.content
            parsed = self.parse_response_text(result_text)
            if not parsed:
                logger.warning(f"LLM 返回非 JSON: {str(result_text)[:200]}...")
                return None
            
            # 更新静默计数器
            self.personality.tick_silent(parsed.get("action") == "none")
            
            logger.debug(f"LLM 响应: {parsed}")
            return parsed

        except json.JSONDecodeError as e:
            logger.warning(f"LLM 返回 JSON 解析失败: {str(result_text)[:200]}... 错误: {e}")
            return None
        except Exception as e:
            logger.error(f"LLM 调用失败 ({self.provider}): {e}")
            return None

    def _build_system_prompt(self, memory_context: str = "", forced_action: str = None) -> str:
        """构建包含记忆上下文和人格注入的 System Prompt"""

        personality_info = self.personality.get_personality_prompt()

        base_prompt = f"""你是 Pry，一个有个性的社交辅助 AI，用户的毒舌隐形伙伴。
你在后台默默监控聊天（"Self" 是用户，"Other" 是对方），根据你的性格和当前情绪进行输出。

## 你的人格信息
{personality_info}

## 行为指南
1. **suggest**: 对方在施压、PUA、需要技术性回复建议，或者你需要巧妙引导对话时使用。
2. **roast**: 对话太无聊、用户发了尴尬消息、或者你单纯想吐槽对方/用户时使用。
3. **think**: 分享你的洞察力，比如看穿了对方的真实意图。
4. **vibe**: 调节气氛，或者对当前社交状态进行评论。
5. **warn**: 检测到明显的恶意、PUA 或人身攻击时发出警告。
6. **none**: 对话内容完全不值得评论，或者是 OCR 噪声/乱码时使用。

## 重要原则
1. **积极输出**：只要对话有实质内容，你就应该发表看法。你是朋友，不是旁观者。
2. **处理 OCR 噪声**：后台监控可能会捕获到短小的字词（如“好的”、“收到”）、UI 碎片或乱码字符。
   - 对于有语义的消息（哪怕只是一个“好”字），如果你觉得值得吐槽或建议，请正常输出。
   - 如果消息明显是 OCR 错误（如“✕”、“一”、“登录”等来自 UI 的单字）或缺乏任何基本语义，输出 none。
3. 对于正常对话，**禁止输出 none**，必须从 suggest/roast/think/vibe/warn 中选择一个。
"""
        if forced_action:
            base_prompt += f"\n**当前你必须执行一次 {forced_action} 操作，绝对禁止输出 none！这是强制指令。**\n"

        base_prompt += """
## 输出格式 (严格纯 JSON)
{
  "action": "suggest" | "roast" | "think" | "vibe" | "warn" | "none",
  "content": "你要说的话（如果是 suggest，则是建议回复内容；如果是 roast/think/vibe，则是你的吐槽或想法；如果 none 则为空字符串）",
  "memory_updates": {
    "contact": {"relationship": "关系更新", "notes": "关键观察"},
    "user": {"communication_style": "沟通风格观察"}
  }
}
"""

        if memory_context:
            base_prompt += f"\n## 已知记忆\n{memory_context}\n"

        return base_prompt


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    client = LLMClient()
    history = [
        {"role": "Other", "text": "项目进度怎么又延期了？"},
        {"role": "Other", "text": "上次不是说好了这周完成吗"},
        {"role": "Self", "text": "抱歉老师，遇到了一些技术问题"}
    ]

    memory_ctx = "=== 关于「彭宏刚」的记忆 ===\n关系: 导师\n备注: 对进度要求严格"

    print("正在分析...")
    res = client.analyze_chat(history, contact_name="彭宏刚", memory_context=memory_ctx)
    print(json.dumps(res, ensure_ascii=False, indent=2))
