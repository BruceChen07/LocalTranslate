"""端到端校验：用 Streamlit AppTest + 本地 mock 引擎，跑通「输入→翻译→出结果」全流程。"""
from __future__ import annotations

import os
import socket
import sys
import threading
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from smoke_test import CHUNKS, MockHandler  # noqa: E402


def free_port(preferred: int) -> int:
    for port in (preferred, preferred + 1, preferred + 2):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("找不到可用端口")


def main() -> int:
    from streamlit.testing.v1 import AppTest

    port = free_port(8080)
    os.environ["LT_LLAMA_URL"] = f"http://127.0.0.1:{port}"
    server = HTTPServer(("127.0.0.1", port), MockHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        at.run()
        assert not at.exception, f"首次渲染异常: {[str(e.value) for e in at.exception]}"

        at.text_area[0].set_value("你好世界")
        translate_btn = next(
            (b for b in at.button if b.label == "立即翻译"), None
        )
        assert translate_btn is not None, [b.label for b in at.button]
        translate_btn.click()
        at.run()
        assert not at.exception, f"翻译时异常: {[str(e.value) for e in at.exception]}"

        result = at.session_state["result"]
        expected = "".join(CHUNKS)
        assert result == expected, f"译文不匹配: {result!r} != {expected!r}"

        print("[PASS] AppTest 端到端通过。")
        print("       译文：", result)
        return 0
    finally:
        server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
