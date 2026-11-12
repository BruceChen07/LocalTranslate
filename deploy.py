#!/usr/bin/env python3
"""译心 · LocalTranslate 部署脚本。

自动下载：
  1. llama.cpp Windows CPU 版（llama-server.exe + 依赖 DLL），解压到 ./llama/
  2. Hy-MT2-7B-Q4_K_M.gguf（约 4.6 GB），放到 ./models/
     默认从 ModelScope（魔搭，国内速度快）下载，可用 --source hf 切换 Hugging Face。

只依赖标准库，可在装依赖之前直接运行：
    py -3.12 deploy.py

可选参数：
    --source {modelscope,hf,auto}  模型下载源（默认 modelscope）
    --force          已存在也重新下载
    --insecure       跳过 TLS 校验（企业代理 MITM 时用）
    --llama-url URL  手动指定 llama.cpp zip 地址
    --model-url URL  手动指定 gguf 地址
    --skip-engine    跳过引擎下载
    --skip-model     跳过模型下载
    --skip-hash      跳过模型 SHA-256 校验
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LLAMA_DIR = ROOT / "llama"
MODEL_DIR = ROOT / "models"
DOWNLOADS = ROOT / "downloads"
MODEL_NAME = "Hy-MT2-7B-Q4_K_M.gguf"
GH_API = "https://api.github.com/repos/ggml-org/llama.cpp"
LOCK_FILE = ROOT / ".deploy.lock"

# 模型仓库
MODELSCOPE_REPO = "Tencent-Hunyuan/Hy-MT2-7B-GGUF"
MODELSCOPE_REVISION = "master"
HF_REPO = "tencent/Hy-MT2-7B-GGUF"
EXPECTED_SIZE = 4624648896
EXPECTED_SHA256 = "9f96256500f3fc1ab4d64336b58f52a949a95ad7516b0c229476eef782f9f77b"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) LocalTranslate-deploy/1.0"
)


def log(message: str = "") -> None:
    print(message, flush=True)


def human(num: int | None) -> str:
    if num is None:
        return "?"
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{value:.1f}TB"


# --------------------------------------------------------------------------- 单实例锁
def acquire_lock() -> None:
    if LOCK_FILE.exists():
        age = time.time() - LOCK_FILE.stat().st_mtime
        if age < 6 * 3600:
            raise RuntimeError(
                f"检测到另一个部署进程正在运行（{LOCK_FILE}）。"
                "如确认没有，请删除该文件后重试。"
            )
        LOCK_FILE.unlink()
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")


def release_lock() -> None:
    try:
        LOCK_FILE.unlink()
    except FileNotFoundError:
        pass


# --------------------------------------------------------------------------- HTTP
def ssl_context(insecure: bool) -> ssl.SSLContext:
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()


def api_json(url: str, *, insecure: bool = False) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60, context=ssl_context(insecure)) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise RuntimeError(
                "GitHub API 被限流或不可达（403）。可改用 --llama-url 手动指定 zip 地址。"
            ) from exc
        raise


def http_get_text(url: str, *, insecure: bool = False) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60, context=ssl_context(insecure)) as resp:
        return resp.read(4096).decode("utf-8", "replace")


def download_file(
    url: str,
    dest: Path,
    *,
    insecure: bool = False,
    force: bool = False,
    label: str | None = None,
    expected_size: int | None = None,
) -> Path:
    dest = Path(dest)
    label = label or dest.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")

    if dest.exists() and dest.stat().st_size > 0 and not force:
        log(f"[跳过] {label} 已存在（{human(dest.stat().st_size)}）")
        return dest
    if force and dest.exists():
        dest.unlink()

    # 损坏的超大断点文件直接丢弃
    if part.exists() and expected_size and part.stat().st_size > expected_size:
        log("[警告] 断点文件大于预期大小，已删除并重新下载")
        part.unlink()

    start = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": USER_AGENT}
    if start > 0:
        headers["Range"] = f"bytes={start}-"

    req = urllib.request.Request(url, headers=headers)
    log(f"[下载] {label}{'（断点续传）' if start else ''}")
    try:
        resp = urllib.request.urlopen(req, timeout=120, context=ssl_context(insecure))
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and start > 0:
            part.replace(dest)
            log(f"[完成] {label}（{human(dest.stat().st_size)}）")
            return dest
        raise

    with resp:
        status = getattr(resp, "status", resp.getcode())
        total = expected_size
        content_range = resp.headers.get("Content-Range")
        if content_range and "/" in content_range:
            total = int(content_range.rsplit("/", 1)[-1])
        elif status == 200:
            length = resp.headers.get("Content-Length")
            if length:
                total = int(length)

        if status == 200 and start > 0:
            start = 0
            if part.exists():
                part.unlink()
        mode = "ab" if start > 0 else "wb"
        written = start
        last_t = time.time()
        last_b = written
        with open(part, mode) as fh:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                if total is not None and written + len(chunk) > total:
                    chunk = chunk[: total - written]
                fh.write(chunk)
                written += len(chunk)
                now = time.time()
                if now - last_t >= 0.5:
                    speed = (written - last_b) / (now - last_t) / (1024 * 1024)
                    pct = f"{written / total * 100:5.1f}%" if total else "  ?  "
                    print(
                        f"\r    {label}: {human(written)} / {human(total)} ({pct}) {speed:4.1f} MB/s",
                        end="",
                        flush=True,
                    )
                    last_t, last_b = now, written
                if total is not None and written >= total:
                    break
        print()

    size = part.stat().st_size
    if total is not None and size != total:
        # 兜底：写入超量则截断
        if size > total:
            with open(part, "r+b") as fh:
                fh.truncate(total)
            log(f"[修正] {label} 截断到 {human(total)}")
            size = total
        else:
            raise RuntimeError(f"{label} 下载不完整：{human(size)} / {human(total)}，请重试续传。")
    part.replace(dest)
    log(f"[完成] {label}（{human(size)}）")
    return dest


# --------------------------------------------------------------------------- llama.cpp
def _is_win_cpu_asset(name: str) -> bool:
    n = name.lower()
    if not n.endswith(".zip") or "bin-win" not in n:
        return False
    if any(x in n for x in ("cudart", "cuda", "vulkan", "rocm", "sycl", "opencl", "openvino", "arm64")):
        return False
    return "x64" in n


def pick_win_cpu_asset(assets: list[dict]) -> dict | None:
    for asset in assets:
        if asset.get("name", "").lower().endswith("bin-win-cpu-x64.zip"):
            return asset
    for asset in assets:
        if _is_win_cpu_asset(asset.get("name", "")):
            return asset
    return None


def resolve_llama_url(*, insecure: bool = False) -> tuple[str, str]:
    latest = api_json(f"{GH_API}/releases/latest", insecure=insecure)
    asset = pick_win_cpu_asset(latest.get("assets", []))
    if asset:
        return asset["browser_download_url"], latest.get("tag_name", "latest")

    tag_asset = next(
        (a for a in latest.get("assets", []) if a.get("name") == "nightly-tag.txt"), None
    )
    if tag_asset:
        text = http_get_text(tag_asset["browser_download_url"], insecure=insecure)
        match = re.search(r"b\d+", text)
        if match:
            tag = match.group(0)
            release = api_json(f"{GH_API}/releases/tags/{tag}", insecure=insecure)
            asset = pick_win_cpu_asset(release.get("assets", []))
            if asset:
                return asset["browser_download_url"], tag

    raise RuntimeError("无法解析 Windows CPU 版本地址，请用 --llama-url 手动指定 zip 下载地址。")


def find_server_exe(*dirs: Path) -> Path | None:
    for base in dirs:
        if not base.exists():
            continue
        direct = base / "llama-server.exe"
        if direct.exists():
            return direct
        for found in base.rglob("llama-server.exe"):
            return found
    return None


def extract_zip(zip_path: Path, target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(target)
    children = list(target.iterdir())
    if len(children) == 1 and children[0].is_dir():
        nested = children[0]
        for item in nested.iterdir():
            shutil.move(str(item), str(target / item.name))
        nested.rmdir()
    exe = find_server_exe(target)
    if not exe:
        raise RuntimeError(f"解压后未找到 llama-server.exe（{target}）")
    return exe


# --------------------------------------------------------------------------- 模型
def build_model_urls(name: str, hf_endpoint: str) -> dict[str, str]:
    hf_endpoint = hf_endpoint.rstrip("/")
    return {
        "modelscope": (
            f"https://www.modelscope.cn/models/{MODELSCOPE_REPO}/"
            f"resolve/{MODELSCOPE_REVISION}/{name}"
        ),
        "hf": f"{hf_endpoint}/{HF_REPO}/resolve/main/{name}",
    }


def verify_gguf(path: Path) -> None:
    with open(path, "rb") as fh:
        magic = fh.read(4)
    if magic != b"GGUF":
        raise RuntimeError(f"模型文件校验失败：{path} 不是有效的 GGUF 文件。")


def verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual.lower() != expected.lower():
        raise RuntimeError(
            "模型 SHA-256 校验失败：\n"
            f"  期望 {expected}\n"
            f"  实际 {actual}\n"
            "文件可能损坏或上游已更新；可加 --skip-hash 跳过，或用 --model-url 指定地址。"
        )
    log("[校验] SHA-256 一致")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="下载 llama-server 与 Hy-MT2-7B 模型")
    parser.add_argument(
        "--source", choices=["modelscope", "hf", "auto"], default="modelscope",
        help="模型下载源（默认 modelscope；auto 先 ModelScope 再 HF）",
    )
    parser.add_argument("--force", action="store_true", help="已存在也重新下载")
    parser.add_argument("--insecure", action="store_true", help="跳过 TLS 校验")
    parser.add_argument("--llama-url", default=None, help="手动指定 llama.cpp zip 地址")
    parser.add_argument("--model-url", default=None, help="手动指定 gguf 地址")
    parser.add_argument("--skip-engine", action="store_true", help="跳过引擎下载")
    parser.add_argument("--skip-model", action="store_true", help="跳过模型下载")
    parser.add_argument("--skip-hash", action="store_true", help="跳过模型 SHA-256 校验")
    args = parser.parse_args(argv)

    if os.name != "nt":
        log("[提示] 本脚本下载的是 Windows 版 llama-server，当前系统可能无法直接运行。")

    acquire_lock()
    exit_code = 0
    try:
        if not args.skip_engine:
            existing = find_server_exe(LLAMA_DIR, ROOT)
            if existing and not args.force:
                log(f"[跳过] 引擎已存在：{existing}")
            else:
                if args.llama_url:
                    url, tag = args.llama_url, "自定义地址"
                else:
                    url, tag = resolve_llama_url(insecure=args.insecure)
                    log(f"[解析] llama.cpp {tag} · Windows CPU 版")
                zip_path = DOWNLOADS / "llama-server-win-cpu.zip"
                download_file(
                    url, zip_path, insecure=args.insecure, force=args.force,
                    label="llama.cpp 引擎包",
                )
                exe = extract_zip(zip_path, LLAMA_DIR)
                log(f"[完成] 引擎：{exe}")

        if not args.skip_model:
            dest = MODEL_DIR / MODEL_NAME
            if dest.exists() and dest.stat().st_size > 3_000_000_000 and not args.force:
                log(f"[跳过] 模型已存在：{dest}（{human(dest.stat().st_size)}）")
            else:
                hf_endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co")
                urls = build_model_urls(MODEL_NAME, hf_endpoint)
                if args.model_url:
                    candidates = [("custom", args.model_url)]
                elif args.source == "auto":
                    candidates = [("modelscope", urls["modelscope"]), ("hf", urls["hf"])]
                else:
                    candidates = [(args.source, urls[args.source])]

                last_error: Exception | None = None
                for source_name, url in candidates:
                    log(f"[模型] 下载源：{source_name}")
                    try:
                        download_file(
                            url, dest, insecure=args.insecure, force=args.force,
                            label=MODEL_NAME,
                            expected_size=None if args.model_url else EXPECTED_SIZE,
                        )
                        last_error = None
                        break
                    except (RuntimeError, urllib.error.URLError, OSError) as exc:
                        last_error = exc
                        log(f"[警告] 源 {source_name} 失败：{exc}")
                if last_error:
                    raise last_error

                verify_gguf(dest)
                if not args.skip_hash and not args.model_url:
                    verify_sha256(dest, EXPECTED_SHA256)

        log()
        log("=" * 60)
        log("部署完成。下一步：")
        log("  1) py -3.12 -m pip install -r requirements.txt")
        log("  2) 双击 启动翻译助手.bat（或桌面快捷方式）")
        log("=" * 60)
    except (RuntimeError, urllib.error.URLError, OSError) as exc:
        log()
        log(f"[错误] {exc}")
        log("提示：默认走 ModelScope；如仍失败可试 `--source hf` 或设")
        log("      `set HF_ENDPOINT=https://hf-mirror.com`；也可用 --model-url 指定地址。")
        exit_code = 1
    finally:
        release_lock()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
