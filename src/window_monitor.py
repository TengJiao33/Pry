import argparse
import logging
import time
import threading

from llm_client import LLMClient
from message_utils import fingerprint_messages, normalize_messages
from memory_store import MemoryStore
from ocr_reader import AppReader
from platform_config import auto_detect_platform, get_platform_by_name
from popup_window import PopupWindow
import win32gui

# ========== 日志配置 ==========

LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
LOG_DATE_FORMAT = '%H:%M:%S'

logger = logging.getLogger("pry")

def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    logging.getLogger("rapidocr_onnxruntime").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


class AIWorker:
    """
    Run at most one LLM task at a time and keep only the newest pending task.
    This prevents thread explosion when OCR updates arrive quickly.
    """

    def __init__(self, llm: LLMClient, memory: MemoryStore, popup: PopupWindow):
        self.llm = llm
        self.memory = memory
        self.popup = popup
        self._lock = threading.Lock()
        self._busy = False
        self._pending = None

    def submit(self, chat_history, contact_name):
        with self._lock:
            self._pending = (list(chat_history), contact_name)
            if self._busy:
                return
            self._busy = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            with self._lock:
                task = self._pending
                self._pending = None

            if task is None:
                with self._lock:
                    self._busy = False
                return

            chat_history, contact_name = task
            start_time = time.time()
            try:
                memory_context = self.memory.get_context_for_llm(contact_name)
                res = self.llm.analyze_chat(
                    chat_history,
                    contact_name=contact_name,
                    memory_context=memory_context,
                )
            except Exception:
                logger.exception("AI 处理线程异常")
                continue

            elapsed = time.time() - start_time
            logger.debug(f"AI 分析耗时: {elapsed:.2f}s")

            if not res:
                continue

            action = res.get("action")
            content = res.get("content", "")
            if action and action != "none" and content:
                self.popup.show(action, content)
                print(f"\n  [{action.upper()}] {content}")

            updates = res.get("memory_updates")
            if updates:
                self.memory.apply_memory_updates(updates, contact_name)

# ========== 监控逻辑 (线程运行) ==========

def monitor_loop(args, popup):
    # 平台检测
    if args.platform:
        config = get_platform_by_name(args.platform)
        logger.info(f"手动指定平台: {config.display_name}")
    else:
        config = auto_detect_platform()

    # 初始化 OCR
    try:
        reader = AppReader(config)
    except Exception as e:
        logger.error(f"OCR 引擎初始化失败: {e}")
        return

    # 初始化 LLM
    llm = LLMClient()
    if llm.client:
        logger.info(f"🧠 AI 大脑在线: {llm.provider} ({llm.model})")
    else:
        logger.warning("🧠 AI 大脑离线: 未配置 API Key")

    # 初始化记忆系统
    memory = MemoryStore()
    logger.info(f"💾 记忆系统就绪: {memory.memory_path}")
    ai_worker = AIWorker(llm=llm, memory=memory, popup=popup)

    print(f"\n✅ Pry 监控已启动 [{config.display_name}]")
    print(f"   轮询间隔: {args.interval}s | 按 Ctrl+C 停止")
    print(f"   请保持 {config.display_name} 窗口打开（不要最小化）\n")

    last_fingerprint = None
    last_contact = None

    while True:
        try:
            # 0. 窗口状态检测：只要不是最小化就工作
            target_hwnd = None
            rect_result = reader.get_window_rect()
            if rect_result:
                target_hwnd = rect_result[1]
            
            if not target_hwnd or win32gui.IsIconic(target_hwnd):
                time.sleep(args.interval)
                continue

            # 1. 读取消息
            start_ocr = time.time()
            raw_msgs = reader.read_messages()

            msgs = normalize_messages(
                raw_msgs,
                min_len=args.min_msg_len,
                include_system=args.include_system,
            )

            end_ocr = time.time()

            # 去噪后无有效消息，跳过（不更新指纹）
            if not msgs:
                time.sleep(args.interval)
                continue

            logger.debug(f"OCR 识别耗时: {end_ocr - start_ocr:.2f}s, 有效消息: {len(msgs)} 条")

            # 2. 去重（稳定指纹比对）
            current_fingerprint = fingerprint_messages(msgs)

            if current_fingerprint == last_fingerprint:
                time.sleep(args.interval)
                continue

            # 3. 识别联系人
            contact_name = reader.read_title()
            if contact_name:
                if contact_name != last_contact:
                    logger.info(f"👤 当前联系人: {contact_name}")
                    last_contact = contact_name

            # 4. 显示新消息 (终端保留日志)
            print(f"\n[{time.strftime('%H:%M:%S')}] 新消息 "
                  f"{'('+contact_name+')' if contact_name else ''}:")
            for m in msgs:
                icon = "👤" if m['role'] == "Self" else "💬"
                label = m['role']
                if contact_name and m['role'] == "Other":
                    label = contact_name
                print(f"  {icon} [{label}] {m['text']}")

            # 5. AI 分析 (单线程顺序处理，仅保留最新任务)
            if llm.client:
                ai_worker.submit(msgs, contact_name)

            last_fingerprint = current_fingerprint
            time.sleep(args.interval)

        except Exception:
            logger.exception("监控回路异常，将在下一轮继续")
            time.sleep(args.interval)

# ========== 主入口 ==========

def main():
    # 启用 DPI 感知
    AppReader.enable_high_dpi_awareness()
    
    parser = argparse.ArgumentParser(description="Pry - 非侵入式社交AI助手")
    parser.add_argument("--platform", choices=["wechat", "qq"], default=None,
                        help="指定平台（不指定则自动检测）")
    parser.add_argument("--debug", action="store_true", help="启用调试日志")
    parser.add_argument("--interval", type=float, default=2.0, help="轮询间隔（秒）")
    parser.add_argument("--min-msg-len", type=int, default=2, help="消息最小长度过滤阈值")
    parser.add_argument("--include-system", action="store_true", help="包含 System 角色文本")
    args = parser.parse_args()

    setup_logging(debug=args.debug)
    
    # 启动弹窗系统 (主线程)
    popup = PopupWindow()
    
    # 启动监控逻辑 (后台线程)
    monitor_thread = threading.Thread(target=monitor_loop, args=(args, popup), daemon=True)
    monitor_thread.start()
    
    logger.info("UI 主循环已启动")
    popup.start()

if __name__ == "__main__":
    main()
