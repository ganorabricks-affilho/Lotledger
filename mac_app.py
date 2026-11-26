"""Open Ganorabricks in a native Mac window. `python app.py` is unchanged."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

import webview

import app as lotledger
from paths import data_dir


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve(port: int) -> None:
    lotledger.app.run(
        host="127.0.0.1",
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


def _wait_until_up(port: int) -> None:
    url = f"http://127.0.0.1:{port}/"
    for _ in range(100):
        try:
            with urllib.request.urlopen(url, timeout=0.3) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.1)
    raise RuntimeError("Ganorabricks did not start.")


def main() -> None:
    port = _free_port()
    port_file = data_dir() / "port"
    threading.Thread(target=_serve, args=(port,), daemon=True).start()
    _wait_until_up(port)
    port_file.write_text(str(port))
    webview.create_window(
        "Ganorabricks",
        f"http://127.0.0.1:{port}/",
        width=1280,
        height=840,
        min_size=(960, 640),
        text_select=True,
        background_color="#ececec",
    )
    try:
        webview.start()
    finally:
        port_file.unlink(missing_ok=True)
        # The local server thread would otherwise keep the process open.
        os._exit(0)


if __name__ == "__main__":
    main()
