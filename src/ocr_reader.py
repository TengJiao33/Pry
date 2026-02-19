"""
OCR 阅读器模块 — 支持多平台（微信/QQ）的消息识别
通过截屏 + RapidOCR 识别聊天内容、联系人名称和消息角色。
"""
import logging
import re
import time

import cv2
import numpy as np
import win32api
import win32con
import win32gui
import win32ui
import ctypes
from rapidocr_onnxruntime import RapidOCR

from platform_config import PlatformConfig, WECHAT_CONFIG

logger = logging.getLogger(__name__)


class AppReader:
    """通用IM应用阅读器，通过OCR识别聊天消息"""

    def __init__(self, config: PlatformConfig = None):
        """
        初始化阅读器
        :param config: 平台配置，默认为微信
        """
        self.config = config or WECHAT_CONFIG

        # 启用 DPI 感知（适配高分屏缩放）
        self.enable_high_dpi_awareness()
        
        logger.info("正在初始化 RapidOCR 引擎...")
        self.ocr_engine = RapidOCR()
        logger.info("OCR 引擎就绪")

        # 缓存布局参数
        self._layout_params = None
        self._last_window_rect = None

    @staticmethod
    def enable_high_dpi_awareness():
        """
        开启 Windows 进程 DPI 感知，确保获取的是物理像素坐标而非虚拟坐标。
        适配高分屏缩放（如 125%, 150%, 200%）。
        """
        try:
            # 统一使用 PROCESS_SYSTEM_DPI_AWARE (1)
            shcore = ctypes.windll.shcore
            shcore.SetProcessDpiAwareness(1)
            logger.debug("DPIAware: 已通过 shcore 设置感知 (Level 1)")
        except Exception:
            try:
                # 后备方案 SetProcessDPIAware (Windows Vista+)
                user32 = ctypes.windll.user32
                user32.SetProcessDPIAware()
                logger.debug("DPIAware: 已通过 user32 设置感知")
            except Exception as e:
                logger.warning(f"DPIAware: 无法设置 DPI 感知: {e}")

    # ========== 窗口操作 ==========

    def get_window_rect(self):
        """
        查找目标IM窗口并返回坐标。
        采用多重回退策略：类名+标题 -> 仅类名 -> 仅标题。
        :return: ((left, top, right, bottom), hwnd) 或 None
        """
        candidates = []
        
        def check_hwnd(hwnd):
            if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return
            try:
                rect = win32gui.GetWindowRect(hwnd)
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                if w > 200 and h > 200: # 过滤掉微小窗口
                    candidates.append((w * h, rect, hwnd))
            except:
                pass

        def enum_callback(hwnd, _):
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            
            # 策略 1: 完美匹配
            if cls == self.config.window_class and title == self.config.window_title:
                check_hwnd(hwnd)
            # 策略 2: 类名匹配 (针对 QQ/微信 这种类名比较独特的)
            elif cls == self.config.window_class:
                check_hwnd(hwnd)
            # 策略 3: 标题匹配
            elif title == self.config.window_title:
                check_hwnd(hwnd)
        
        win32gui.EnumWindows(enum_callback, None)
        
        if not candidates:
            return None
        
        # 选面积最大的窗口
        candidates.sort(key=lambda x: x[0], reverse=True)
        _, rect, hwnd = candidates[0]
        logger.debug(f"找到窗口: hwnd={hwnd}, rect={rect}, 候选数={len(candidates)}")
        return rect, hwnd

    def capture_screen(self, region=None):
        """
        截取指定区域的屏幕截图（使用 BitBlt 高速截图）。
        :param region: (left, top, width, height) 或 None 截全屏
        :return: BGR numpy array 或 None
        """
        try:
            hwin = win32gui.GetDesktopWindow()

            if region:
                left, top, width, height = region
            else:
                width = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
                height = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
                left = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
                top = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)

            hwindc = win32gui.GetWindowDC(hwin)
            srcdc = win32ui.CreateDCFromHandle(hwindc)
            memdc = srcdc.CreateCompatibleDC()
            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(srcdc, width, height)
            memdc.SelectObject(bmp)
            memdc.BitBlt((0, 0), (width, height), srcdc, (left, top), win32con.SRCCOPY)

            # 转换为 numpy 数组
            signed_ints = bmp.GetBitmapBits(True)
            img = np.frombuffer(signed_ints, dtype='uint8')
            img.shape = (height, width, 4)

            srcdc.DeleteDC()
            memdc.DeleteDC()
            win32gui.ReleaseDC(hwin, hwindc)
            win32gui.DeleteObject(bmp.GetHandle())

            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None

    # ========== 布局检测 ==========

    # ========== 布局检测 (Icon-Based V12) ==========

    def detect_layout(self, img):
        """
        布局检测（多信号融合）：
        1) 聊天列表分界线：基于左右亮度差的稳定峰值（替代“加号图标锚点”）。
        2) 标题栏高度：优先检测上部水平分隔线，并做强约束防止飘到 150px+。
        3) 输入框顶部：在下半区寻找“连续水平线”峰值，避免误检消息气泡边缘。
        4) 右侧面板：仅在差异持续且纹理密度足够时启用。
        """
        if img is None:
            return None

        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 默认回退值（始终可用）
        default_cl_w = int(w * self.config.chatlist_default_pct)
        default_cr_w = int(w * self.config.chatright_default_pct)
        default_t_h = int(h * self.config.title_default_pct)
        default_i_y = h - int(h * self.config.input_bar_min_pct) - 20

        # ---------- 1) 聊天列表分界线 ----------
        chat_x_min = int(w * 0.16)
        chat_x_max = int(w * 0.56)
        chat_band_y1 = int(h * 0.12)
        chat_band_y2 = int(h * 0.88)
        chat_k = max(8, int(w * 0.01))

        if chat_x_max <= chat_x_min + chat_k + 2:
            return default_cl_w, default_t_h, default_i_y, default_cr_w

        gray_f = gray.astype(np.float32)
        chat_scores = []
        for x in range(chat_x_min, chat_x_max):
            if x - chat_k < 0 or x + chat_k + 1 >= w:
                chat_scores.append(0.0)
                continue
            left_mean = gray_f[chat_band_y1:chat_band_y2, x - chat_k:x].mean()
            right_mean = gray_f[chat_band_y1:chat_band_y2, x + 1:x + chat_k + 1].mean()
            chat_scores.append(abs(float(left_mean - right_mean)))

        chat_scores = np.array(chat_scores, dtype=np.float32)
        if len(chat_scores) > 9:
            chat_scores = np.convolve(chat_scores, np.ones(9) / 9.0, mode='same')
        rel_idx = int(np.argmax(chat_scores))
        cl_w = chat_x_min + rel_idx

        # 防止离谱：分界线限制到常见比例区间
        min_cl = int(w * 0.18)
        max_cl = int(w * 0.45)
        if not (min_cl <= cl_w <= max_cl):
            cl_w = default_cl_w
        logger.debug(f"Layout chatlist: x={cl_w}, score={chat_scores[rel_idx]:.2f}")

        # ---------- 2) 标题栏高度 ----------
        # 使用上部横向梯度 + 强约束，避免误飘到消息区域
        title_x1 = min(w - 2, cl_w + 20)
        title_x2 = min(w - 1, int(w * 0.95))
        if title_x2 <= title_x1 + 10:
            t_h = default_t_h
        else:
            row_diff = np.abs(
                gray_f[1:, title_x1:title_x2] - gray_f[:-1, title_x1:title_x2]
            )
            # 用中位数抑制局部文字/头像尖峰
            row_score = np.median(row_diff, axis=1)
            if len(row_score) > 7:
                row_score = np.convolve(row_score, np.ones(7) / 7.0, mode='same')

            y1 = int(h * 0.03)
            y2 = int(h * 0.20)
            if y2 <= y1 + 5:
                t_h = default_t_h
            else:
                seg = row_score[y1:y2]
                strong = np.where(seg >= (np.median(seg) + np.std(seg) * 0.6))[0]
                if len(strong) > 0:
                    # 取最早的显著分隔线，避免命中上方消息气泡边缘
                    t_h = y1 + int(strong[0]) + 6
                else:
                    t_h = default_t_h

        t_h = int(np.clip(t_h, int(h * 0.045), int(h * 0.10)))

        # ---------- 3) 输入框顶部 ----------
        content_x1 = min(w - 2, cl_w + 10)
        content_x2 = max(content_x1 + 20, w - 10)
        cr_w = 0

        row_diff_main = np.abs(
            gray_f[1:, content_x1:content_x2] - gray_f[:-1, content_x1:content_x2]
        )
        # 使用上分位统计，突出“连续线”而非局部字符
        row_score_main = np.percentile(row_diff_main, 75, axis=1)
        if len(row_score_main) > 9:
            row_score_main = np.convolve(row_score_main, np.ones(9) / 9.0, mode='same')

        iy1 = int(h * 0.55)
        iy2 = int(h * 0.94)
        i_y = default_i_y
        if iy2 > iy1 + 5:
            seg = row_score_main[iy1:iy2]
            threshold = np.median(seg) + np.std(seg) * 1.0
            strong = np.where(seg >= threshold)[0]
            if len(strong) > 0:
                # 取最靠下的显著线，通常是输入框上边界
                i_y = iy1 + int(strong[-1])
        i_y = int(np.clip(i_y, int(h * 0.58), int(h * 0.90)))

        # ---------- 4) 右侧面板（可选） ----------
        # 仅在“差异持续 + 右侧有足够纹理”时启用，减少误判
        rp_x_min = int(w * 0.62)
        rp_x_max = int(w * 0.90)
        rp_k = max(10, int(w * 0.012))
        best_rp_x = None
        best_rp_score = 0.0
        best_rp_diffs = None

        for x in range(rp_x_min, rp_x_max):
            if x - rp_k < 0 or x + rp_k + 1 >= w:
                continue

            diffs = []
            for a, b in ((0.20, 0.35), (0.35, 0.55), (0.55, 0.72)):
                y1 = int(h * a)
                y2 = int(h * b)
                left_m = gray_f[y1:y2, x - rp_k:x].mean()
                right_m = gray_f[y1:y2, x + 1:x + rp_k + 1].mean()
                diffs.append(abs(float(left_m - right_m)))

            score = min(diffs) * 0.7 + (sum(diffs) / len(diffs)) * 0.3
            if score > best_rp_score:
                best_rp_score = score
                best_rp_x = x
                best_rp_diffs = diffs

        if best_rp_x is not None:
            panel_w = w - best_rp_x
            min_panel_w = int(w * 0.10)
            max_panel_w = int(w * 0.30)
            if min_panel_w <= panel_w <= max_panel_w:
                min_band_diff = min(best_rp_diffs) if best_rp_diffs else 0.0
                if min_band_diff > 8.0 and best_rp_score > 10.0:
                    cr_w = panel_w

        # 右侧面板存在时重新约束输入区域，避免把成员面板滚动条识别进来
        if cr_w > 0:
            content_x2 = max(content_x1 + 20, w - cr_w - 5)
            row_diff_main = np.abs(
                gray_f[1:, content_x1:content_x2] - gray_f[:-1, content_x1:content_x2]
            )
            row_score_main = np.percentile(row_diff_main, 75, axis=1)
            if len(row_score_main) > 9:
                row_score_main = np.convolve(row_score_main, np.ones(9) / 9.0, mode='same')
            seg = row_score_main[iy1:iy2]
            threshold = np.median(seg) + np.std(seg) * 1.0
            strong = np.where(seg >= threshold)[0]
            if len(strong) > 0:
                i_y = int(np.clip(iy1 + int(strong[-1]), int(h * 0.58), int(h * 0.90)))

        # 安全兜底：保证几何关系正确
        if i_y <= t_h + 120:
            i_y = default_i_y
        if cl_w <= 80 or cl_w >= w - 180:
            cl_w = default_cl_w

        logger.info(
            f"Layout detect -> CL={cl_w}, TH={t_h}, IY={i_y}, CR={cr_w}, "
            f"defaults=({default_cl_w},{default_t_h},{default_i_y},{default_cr_w})"
        )
        return cl_w, t_h, i_y, cr_w

    # ========== 聊天区域截图 ==========

    def get_chat_area_screenshot(self):
        """
        截取聊天消息区域（排除侧边栏、标题栏、输入框）。
        窗口尺寸变化时自动重新检测布局。
        :return: BGR numpy array 或 None
        """
        result = self.get_window_rect()
        if not result:
            return None

        rect, hwnd = result
        x1, y1, x2, y2 = rect
        w = x2 - x1
        h = y2 - y1

        # 窗口尺寸变化时重新检测布局
        if self._last_window_rect is None or \
           abs(w - self._last_window_rect[2]) > 5 or \
           abs(h - self._last_window_rect[3]) > 5:
            logger.info("窗口尺寸变化，重新计算布局...")
            full_img = self.capture_screen((x1, y1, w, h))
            if full_img is not None:
                self._layout_params = self.detect_layout(full_img)
            self._last_window_rect = (x1, y1, w, h)

        # 应用布局参数（百分比回退值）
        chatlist_w = int(w * self.config.chatlist_default_pct)
        chatright_w = int(w * self.config.chatright_default_pct)
        title_h = int(h * self.config.title_default_pct)
        input_y_pos = h - int(h * self.config.input_bar_min_pct) - 20

        if self._layout_params:
            chatlist_w, title_h, input_y_pos, chatright_w = self._layout_params

        roi_x = x1 + chatlist_w + 3
        roi_y = y1 + title_h
        roi_w = w - chatlist_w - chatright_w - 5
        roi_h = input_y_pos - title_h

        if roi_w <= 50 or roi_h <= 50:
            return None

        return self.capture_screen((roi_x, roi_y, roi_w, roi_h))

    # ========== 标题栏识别（联系人名称） ==========

    def read_title(self):
        """
        OCR 识别聊天窗口标题栏，提取当前联系人名称。
        :return: 联系人名称字符串 或 None
        """
        result = self.get_window_rect()
        if not result:
            return None

        rect, hwnd = result
        x1, y1, x2, y2 = rect
        w = x2 - x1
        h = y2 - y1

        # 确定聊天区域的起始 x（跳过侧边栏+聊天列表）
        chatlist_w = int(w * self.config.chatlist_default_pct)
        chatright_w = int(w * self.config.chatright_default_pct)
        title_h = int(h * self.config.title_default_pct)
        
        if self._layout_params:
            chatlist_w, title_h, _, chatright_w = self._layout_params

        # 标题区域：从聊天列表右边到窗口右面板左边，高度为标题栏
        title_x = x1 + chatlist_w + 2
        title_y = y1
        title_w = w - chatlist_w - chatright_w - 2
        title_region_h = title_h

        if title_w <= 50 or title_region_h <= 10:
            return None

        title_img = self.capture_screen((title_x, title_y, title_w, title_region_h))
        if title_img is None:
            return None

        ocr_result, _ = self.ocr_engine(title_img)
        if not ocr_result:
            return None

        # 过滤系统按钮文字和路径/代码特征
        system_words = {"最小化", "最大化", "关闭", "—", "×", "□", "一", "X"}
        code_pattern = re.compile(
            r'[.](py|js|txt|md|bat|exe|json|csv|xml|html|cpp|java|go)'
            r'|[\\/\>:]|\bsrc\b|\bdef\b|\bclass\b|\bimport\b'
        )
        candidates = []
        for item in ocr_result:
            text = item[1].strip()
            box = item[0]
            if text in system_words or len(text) < 1:
                continue
            if code_pattern.search(text):
                logger.debug(f"标题栏过滤代码/路径特征: {text}")
                continue
            # 计算文本块面积
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            area = (max(xs) - min(xs)) * (max(ys) - min(ys))
            candidates.append((text, area))

        if not candidates:
            return None

        # 取面积最大的（通常是联系人名称）
        best = max(candidates, key=lambda c: c[1])
        contact_name = best[0]
        logger.debug(f"识别到联系人: {contact_name}")
        return contact_name

    # ========== 消息识别 ==========

    def read_messages(self):
        """
        OCR 识别聊天区域的所有可见消息。
        :return: 消息列表 [{"role": "Self"/"Other"/"System", "text": "...", "conf": float, "box": [...]}]
        """
        img = self.get_chat_area_screenshot()
        if img is None:
            return []

        height, width, _ = img.shape

        ocr_result, _ = self.ocr_engine(img)

        raw_messages = []
        if ocr_result:
            for item in ocr_result:
                text = item[1]
                conf = item[2]
                box = item[0]

                xs = [p[0] for p in box]
                avg_x = sum(xs) / len(xs)

                # 根据水平位置判断角色 (基于相对宽度)
                # 左侧 35% 为 Other, 右侧 65% 为 Self, 中间为 System
                rel_x = avg_x / width
                if rel_x < 0.35:
                    role = "Other"
                elif rel_x > 0.65:
                    role = "Self"
                else:
                    role = "System"

                if conf > 0.60: # 稍微降低置信度阈值以捕获更多内容
                    raw_messages.append({
                        "role": role,
                        "text": text,
                        "conf": conf,
                        "box": box
                    })

        return self.merge_messages(raw_messages)

    # ========== 消息合并 ==========

    def merge_messages(self, raw_msgs):
        """
        合并属于同一消息气泡的相邻文本块。
        规则：相同角色 + 垂直距离小于1.5倍行高 → 合并
        """
        if not raw_msgs:
            return []

        # 按 Y 坐标排序（从上到下）
        raw_msgs.sort(key=lambda m: m['box'][0][1])

        merged = []
        current = None

        for msg in raw_msgs:
            if current is None:
                current = msg
                continue

            if msg['role'] == current['role']:
                # 计算垂直距离
                y1 = current['box'][2][1]  # 当前消息底部 Y
                y2 = msg['box'][0][1]      # 新消息顶部 Y
                line_h = y1 - current['box'][0][1]  # 当前行高
                distance = y2 - y1

                if distance < line_h * 1.5:
                    # 合并
                    current['text'] += " " + msg['text']
                    current['conf'] = min(current['conf'], msg['conf'])
                    current['box'][2] = msg['box'][2]
                    current['box'][3] = msg['box'][3]
                    continue

            merged.append(current)
            current = msg

        if current:
            merged.append(current)

        return merged


# ===== 兼容性别名 =====
WeChatReader = AppReader  # 向后兼容旧代码


if __name__ == "__main__":
    from platform_config import auto_detect_platform

    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    config = auto_detect_platform()
    reader = AppReader(config)

    print("等待2秒...")
    time.sleep(2)

    # 测试标题栏识别
    contact = reader.read_title()
    print(f"当前联系人: {contact}")

    # 测试消息识别
    print("正在识别消息...")
    msgs = reader.read_messages()
    for m in msgs:
        print(f"  [{m['conf']:.2f}] {m['role']}: {m['text']}")

    # 保存调试截图
    img = reader.get_chat_area_screenshot()
    if img is not None:
        cv2.imwrite("debug_ocr_roi.png", img)
        print("\n调试截图已保存: debug_ocr_roi.png")
