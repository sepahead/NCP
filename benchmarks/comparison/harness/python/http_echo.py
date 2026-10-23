"""HTTP/1.1 keep-alive POST with the standard library, TCP_NODELAY on both ends.

http_echo.py server                          (prints "ready HOST:PORT")
http_echo.py client CALLS WARMUP SPIKES
"""
from __future__ import annotations

import http.client
import http.server
import os
import socket
import sys

from common import Responder, check, measure, report, request, start_server, stop_server


class Echo(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    disable_nagle_algorithm = True
    respond = Responder()

    def do_POST(self) -> None:  # noqa: N802
        body = self.respond(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def server() -> None:
    httpd = http.server.HTTPServer(("127.0.0.1", 0), Echo)
    print(f"ready 127.0.0.1:{httpd.server_address[1]}", flush=True)
    httpd.serve_forever()


def client() -> None:
    calls, warmup, spikes = (int(value) for value in sys.argv[2:5])
    process, address = start_server([sys.executable, "-s", os.path.abspath(__file__), "server"])
    host, port = address.split(":")
    connection = http.client.HTTPConnection(host, int(port))
    connection.connect()
    connection.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    try:
        def call(index: int) -> None:
            data = request(index, spikes)
            connection.request("POST", "/echo", body=data, headers={"Content-Type": "application/octet-stream"})
            check(data, connection.getresponse().read(), spikes)

        times = measure(call, calls, warmup)
    finally:
        connection.close()
        stop_server(process)
    report(times, warmup=warmup, spikes=spikes)


if __name__ == "__main__":
    server() if sys.argv[1] == "server" else client()
