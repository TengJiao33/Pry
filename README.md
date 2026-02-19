# Pry

Pry 是一个 Windows 桌面聊天辅助工具：通过截图 + OCR 读取微信/QQ 聊天窗口，调用大模型分析后弹窗提示（建议、预警、吐槽等）。

## 当前状态

`WIP / 实验性项目`。  
已能跑通主流程，但窗口识别、OCR鲁棒性、端到端延迟仍有明显问题，不建议直接用于生产环境。

## 功能概览

- 自动检测微信 / QQ 窗口
- 截图并识别聊天区、标题栏、输入区
- 调用 LLM 输出结构化动作（`suggest` / `roast` / `think` / `vibe` / `warn` / `none`）
- 托盘 + 桌面弹窗提醒
- 本地 JSON 记忆（联系人与用户画像）
- 提供 OCR 调试脚本与可视化工具

## 目录结构

```text
.
├─ src/                  # 核心代码
│  ├─ window_monitor.py  # 主循环
│  ├─ ocr_reader.py      # 截图/布局识别/OCR
│  ├─ llm_client.py      # 模型调用
│  ├─ memory_store.py    # 本地记忆
│  └─ popup_window.py    # 弹窗与托盘
├─ tools/                # OCR 诊断、复现与可视化脚本
├─ tests/                # 单元测试（保留）
├─ data/test_samples/    # OCR测试样本（保留）
├─ requirements.txt
└─ run_pry.bat
```

## 环境要求

- Windows 10/11
- Python 3.10+
- 已安装微信或QQ桌面版

## 快速开始

1. 安装依赖

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. 配置环境变量（复制模板）

```powershell
copy .env.example .env
```

按需填写以下变量：

- `DOUBAO_API_KEY`
- `DOUBAO_ENDPOINT_ID`
- 或 `DEEPSEEK_API_KEY`

3. 运行

```powershell
python src\window_monitor.py --debug
```

或双击：

```text
run_pry.bat
```

## 调试命令

- OCR 可视化诊断：

```powershell
python tools\debug_ocr.py --platform qq
```

- 离线样本复现：

```powershell
python tools\reproduce_issue.py
```

- 运行测试：

```powershell
pytest -q
```

## 已知问题

- 不同 UI 缩放、主题、窗口布局下，分区识别仍可能漂移
- 群聊右侧成员面板识别存在误判/漏判
- OCR 对图片消息、表情、链接混排场景稳定性不足
- 轮询 + OCR + LLM 链路存在延迟峰值

## 安全与隐私

- 请勿提交 `.env` 到仓库
- `data/memory.json` 为本地运行数据，默认不入库
- 如果密钥曾泄露，请立即在平台侧轮换

## 许可证

暂未声明（默认保留所有权利）。如需开源发布，请补充 `LICENSE` 文件。

