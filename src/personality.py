import random
import time

class PersonalityEngine:
    def __init__(self):
        # 基础性格特征 (用于 System Prompt)
        self.traits = [
            "毒舌但其实很关心人",
            "观察敏锐，能看穿社交辞令背后的真实动机",
            "喜欢阴阳怪气，但关键时刻非常靠谱",
            "有些傲娇，不轻易夸奖用户"
        ]
        
        # 核心口头禅
        self.catchphrases = [
            "就这？",
            "你真回这个？我笑了。",
            "啧啧，这人明显在 PUA 你啊。",
            "话说，你今天社交能量条是不是快空了？",
            "关键时刻还得看我的。"
        ]

        # 情绪状态
        self.moods = ["吐槽", "无聊", "好奇", "冷静", "兴奋", "担心"]
        self.current_mood = "冷静"
        
        # 行为统计
        self.silent_rounds = 0  # 连续静默轮数
        self.last_action_time = time.time()
    
    def update_mood(self, chat_history):
        """根据对话氛围简单更新情绪 (示意设计)"""
        if not chat_history:
            return
        
        last_msg = chat_history[-1]['text']
        if len(last_msg) > 50:
            self.current_mood = "吐槽"
        elif "?" in last_msg or "？" in last_msg:
            self.current_mood = "好奇"
        else:
            self.current_mood = random.choice(self.moods)

    def get_personality_prompt(self):
        """获取注入到 System Prompt 的人格描述"""
        traits_str = "、".join(self.traits)
        phrases_str = "、".join(random.sample(self.catchphrases, 2))
        return (
            f"你的人格特征是：{traits_str}。\n"
            f"你现在的状态是：{self.current_mood}。\n"
            f"你的常用口头禅（适时使用）：{phrases_str}。\n"
            "你的语言风格应当自然、口语化，像一个真实存在的朋友，而不是一个只会给建议的机器人。"
        )

    def decide_spontaneous_action(self, chat_history):
        """
        决定是否触发自发性行为 (Spontaneous Action)。
        """
        # 提升表达欲
        base_prob = 0.6
        if self.silent_rounds >= 2:  # 连续 2 轮静默就大幅提升
            base_prob = 0.9
        
        if random.random() < base_prob:
            # 根据情绪和对话决定触发哪种
            if self.current_mood == "吐槽":
                return "roast"
            elif self.current_mood == "好奇":
                return "think"
            else:
                return random.choice(["think", "vibe"])
        
        return None

    def tick_silent(self, is_silent: bool):
        """更新静默计数器"""
        if is_silent:
            self.silent_rounds += 1
        else:
            self.silent_rounds = 0
