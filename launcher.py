"""启动器：只负责启动界面；翻译引擎由应用按需启停、空闲自动释放。

双击 `启动翻译助手.bat` 时由它调用。关闭命令行窗口即退出，
并确保残留的 llama-server 子进程一并被回收，避免继续占用内存。
环境变量可覆盖默认值：
    LT_MODEL     模型文件名（默认 Hy-MT2-7B-Q4_K_M.gguf）
    LT_PORT      引擎端口（默认 8080）
    LT_ST_PORT   界面端口（默认 8501）
    LT_THREADS   推理线程数（默认 CPU 核数-6，最低 4）
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


def find_llama_server() -> Path | None:
    """兼容根目录与 llama/ 子目录（部署脚本解压到 llama/）。"""
    for candidate in (ROOT / "llama-server.exe", ROOT / "llama" / "llama-server.exe"):
        if candidate.exists():
            return candidate
    for found in ROOT.rglob("llama-server.exe"):
        if "downloads" not in found.parts:
            return found
    return None


def check_requirements() -> list[str]:
    problems: list[str] = []
    if find_llama_server() is None:
        problems.append(
            "缺少 llama-server.exe（应位于 "
            f"{ROOT / 'llama-server.exe'} 或 {ROOT / 'llama' / 'llama-server.exe'}）"
        )
    model = ROOT / "models" / os.environ.get("LT_MODEL", "Hy-MT2-7B-Q4_K_M.gguf")
    if not model.exists():
        problems.append(f"缺少模型文件（应位于 {model}）")
    return problems


def kill_engine() -> None:
    """关闭界面时回收应用按需拉起的引擎进程。"""
    pid_file = ROOT / ".engine.pid"
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        pid = None
    if pid:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
            )
        except Exception:  # noqa: BLE001
            pass
    try:
        pid_file.unlink()
    except FileNotFoundError:
        pass


def main() -> int:
    LOG_DIR.mkdir(exist_ok=True)

    problems = check_requirements()
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

    log("启动界面 …（翻译时按需加载引擎，空闲/完成后自动释放内存）")
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
