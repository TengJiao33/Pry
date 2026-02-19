"""
弹窗系统测试 — 测试统一暗色主题、自适应高度、弹窗替换、智能时长
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from popup_window import PopupWindow
import threading
import time


def run_test():
    pw = PopupWindow()

    def trigger_test_messages():
        print("等待 2 秒后开始弹窗测试...\n")
        time.sleep(2)

        test_cases = [
            ("suggest", "试试回：好哒，没问题！"),

            ("roast",
             "这人的回复也太敷衍了吧？就一个'嗯'字打发你？"
             "你值得更走心的回复。"),

            ("think",
             "我注意到对方最近三条消息的回复间隔越来越长（从2分钟到15分钟），"
             "而且语气从热情变得很敷衍。结合之前的聊天记录来看，"
             "对方可能正在忙别的事情，或者对当前话题失去了兴趣。"
             "建议换一个对方可能感兴趣的话题试试。"),

            ("warn", "对方的措辞带有明显的情绪操控迹象，注意保护自己的边界。"),

            ("vibe", "今天的聊天气氛很愉快，继续保持！"),
        ]

        for action, content in test_cases:
            print(f"弹出: [{action}] {content[:30]}...")
            pw.show(action, content)
            time.sleep(3)

        print("\n测试完成。弹窗将自动消失。")

    threading.Thread(target=trigger_test_messages, daemon=True).start()
    pw.start()


if __name__ == "__main__":
    run_test()
