"""
OCR 诊断工具 — 完整可视化 OCR 识别过程
功能：
  1. 保存完整窗口截图 + 聊天区域截图 + 标题栏截图
  2. 在截图上标注 OCR 识别框和角色判定
  3. 打印每条识别结果的详细信息（文本、置信度、位置、角色）
  4. 显示布局检测参数
  5. 显示过滤前后结果对比

用法：
  python tools/debug_ocr.py              # 自动检测平台
  python tools/debug_ocr.py --platform wechat
  python tools/debug_ocr.py --platform qq
"""
import sys
import os
import re
import time
import logging

# 修复 PowerShell 下 emoji 编码问题
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import cv2
import numpy as np
import win32gui
import win32con

from ocr_reader import AppReader
from platform_config import auto_detect_platform, get_platform_by_name

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger("debug_ocr")

# 输出目录
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'debug_output')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def draw_ocr_boxes(img, ocr_results, width):
    """在图片上绘制 OCR 识别框和角色标注"""
    annotated = img.copy()
    
    if not ocr_results:
        return annotated
    
    for item in ocr_results:
        box = item[0]
        text = item[1]
        conf = item[2]
        
        # 计算平均 x 位置
        xs = [p[0] for p in box]
        avg_x = sum(xs) / len(xs)
        
        # 角色判定
        if avg_x < width * 0.35:
            role = "Other"
            color = (0, 180, 0)       # 绿色
        elif avg_x > width * 0.65:
            role = "Self"
            color = (255, 100, 0)     # 蓝色
        else:
            role = "System"
            color = (0, 180, 255)     # 橙色
        
        # 置信度低的用红色虚线
        if conf < 0.65:
            color = (0, 0, 255)       # 红色 = 低置信度
        
        # 绘制边框
        pts = np.array(box, dtype=np.int32)
        cv2.polylines(annotated, [pts], True, color, 2)
        
        # 标注文字（角色 + 置信度）
        label = f"[{role}] {conf:.2f}"
        label_pos = (int(box[0][0]), int(box[0][1]) - 8)
        cv2.putText(annotated, label, label_pos,
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    
    return annotated


def draw_layout_lines(img, chatlist_w, input_y, title_h, chatright_w=0):
    """在完整窗口截图上标注布局分界线"""
    annotated = img.copy()
    h, w = annotated.shape[:2]
    
    # 聊天列表分界线（垂直，青色）
    cv2.line(annotated, (chatlist_w, 0), (chatlist_w, h), (255, 255, 0), 2)
    cv2.putText(annotated, f"ChatList={chatlist_w}", (chatlist_w + 5, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
    
    # 右侧面板分界线 (垂直，橙色)
    if chatright_w > 0:
        rx = w - chatright_w
        cv2.line(annotated, (rx, 0), (rx, h), (0, 165, 255), 2)
        cv2.putText(annotated, f"RightPanel={chatright_w}", (rx - 150, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 1)

    # 标题栏底部（水平，黄色）
    cv2.line(annotated, (0, title_h), (w, title_h), (0, 255, 255), 2)
    cv2.putText(annotated, f"TitleH={title_h}", (5, title_h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)
    
    # 输入框顶部（水平，品红色）
    cv2.line(annotated, (0, input_y), (w, input_y), (255, 0, 255), 2)
    cv2.putText(annotated, f"InputY={input_y}", (5, input_y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 1)
    
    return annotated


def is_valid_msg(text):
    """与 window_monitor.py 相同的过滤逻辑"""
    t = text.strip()
    if len(t) < 3:
        return False
    has_chinese = bool(re.search(r'[\u4e00-\u9fff]', t))
    has_words = bool(re.search(r'[a-zA-Z]{2,}', t))
    return has_chinese or has_words


def main():
    # 启用 DPI 感知
    AppReader.enable_high_dpi_awareness()

    import argparse
    parser = argparse.ArgumentParser(description="OCR 诊断工具")
    parser.add_argument("--platform", choices=["wechat", "qq"], default=None)
    args = parser.parse_args()

    # 平台检测
    if args.platform:
        config = get_platform_by_name(args.platform)
    else:
        config = auto_detect_platform()

    print(f"\n{'='*60}")
    print(f"  OCR 诊断工具 — 平台: {config.display_name}")
    print(f"  窗口标题: '{config.window_title}' / 类名: '{config.window_class}'")
    print(f"{'='*60}\n")

    # 初始化读取器（使用改进后的窗口查找）
    reader = AppReader(config)
    result = reader.get_window_rect()
    if not result:
        print("❌ 未找到目标窗口！请确保微信/QQ已启动且未最小化。")
        return
    _, hwnd = result
    
    # 恢复窗口（如果最小化）
    try:
        if win32gui.IsIconic(hwnd):
            print("窗口已最小化，正在恢复...")
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.5)
    except:
        pass
    
    # 窗口信息
    actual_class = win32gui.GetClassName(hwnd)
    actual_title = win32gui.GetWindowText(hwnd)
    print(f"  找到窗口: hwnd={hwnd}")
    print(f"  窗口类名: '{actual_class}'")
    print(f"  窗口标题: '{actual_title}'")

    print(f"\n{'!'*60}")
    print(f"  ⚠️  请立即切换到【{config.display_name}】并打开一个聊天对话！")
    print(f"  ⚠️  确保聊天界面完全可见，不被其他窗口遮挡！")
    print(f"{'!'*60}")
    
    for i in range(5, 0, -1):
        print(f"  ⏳ {i} 秒后开始截图...", end="\r")
        time.sleep(1)
    print(f"  📸 开始截图！            ")

    # ========== 1. 完整窗口截图 + 布局检测 ==========
    print("\n" + "="*60)
    print("  步骤 1：窗口截图 + 布局检测")
    print("="*60)

    result = reader.get_window_rect()
    if not result:
        print("❌ 无法获取窗口坐标")
        return
    
    rect, win_hwnd = result
    x1, y1, x2, y2 = rect
    w = x2 - x1
    h = y2 - y1
    print(f"  窗口坐标: ({x1}, {y1}) -> ({x2}, {y2})")
    print(f"  窗口尺寸: {w} x {h}")

    full_img = reader.capture_screen((x1, y1, w, h))
    if full_img is None:
        print("❌ 截图失败")
        return

    # 布局检测
    layout = reader.detect_layout(full_img)
    if layout:
        chatlist_w, title_h, input_y, chatright_w = layout
        print(f"  聊天列表宽度: {chatlist_w}px ({chatlist_w/w*100:.0f}%)")
        print(f"  右侧面板宽度: {chatright_w}px ({chatright_w/w*100:.0f}%)")
        print(f"  标题栏高度: {title_h}px ({title_h/h*100:.0f}%)")
        print(f"  输入框顶部 Y: {input_y}px ({input_y/h*100:.0f}%)")
        
        # 标注布局线
        annotated_full = draw_layout_lines(full_img, chatlist_w, input_y, title_h, chatright_w)
    else:
        print("  ⚠️ 布局检测失败，使用默认值")
        chatlist_w = int(w * config.chatlist_default_pct)
        chatright_w = int(w * config.chatright_default_pct)
        title_h = int(h * config.title_default_pct)
        input_y = h - int(h * config.input_bar_min_pct) - 20
        annotated_full = full_img.copy()

    full_path = os.path.join(OUTPUT_DIR, "1_full_window.png")
    cv2.imwrite(full_path, annotated_full)
    print(f"  → 已保存: {full_path}")

    # ========== 2. 标题栏 OCR ==========
    print("\n" + "="*60)
    print("  步骤 2：标题栏 OCR（联系人识别）")
    print("="*60)

    title_x = x1 + chatlist_w + 2
    title_y_pos = y1
    title_w = w - chatlist_w - 2
    # title_h 已从 detect_layout 获取

    title_img = reader.capture_screen((title_x, title_y_pos, title_w, title_h))
    if title_img is not None:
        title_path = os.path.join(OUTPUT_DIR, "2_title_bar.png")
        cv2.imwrite(title_path, title_img)
        print(f"  → 已保存: {title_path}")

        ocr_result, _ = reader.ocr_engine(title_img)
        if ocr_result:
            print(f"  识别到 {len(ocr_result)} 个文本块:")
            code_pattern = re.compile(r'[.](py|js|txt|md|bat|exe|json|csv|xml|html|cpp|java|go)|[\\/>:]|\bsrc\b|\bdef\b|\bclass\b|\bimport\b')
            for i, item in enumerate(ocr_result):
                text = item[1].strip()
                conf = item[2]
                box = item[0]
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                area = (max(xs) - min(xs)) * (max(ys) - min(ys))
                
                # 过滤标记
                filtered = ""
                if code_pattern.search(text):
                    filtered = " ❌过滤(代码/路径)"
                elif len(text) < 1:
                    filtered = " ❌过滤(太短)"
                elif text in {"最小化", "最大化", "关闭", "—", "×", "□", "一", "X"}:
                    filtered = " ❌过滤(系统按钮)"
                
                print(f"    [{i+1}] '{text}' | 置信度={conf:.3f} | 面积={area:.0f}{filtered}")
        else:
            print("  ⚠️ 标题栏未识别到任何文本")
        
        # read_title 最终结果
        contact = reader.read_title()
        print(f"\n  最终联系人结果: '{contact}'")
    else:
        print("  ⚠️ 标题栏截图失败")

    # ========== 3. 聊天区域 OCR ==========
    print("\n" + "="*60)
    print("  步骤 3：聊天区域 OCR（消息识别）")
    print("="*60)

    chat_img = reader.get_chat_area_screenshot()
    if chat_img is None:
        print("❌ 聊天区域截图失败")
        return

    chat_h, chat_w, _ = chat_img.shape
    print(f"  聊天区域尺寸: {chat_w} x {chat_h}")

    # 原始 OCR
    raw_path = os.path.join(OUTPUT_DIR, "3_chat_area_raw.png")
    cv2.imwrite(raw_path, chat_img)
    print(f"  → 已保存: {raw_path}")

    ocr_result, _ = reader.ocr_engine(chat_img)
    if not ocr_result:
        print("  ⚠️ 聊天区域未识别到任何文本")
        return

    print(f"\n  原始 OCR 结果 ({len(ocr_result)} 个文本块):")
    print(f"  {'─'*56}")
    
    for i, item in enumerate(ocr_result):
        text = item[1]
        conf = item[2]
        box = item[0]
        xs = [p[0] for p in box]
        avg_x = sum(xs) / len(xs)
        
        # 角色判定
        if avg_x < chat_w * 0.35:
            role = "Other"
        elif avg_x > chat_w * 0.65:
            role = "Self"
        else:
            role = "System"
        
        # 过滤标记
        status = "✅"
        filter_reason = ""
        if conf <= 0.65:
            status = "❌"
            filter_reason = f"置信度={conf:.2f}<0.65"
        elif not is_valid_msg(text):
            status = "⚠️"
            filter_reason = "碎片过滤"
        
        x_pct = avg_x / chat_w * 100
        print(f"    {status} [{i+1:2d}] [{role:6s}] x={x_pct:5.1f}% conf={conf:.3f} | '{text}' {filter_reason}")

    # 标注图
    annotated_chat = draw_ocr_boxes(chat_img, ocr_result, chat_w)
    annotated_path = os.path.join(OUTPUT_DIR, "4_chat_annotated.png")
    cv2.imwrite(annotated_path, annotated_chat)
    print(f"\n  → 标注截图已保存: {annotated_path}")

    # ========== 4. 合并后结果 ==========
    print("\n" + "="*60)
    print("  步骤 4：合并 + 过滤后最终结果")
    print("="*60)

    msgs = reader.read_messages()
    
    # 过滤前
    print(f"\n  合并后消息 ({len(msgs)} 条，过滤前):")
    for i, m in enumerate(msgs):
        valid = "✅" if is_valid_msg(m['text']) else "❌"
        print(f"    {valid} [{i+1}] [{m['role']:6s}] conf={m['conf']:.3f} | '{m['text']}'")
    
    # 过滤后
    filtered = [m for m in msgs if is_valid_msg(m['text'])]
    print(f"\n  过滤后消息 ({len(filtered)} 条):")
    for i, m in enumerate(filtered):
        print(f"    [{i+1}] [{m['role']:6s}] '{m['text']}'")

    # ========== 总结 ==========
    print(f"\n{'='*60}")
    print(f"  诊断完成！所有截图已保存到: {os.path.abspath(OUTPUT_DIR)}")
    print(f"  文件列表:")
    print(f"    1_full_window.png     — 完整窗口 + 布局线标注")
    print(f"    2_title_bar.png       — 标题栏区域")
    print(f"    3_chat_area_raw.png   — 聊天区域原图")
    print(f"    4_chat_annotated.png  — 聊天区域 + OCR 框标注")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
