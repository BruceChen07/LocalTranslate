"""离线冒烟测试：用本地 mock 服务验证流式客户端与提示词构造，无需真实模型。"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

CHUNKS = ["根据", "本季度", "的销售数据", "，营收同比增长。", " 谢谢。"]


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for piece in CHUNKS:
            event = {"choices": [{"delta": {"content": piece}}]}
            self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))

    from assets.llm_client import LlamaServerClient
    from assets.translator import build_messages, detect_direction

    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        client = LlamaServerClient(f"http://127.0.0.1:{port}")
        assert client.health(), "health check 应返回 True"

        messages = build_messages("你好世界", "中 → 英", "正式商务")
        assert messages[0]["role"] == "system"
        assert "Chinese" in messages[0]["content"] and "English" in messages[0]["content"]

        out = "".join(client.stream_chat(messages))
        assert out == "".join(CHUNKS), f"流式内容不匹配：{out!r}"

        assert detect_direction("你好") == "中 → 英"
        assert detect_direction("Hello") == "英 → 中"

        print("[PASS] 冒烟测试通过。")
        print("       流式输出：", out)
        return 0
    finally:
        server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
