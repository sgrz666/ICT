#!/usr/bin/env python3
"""同源伺服：把 CircuitJS1 的 GWT 产物目录与本项目验收台页面拼到同一个 origin。

为什么要有这个脚本：CircuitJS1 的 JavaScript 接口受同源策略约束（官方 js-interface.html 明写
「simulator code is hosted on the same website」），验收台必须和 simulator 同源。
产物在上游 build 目录里（不能往上游树里写文件），验收台在本目录里，所以用一层薄伺服：
/circuit_harness.html 走本目录，其它一律走 makeSite 产出的 site/（站点根 = war 静态文件 + circuitjs1/ GWT 模块）。

跑法：python source/library/serve_circuitjs.py [port]
"""
import http.server
import os
import socketserver
import sys
import functools
import io

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "upstream", "circuitjs1", "site"))
HARNESS_DIR = os.path.abspath(os.path.dirname(__file__))
MAP = {
    "/circuit_harness.html": os.path.join(HARNESS_DIR, "circuit_harness.html"),
}


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):  # noqa: N802  验收台把结果 POST 回来，由这里落盘（浏览器写不了文件）
        if self.path.split("?")[0] != "/report":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        out = os.path.join(HARNESS_DIR, "circuit-lab-evidence.json")
        with io.open(out, "wb") as f:
            f.write(body)
        print("wrote %s (%d bytes)" % (out, len(body)), flush=True)
        self.send_response(204)
        self.end_headers()

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        if path in MAP:
            with io.open(MAP[path], "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def log_message(self, *a):  # 静音
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    if not os.path.isdir(ROOT):
        print("NOT_FOUND: %s（先跑 makeSite，见 source/upstream/upstream.lock.json 的 gwt_build_2026_10_19）" % ROOT)
        return 1
    with socketserver.TCPServer(("127.0.0.1", port), functools.partial(Handler, directory=ROOT)) as srv:
        print("serving %s on http://127.0.0.1:%d/circuit_harness.html" % (ROOT, port), flush=True)
        srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
