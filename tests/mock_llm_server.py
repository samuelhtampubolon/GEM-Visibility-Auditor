"""Server HTTP lokal yang meniru format wire Claude, Gemini, dan OpenAI.

Dipakai tes untuk menguji jalur HTTP sungguhan (requests, header, body, retry,
parsing) tanpa kunci API. Semua permintaan dicatat di server.requests.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ANSWERS = {
    "anthropic": "Rekomendasi: Bali, Labuan Bajo (Pulau Komodo), lalu Danau Toba di Sumatra Utara. "
                 "Lake Toba dan Pulau Samosir sangat indah.",
    "gemini": "1. Bali\n2. Raja Ampat\n3. Yogyakarta dan Borobudur\n4. Labuan Bajo",
    "openai": "Top picks: Bali, Lombok, Gili Trawangan, Lake Toba, and Komodo National Park.",
}


class MockState:
    def __init__(self):
        self.requests = []
        self.fail_first = 0           # jumlah 429 sebelum sukses
        self.reject_fallbacks = False  # balas 400 bila body memuat 'fallbacks'
        self.refuse = False
        self.unauthorized = False
        self.lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    state: MockState = None  # diisi oleh start_server

    def log_message(self, *args):  # senyap
        pass

    def _send(self, code: int, payload: dict, headers: dict | None = None):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        st = self.state
        with st.lock:
            st.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()},
                                "body": body})
            n = len(st.requests)
            if st.fail_first and n <= st.fail_first:
                return self._send(429, {"error": {"type": "rate_limit_error", "message": "slow down"}},
                                  {"retry-after": "0"})
        if st.unauthorized:
            return self._send(401, {"type": "error", "error": {"type": "authentication_error",
                                                               "message": "invalid x-api-key"}})
        if self.path == "/v1/messages":
            if st.reject_fallbacks and "fallbacks" in body:
                return self._send(400, {"type": "error", "error": {"type": "invalid_request_error",
                                                                   "message": "fallbacks: Extra inputs are not permitted"}})
            if st.refuse:
                return self._send(200, {"type": "message", "content": [], "stop_reason": "refusal",
                                        "stop_details": {"type": "refusal", "category": "cyber"},
                                        "usage": {"input_tokens": 10, "output_tokens": 0}})
            return self._send(200, {
                "id": "msg_mock", "type": "message", "role": "assistant", "model": body["model"],
                "content": [{"type": "thinking", "thinking": "", "signature": "x"},
                            {"type": "text", "text": ANSWERS["anthropic"]}],
                "stop_reason": "end_turn", "usage": {"input_tokens": 21, "output_tokens": 55},
            })
        if self.path.startswith("/v1beta/models/") and self.path.endswith(":generateContent"):
            return self._send(200, {
                "candidates": [{"content": {"role": "model", "parts": [
                    {"text": "Bali Bali Bali (pikiran internal)", "thought": True},
                    {"text": ANSWERS["gemini"]}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 30, "thoughtsTokenCount": 5},
            })
        if self.path.endswith("/chat/completions"):
            return self._send(200, {
                "id": "chatcmpl-mock", "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": ANSWERS["openai"]},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 15, "completion_tokens": 25},
            })
        return self._send(404, {"error": {"message": f"unknown path {self.path}"}})


def start_server():
    state = MockState()
    handler = type("BoundHandler", (Handler,), {"state": state})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    srv.state = state
    srv.base = f"http://127.0.0.1:{srv.server_address[1]}"
    return srv
