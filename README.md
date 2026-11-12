# 译心 · LocalTranslate

> 本地中英翻译助手：Streamlit 界面 + llama.cpp 引擎 + 腾讯混元 Hy-MT2-7B（GGUF Q4_K_M）。
> **完全离线，数据不出机，无需安装、无需联网、不需要 JDK 或任何编译环境。**
> **CPU / GPU 自适应**：有 NVIDIA 显卡自动走 CUDA 加速，没有则回退 CPU。

> ⚠️ 引擎与模型合计约 4.7 GB，已通过 `.gitignore` 排除；上传 GitHub 时勿提交 `llama/`、`llama-cuda/`、`models/*.gguf`、`downloads/`。

## 特性

- 中 ⇄ 英双向翻译，支持自动检测语言方向
- 三种语气：正式商务 / 自然口语 / 忠实直译
- 流式输出（边译边显示），状态栏实时显示 tok/s
- **引擎按需加载，翻译结束/空闲后自动释放内存（默认 30 秒）**
- **CPU / GPU 自适应**：检测到 NVIDIA 自动用 CUDA 版（`-ngl 99` 全量上显存）
- 暗色 / 亮色主题，设置自动记忆
- 一键复制译文、导出 `.txt`
- 双击图标启动，绿色文件夹，拷走即用

## 环境要求

- **Python 3.12**（启动脚本优先使用 `py -3.12`，不可用时回退到 `python`）
- 依赖：`streamlit`、`requests`（`psutil` 可选，用于更好释放引擎）
- 可选：**NVIDIA GPU**（如 RTX 3060 12G），有则 `deploy.py` 自动下载 CUDA 版并加速

## GPU 加速（自适应）

- `deploy.py` 默认 `--backend auto`：检测到 NVIDIA 就下载 CUDA 版到 `llama-cuda/`，否则下载 CPU 版到 `llama/`。
- 启动时引擎自动选择：有 GPU 且 CUDA 版存在 → 用 `llama-cuda/llama-server.exe` 并加 `-ngl 99`；否则用 CPU 版。
- 想强制指定：环境变量 `LT_BACKEND=cpu|cuda`，或 `deploy.py --backend cpu|cuda`。
- 显存足够时（如 RTX 3060 12G），7B Q4 预计约 **45–60 tok/s**，约为 CPU 的 15–20 倍。

## 资源占用与自动释放

引擎平时**不常驻后台**，避免占用笔记本内存影响其他程序：

- 首次点「立即翻译」时才加载模型（约 6 秒），期间界面显示“正在启动引擎”。
- 侧边栏「翻译后释放引擎」可选：**立即 / 30 秒 / 1 分钟 / 3 分钟 / 不释放**。
  - 选「立即」：每次翻译结束立刻关闭引擎；
  - 选「30 秒」等：最后一次翻译后等待相应空闲时间再关闭。
- 关闭启动器窗口时也会回收引擎进程。
- 侧边栏还有「立即释放引擎内存」按钮，可手动释放。
- 若系统里已有遗留的 `llama-server` 占用内存，应用会在下次翻译时接管并按策略释放。

## 快速开始（自动部署，推荐）

```bash
# 1. 安装依赖
py -3.12 -m pip install -r requirements.txt

# 2. 一键下载引擎与模型（约 4.7 GB；有 NVIDIA 会自动下 CUDA 版）
py -3.12 deploy.py
# 或直接双击 一键部署.bat
```

`deploy.py` 会自动：

1. 根据是否有 NVIDIA GPU，下载 **Windows CPU 版**（`llama/`）或 **CUDA 版**（`llama-cuda/`，含 cudart 运行时）；
2. 默认从 **ModelScope（魔搭，国内速度快）** 下载 `Hy-MT2-7B-Q4_K_M.gguf` 到 `models/`，**支持断点续传**，并校验 GGUF 文件头与 SHA-256。

完成后双击 `启动翻译助手.bat`（或桌面快捷方式）即可。

> 启动器只打开界面（8501）；翻译引擎在第一次点「立即翻译」时按需加载。
> 切换下载源：
> - Hugging Face：`py -3.12 deploy.py --source hf`
> - 自动回退：`py -3.12 deploy.py --source auto`
> - 手动指定：`py -3.12 deploy.py --model-url <gguf>`；跳过哈希：`--skip-hash`
> - 强制后端：`py -3.12 deploy.py --backend cuda`（或 `cpu`）

## 手动部署（备选）

自备以下文件：

