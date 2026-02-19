"""
平台配置模块 — 定义各IM平台的窗口特征和布局参数
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PlatformConfig:
    """IM平台配置"""
    name: str               # 内部标识: "wechat" / "qq"
    display_name: str        # 显示名称: "微信" / "QQ"
    window_title: str        # 窗口标题（用于 FindWindow）
    window_class: str        # 窗口类名（用于 FindWindow）

    # 布局检测参数 —— 全部使用百分比，适配任意窗口尺寸
    sidebar_scan_pct: float = 0.05            # 侧边栏扫描范围（占宽度%）
    chatlist_scan_pct: tuple = (0.15, 0.55)   # 聊天列表分界线扫描范围（占宽度%）
    title_scan_pct: tuple = (0.04, 0.15)      # 标题栏高度扫描范围（占高度%）
    chatlist_default_pct: float = 0.30         # 默认聊天列表宽度（回退值，占宽度%）
    chatright_default_pct: float = 0.20        # 默认右侧面板宽度 (针对群聊，占宽度%)
    title_default_pct: float = 0.07            # 默认标题栏高度（回退值，占高度%）
    input_bar_min_pct: float = 0.08            # 输入框最小高度（占高度%）
    edge_threshold: int = 15                   # 边缘检测阈值
    color_diff_threshold: int = 8              # 分界线两侧颜色差异阈值


# ===== 预置平台配置 =====

WECHAT_CONFIG = PlatformConfig(
    name="wechat",
    display_name="微信",
    window_title="微信",
    window_class="Qt51514QWindowIcon",
    chatlist_scan_pct=(0.15, 0.55),
    title_scan_pct=(0.04, 0.12),
    chatlist_default_pct=0.30,
    chatright_default_pct=0.0, # 微信默认可能更简单，或者根据需要调整
    title_default_pct=0.06,
    input_bar_min_pct=0.08,
)

QQ_CONFIG = PlatformConfig(
    name="qq",
    display_name="QQ",
    window_title="QQ",
    window_class="TXGuiFoundation",  # QQ 常见类名
    sidebar_scan_pct=0.08,
    chatlist_scan_pct=(0.15, 0.60),
    title_scan_pct=(0.04, 0.15),
    chatlist_default_pct=0.35,
    chatright_default_pct=0.20,
    title_default_pct=0.07,
    input_bar_min_pct=0.10,
)

ALL_PLATFORMS = [WECHAT_CONFIG, QQ_CONFIG]


def auto_detect_platform():
    """
    自动检测当前运行的IM平台。
    优先查找微信，其次QQ。返回第一个找到窗口的配置。
    """
    import win32gui

    for config in ALL_PLATFORMS:
        hwnd = win32gui.FindWindow(config.window_class, config.window_title)
        if not hwnd:
            # 回退：仅按标题搜索
            hwnd = win32gui.FindWindow(None, config.window_title)
        if hwnd:
            logger.info(f"自动检测到平台: {config.display_name}")
            return config

    # 都没找到，默认返回微信配置
    logger.warning("未检测到已知IM窗口，默认使用微信配置")
    return WECHAT_CONFIG


def get_platform_by_name(name: str) -> PlatformConfig:
    """按名称获取平台配置"""
    for config in ALL_PLATFORMS:
        if config.name == name:
            return config
    raise ValueError(f"未知平台: {name}，可选: {[c.name for c in ALL_PLATFORMS]}")
