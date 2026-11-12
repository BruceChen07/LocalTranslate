"""启动器：只负责启动界面；翻译引擎由应用按需启停、空闲自动释放。

自适应：检测到 NVIDIA GPU 且已部署 CUDA 版时走 GPU，否则回退 CPU。
双击 `启动翻译助手.bat` 时由它调用。关闭命令行窗口会回收引擎进程。
环境变量可覆盖默认值：
    LT_BACKEND   auto|cpu|cuda（默认 auto）
    LT_MODEL     Hy-MT2-7B-Q4_K_M.gguf
    LT_PORT      8080
    LT_ST_PORT   8501
    LT_THREADS   推理线程数
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def log(message: str) -> None:
    print(message, flush=True)


def check_requirements() -> tuple[list[str], str]:
    from assets.gpu import select_engine

    problems: list[str] = []
    exe, backend, gpu = select_engine()
    if exe is None:
        problems.append(
            "缺少 llama-server.exe（应位于 llama/ 或 llama-cuda/，请先运行 deploy.py）"
        )
    model = ROOT / "models" / os.environ.get("LT_MODEL", "Hy-MT2-7B-Q4_K_M.gguf")
    if not model.exists():
        problems.append(f"缺少模型文件（应位于 {model}）")
    label = backend.upper() + (f"（{gpu}）" if gpu else "")
    return problems, label


def kill_engine() -> None:
    pid_file = ROOT / ".engine.pid"
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        pid = None
    if pid:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True
            )
        except Exception:  # noqa: BLE001
            pass
    try:
        pid_file.unlink()
    except FileNotFoundError:
        pass


def main() -> int:
    LOG_DIR.mkdir(exist_ok=True)

    problems, backend_label = check_requirements()
    if problems:
        log("=" * 62)
        log("启动失败：缺少必要文件")
        for item in problems:
            log("  - " + item)
        log("=" * 62)
        log("请先运行 deploy.py（或 一键部署.bat）下载引擎与模型，再重试。")
        return 1

    st_port = int(os.environ.get("LT_ST_PORT", "8501"))
    env = os.environ.copy()
    env.setdefault("LT_LLAMA_URL", f"http://127.0.0.1:{os.environ.get('LT_PORT', '8080')}")

    log(f"[后端] {backend_label} · 启动界面 …（按需加载，空闲/完成后自动释放）")
    try:
        st_proc = subprocess.Popen(
            [
                sys.executable,
                "-m", "streamlit", "run", str(ROOT / "app.py"),
                "--server.port", str(st_port),
                "--server.headless", "false",
            ],
            cwd=str(ROOT),
            env=env,
        )
        st_proc.wait()
    finally:
        kill_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
