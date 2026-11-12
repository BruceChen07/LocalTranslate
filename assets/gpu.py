"""NVIDIA GPU 探测与引擎后端选择（CPU / CUDA 自适应）。"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CPU_DIR = ROOT / "llama"
CUDA_DIR = ROOT / "llama-cuda"


def _which_nvidia_smi() -> str | None:
    exe = shutil.which("nvidia-smi")
    if exe:
        return exe
    for candidate in (
        r"C:\Windows\System32\nvidia-smi.exe",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
    ):
        if Path(candidate).exists():
            return candidate
    return None


def detect_gpu() -> str | None:
    """检测 NVIDIA GPU，返回名称；没有则返回 None。"""
    exe = _which_nvidia_smi()
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=8,
        ).stdout.strip()
        if not out:
            return None
        first = out.splitlines()[0]
        name = first.split(",")[0].strip()
        return name or "NVIDIA GPU"
    except Exception:  # noqa: BLE001
        return None


def cpu_exe() -> Path | None:
    for candidate in (CPU_DIR / "llama-server.exe", ROOT / "llama-server.exe"):
        if candidate.exists():
            return candidate
    return None


def cuda_exe() -> Path | None:
    candidate = CUDA_DIR / "llama-server.exe"
    return candidate if candidate.exists() else None


def select_engine() -> tuple[Path | None, str, str | None]:
    """返回 (可执行文件, 'cuda'|'cpu', GPU 名称)。

    优先级：LT_BACKEND 环境变量 > 有 NVIDIA 且已下载 CUDA 版 > CPU。
    """
    forced = os.environ.get("LT_BACKEND", "auto").lower()
    gpu = detect_gpu()
    c_cuda = cuda_exe()
    c_cpu = cpu_exe()

    if forced == "cuda":
        return (c_cuda or c_cpu), ("cuda" if c_cuda else "cpu"), gpu
    if forced == "cpu":
        return (c_cpu or c_cuda), ("cpu" if c_cpu else "cuda"), gpu
    if gpu and c_cuda:
        return c_cuda, "cuda", gpu
    if c_cpu:
        return c_cpu, "cpu", gpu
    return c_cuda, ("cuda" if c_cuda else "cpu"), gpu
