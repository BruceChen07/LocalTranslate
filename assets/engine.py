"""按需启停 llama-server：翻译时懒加载，空闲/完成后立即释放 CPU 与内存。

后端自适应该：
- 检测到 NVIDIA GPU 且已下载 CUDA 版时，使用 `llama-cuda/llama-server.exe` 并 `-ngl 99` 全量上显存；
- 否则回退到 CPU 版 `llama/llama-server.exe`。

- `ensure_running()`：首次翻译时启动引擎（约 6 秒加载模型）。
- `touch()`：每次活动刷新“最后使用时间”。
- 空闲超过 `idle_timeout` 秒后自动 `stop()`，释放内存/显存。
- 应用退出时（atexit）也会回收引擎进程。
"""
from __future__ import annotations

import atexit
import os
import subprocess
import threading
import time
from pathlib import Path

from .gpu import select_engine

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
PID_FILE = ROOT / ".engine.pid"
DEFAULT_URL = os.environ.get("LT_LLAMA_URL", "http://127.0.0.1:8080")


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except Exception:  # noqa: BLE001
        return False


def _pid_is_llama(pid: int) -> bool:
    try:
        import psutil
        return "llama-server" in psutil.Process(pid).name().lower()
    except Exception:  # noqa: BLE001
        return False


def _find_pid_on_port(port: int) -> int | None:
    try:
        import psutil
        for conn in psutil.net_connections(kind="inet"):
            if (
                conn.laddr
                and conn.laddr.port == port
                and conn.status == psutil.CONN_LISTEN
                and conn.pid
            ):
                return conn.pid
    except Exception:  # noqa: BLE001
        pass
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=10
        ).stdout
        for line in out.splitlines():
            if f":{port}" in line and "LISTEN" in line.upper():
                parts = line.split()
                if parts and parts[-1].isdigit():
                    return int(parts[-1])
    except Exception:  # noqa: BLE001
        pass
    return None


class EngineManager:
    def __init__(self) -> None:
        self._exe, self.backend, self.gpu_name = select_engine()
        self.url = DEFAULT_URL.rstrip("/")
        self.port = int(os.environ.get("LT_PORT", "8080"))
        self.model = ROOT / "models" / os.environ.get("LT_MODEL", "Hy-MT2-7B-Q4_K_M.gguf")
        self.threads = int(os.environ.get("LT_THREADS", "0")) or max(4, (os.cpu_count() or 8) - 6)
        self.idle_timeout = float(os.environ.get("LT_IDLE_TIMEOUT", "30"))
        self._proc: subprocess.Popen | None = None
        self._external_pid: int | None = None
        self._log = None
        self._last = 0.0
        self._lock = threading.Lock()
        self._monitor_started = False
        atexit.register(self.stop)

    # ------------------------------------------------------------------ 状态
    def backend_label(self) -> str:
        if self.backend == "cuda":
            return f"GPU · {self.gpu_name}" if self.gpu_name else "GPU"
        return "CPU"

    def is_alive(self) -> bool:
        if self._proc is not None and self._proc.poll() is None:
            return True
        return _pid_alive(self._external_pid)

    def health(self) -> bool:
        try:
            import requests
            return requests.get(f"{self.url}/health", timeout=1.5).status_code == 200
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------ 启动
    def ensure_running(self, wait: float = 120.0) -> bool:
        self._start_monitor()
        if self.health():
            self._last = time.time()
            if not self.is_alive():
                pid = _find_pid_on_port(self.port)
                if pid and _pid_is_llama(pid):
                    self._external_pid = pid
            return True
        with self._lock:
            if self._external_pid and not _pid_alive(self._external_pid):
                self._external_pid = None
            if not self.is_alive():
                self._start()
        return self._wait_health(wait)

    def _start(self) -> None:
        if self._exe is None or not self.model.exists():
            raise RuntimeError("缺少 llama-server.exe 或模型文件")
        LOG_DIR.mkdir(exist_ok=True)
        self._log = open(LOG_DIR / "llama-server.log", "a", encoding="utf-8")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        args = [
            str(self._exe), "-m", str(self.model),
            "--host", "127.0.0.1", "--port", str(self.port),
            "-c", "8192", "-t", str(self.threads),
        ]
        if self.backend == "cuda":
            args += ["-ngl", "99"]
        self._proc = subprocess.Popen(
            args, stdout=self._log, stderr=subprocess.STDOUT, creationflags=flags,
        )
        try:
            PID_FILE.write_text(str(self._proc.pid), encoding="utf-8")
        except OSError:
            pass
        self._last = time.time()

    def _wait_health(self, timeout: float) -> bool:
        started = time.time()
        while time.time() - started < timeout:
            if self.health():
                self._last = time.time()
                return True
            proc = self._proc
            if proc is not None and proc.poll() is not None:
                return False
            time.sleep(0.5)
        return False

    # ------------------------------------------------------------------ 释放
    def touch(self) -> None:
        self._last = time.time()

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
            ext = self._external_pid
            self._proc = None
            self._external_pid = None
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=8)
                except Exception:  # noqa: BLE001
                    try:
                        proc.kill()
                    except Exception:  # noqa: BLE001
                        pass
            if ext and _pid_alive(ext):
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(ext), "/T", "/F"],
                        capture_output=True,
                    )
                except Exception:  # noqa: BLE001
                    pass
            if self._log is not None:
                try:
                    self._log.close()
                except Exception:  # noqa: BLE001
                    pass
                self._log = None
            try:
                PID_FILE.unlink()
            except FileNotFoundError:
                pass

    # ------------------------------------------------------------------ 空闲监控
    def _start_monitor(self) -> None:
        if self._monitor_started:
            return
        self._monitor_started = True
        threading.Thread(target=self._monitor, daemon=True).start()

    def _monitor(self) -> None:
        while True:
            time.sleep(5)
            try:
                if self.idle_timeout > 0 and self.is_alive() and self.health():
                    if time.time() - self._last > self.idle_timeout:
                        self.stop()
            except Exception:  # noqa: BLE001
                pass


engine = EngineManager()