- 引擎：`llama/llama-server.exe`（CPU，连同 DLL）或 `llama-cuda/llama-server.exe`（CUDA，连同 DLL）
- 模型：`models/Hy-MT2-7B-Q4_K_M.gguf`（约 4.6 GB）

下载地址：

- 引擎：https://github.com/ggml-org/llama.cpp/releases （`bin-win-cpu-x64.zip` 或 `bin-win-cuda-12.4-x64.zip` + `cudart-llama-bin-win-cuda-12.4-x64.zip`）
- 模型：https://www.modelscope.cn/models/Tencent-Hunyuan/Hy-MT2-7B-GGUF
  或 https://huggingface.co/tencent/Hy-MT2-7B-GGUF

## 目录结构

```
LocalTranslate/
├── 一键部署.bat            # 双击下载引擎与模型
├── 启动翻译助手.bat        # 双击启动（推荐）
├── 创建桌面快捷方式.ps1     # 生成带图标的桌面快捷方式
├── 翻译助手.ico            # 应用图标
├── deploy.py              # 自动下载引擎与模型（CPU/GPU 自适应）
├── app.py                 # Streamlit 主界面
├── launcher.py            # 启动器：启动界面并回收引擎
├── make_icon.py           # 图标生成脚本
├── .streamlit/config.toml # 主题配置
├── assets/
│   ├── gpu.py             # NVIDIA 探测 / 后端选择
│   ├── engine.py          # 引擎按需启停 / 空闲释放
│   ├── llm_client.py      # 流式客户端
│   ├── translator.py      # 提示词
│   ├── settings.py        # 设置持久化
│   └── styles.css         # 样式
├── scripts/               # 离线验证脚本
├── llama/                 # CPU 引擎（部署脚本解压到此）
├── llama-cuda/            # CUDA 引擎（有 GPU 时）
├── models/                # 模型
├── downloads/             # 下载缓存（可删）
├── logs/                  # 引擎日志
└── data/                  # 设置持久化
```

## 配置项（环境变量，可选）

| 变量 | 默认 | 说明 |
|---|---|---|
| `LT_BACKEND` | `auto` | `auto` / `cpu` / `cuda`，强制后端 |
| `LT_MODEL` | `Hy-MT2-7B-Q4_K_M.gguf` | 模型文件名（放在 models/） |
| `LT_PORT` | `8080` | 引擎端口 |
| `LT_ST_PORT` | `8501` | 界面端口 |
| `LT_THREADS` | 核数-6（最低 4） | CPU 推理线程数 |
| `LT_LLAMA_URL` | `http://127.0.0.1:8080` | 界面调用的引擎地址 |
| `HF_ENDPOINT` | `https://huggingface.co` | HF 下载镜像（`--source hf` 时生效） |

> 「翻译后释放引擎」在界面侧边栏选择，保存在 `data/settings.json`。

## 内网离线部署

若目标机无法联网，先在联网机器上执行 `py -3.12 deploy.py`，然后把 `llama/`（或 `llama-cuda/`）与 `models/` 目录整体拷贝到目标机。

pip 依赖同理可离线打包：

```bash
py -3.12 -m pip download -r requirements.txt -d wheelhouse
# 目标机：
py -3.12 -m pip install --no-index --find-links wheelhouse -r requirements.txt
```

## 验证

```bash
py -3.12 scripts\smoke_test.py      # 流式客户端 + 提示词（mock 引擎）
py -3.12 scripts\apptest_check.py   # Streamlit 界面端到端（mock 引擎）
```

## 常见问题

- **首次翻译要等几秒**：正常，引擎按需加载模型约 6 秒；之后翻译结束会按设置自动释放。
- **有 GPU 但仍是 CPU 速度**：确认 `llama-cuda/llama-server.exe` 存在（运行 `deploy.py --backend cuda`），且 `LT_BACKEND` 未强制为 `cpu`。
- **想让它一直常驻**：侧边栏「翻译后释放引擎」选「不释放」。
- **界面显示引擎未连接**：确认引擎与模型就位；查看 `logs/llama-server.log`。
- **deploy.py 下载慢/失败**：默认走 ModelScope；可 `--source hf` 切 HuggingFace，或设 `HF_ENDPOINT=https://hf-mirror.com`。
- **CPU 速度慢**：电源切高性能、插电散热；或考虑 1.8B 模型。

## 许可与说明

仅供内部使用；底层模型为 Tencent Hy-MT2（Apache-2.0），引擎为 llama.cpp（MIT）。
