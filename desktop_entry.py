"""Desktop shell for the Leiturgia server (leiturgia-desktop).

Starts the Flask/SocketIO server in a worker thread and opens a native
projection window (WebView2 via pywebview) on the chosen monitor. Falls back
to the default browser when the native window is unavailable.

Packaging model: the frozen exe bundles the server tree as data under
``_MEIPASS/leiturgia_server`` and extracts it into the app directory on first
run, so the server's ``root_path`` and the current working directory coincide
(user config/data/media live next to the exe, never inside the bundle).
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

logger = logging.getLogger("leiturgia.desktop")

APP_DIR = ""
_PORT_START = 5000
_PORT_ATTEMPTS = 11
_READY_TIMEOUT = 60.0
_SERVER_SUBDIR = "leiturgia_server"


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _resolve_app_dir() -> str:
    if _is_frozen():
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        exe_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.isdir(exe_dir) and os.access(exe_dir, os.W_OK):
        return exe_dir
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    fallback = os.path.join(local, "Leiturgia")
    os.makedirs(fallback, exist_ok=True)
    return fallback


def _embedded_server_dir() -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, _SERVER_SUBDIR)
    return os.environ.get("LEITURGIA_SERVER_DIR") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "server_src"
    )


def _atomic_write(path: str, data: dict) -> None:
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _seed_config_if_missing() -> None:
    if os.path.exists("config.json"):
        return
    cfg: dict = {}
    if os.path.exists("config.example.json"):
        with open("config.example.json") as f:
            cfg = json.load(f)
    cfg.setdefault("pin", "1234")
    cfg["session_secret"] = secrets.token_urlsafe(32)
    cfg.setdefault("session_timeout_hours", 8)
    cfg.setdefault("max_login_attempts", 5)
    cfg.setdefault("cloud_enabled", False)
    cfg.setdefault("cloud_url", "")
    cfg.setdefault("cloud_token", "")
    cfg.setdefault("enable_self_update", False)
    cfg.setdefault("log_level", "INFO")
    cfg["desktop_mode"] = True
    cfg["bind_lan"] = False
    cfg["monitor"] = "auto"
    _atomic_write("config.json", cfg)
    logger.info("seeded config.json with a generated session_secret")


def _read_server_version(src: str) -> str:
    try:
        with open(os.path.join(src, "_server_version.txt")) as f:
            return f.read().strip()
    except OSError:
        return ""


def _extract_server() -> None:
    src = _embedded_server_dir()
    if not os.path.isdir(src):
        logger.warning("embedded server tree not found at %s", src)
        return
    version = _read_server_version(src)
    marker = os.path.join(APP_DIR, "_server_version")
    if version and os.path.isfile(marker) and os.path.isfile(os.path.join(APP_DIR, "app.py")):
        try:
            with open(marker) as f:
                if f.read().strip() == version:
                    return
        except OSError:
            pass
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        dst_root = APP_DIR if rel == "." else os.path.join(APP_DIR, rel)
        os.makedirs(dst_root, exist_ok=True)
        for name in files:
            if name == "config.json":
                continue
            shutil.copy2(os.path.join(root, name), os.path.join(dst_root, name))
    if version:
        with open(marker, "w") as f:
            f.write(version)
    logger.info("extracted server tree from %s", src)


def _setup_paths() -> None:
    global APP_DIR
    APP_DIR = _resolve_app_dir()
    if _is_frozen():
        _extract_server()
        sys.path.insert(0, APP_DIR)
        os.chdir(APP_DIR)
        _seed_config_if_missing()
        return
    server_dir = _embedded_server_dir()
    if not os.path.isdir(server_dir):
        raise SystemExit(
            f"server source not found: {server_dir} (set LEITURGIA_SERVER_DIR)"
        )
    sys.path.insert(0, server_dir)
    os.chdir(server_dir)


def _load_config() -> dict:
    try:
        with open("config.json") as f:
            return json.load(f)
    except Exception:
        return {}


def _bind_host() -> str:
    return "0.0.0.0" if _load_config().get("bind_lan") else "127.0.0.1"


def _pick_port() -> int:
    import socket

    for port in range(_PORT_START, _PORT_START + _PORT_ATTEMPTS):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return _PORT_START


def _wait_for_server(port: int, timeout: float = _READY_TIMEOUT, proc=None) -> bool:
    url = f"http://127.0.0.1:{port}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def _choose_monitor(spec):
    try:
        from screeninfo import get_monitors
    except Exception:
        return None
    try:
        monitors = get_monitors()
    except Exception:
        return None
    if not monitors:
        return None
    spec = (spec or "auto").strip()
    if spec.lower() == "auto":
        for m in monitors:
            if not getattr(m, "is_primary", False):
                return m
        return monitors[0]
    try:
        idx = int(spec)
        if 0 <= idx < len(monitors):
            return monitors[idx]
    except (TypeError, ValueError):
        pass
    for m in monitors:
        if spec.lower() in (getattr(m, "name", "") or "").lower():
            return m
    return monitors[0]


def _run_server(host: str, port: int) -> None:
    """Run the Flask/SocketIO server in this process (blocking).

    app.py monkey-patches threading via eventlet, which starves Qt/pywebview's own
    helper threads, so the GUI process never imports it: the server runs as a
    child process (``LEITURGIA_ROLE=server``) and the GUI process only talks HTTP.
    """
    server = importlib.import_module("app")
    try:
        starter = getattr(server, "start_background_services", None)
        if callable(starter):
            starter()
        else:
            server.socketio.start_background_task(server._timer_tick_loop)
            server.socketio.start_background_task(server._cloud_update_pump)
        server.socketio.run(server.app, host=host, port=port, debug=False)
    except Exception:
        logger.exception("server failed")
        raise


def _spawn_server(host: str, port: int) -> subprocess.Popen:
    cmd = [sys.executable] if _is_frozen() else [sys.executable, os.path.abspath(__file__)]
    env = dict(os.environ, LEITURGIA_ROLE="server", LEITURGIA_HOST=host, LEITURGIA_PORT=str(port))
    return subprocess.Popen(cmd, env=env)


def _stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _open_projection(port: int, monitor) -> bool:
    """Open the native projection window. Returns False if it fell back to the browser."""
    url = f"http://127.0.0.1:{port}/ch1"
    try:
        import webview

        kwargs = {"title": "Leiturgia", "url": url, "fullscreen": True}
        if monitor is not None:
            kwargs.update(
                x=monitor.x,
                y=monitor.y,
                width=monitor.width,
                height=monitor.height,
            )
        window = webview.create_window(**kwargs)
        start_kwargs = {}
        if sys.platform.startswith("linux"):
            # The frozen binary bundles Qt WebEngine; system GTK is not reachable from it.
            start_kwargs["gui"] = "qt"
        if os.environ.get("LEITURGIA_SELFTEST"):
            start_kwargs["func"] = _selftest_close
            start_kwargs["args"] = (window,)
        webview.start(**start_kwargs)
        return True
    except Exception:
        logger.exception("native window failed; falling back to the browser")
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            logger.exception("browser fallback failed")
        return False


def _selftest_close(window) -> None:
    """CI self-test: wait for the page to load in the native window, report, close."""
    loaded = window.events.loaded.wait(60)
    print("NATIVE_WINDOW_OK" if loaded else "NATIVE_WINDOW_TIMEOUT", flush=True)
    window.destroy()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _setup_paths()

    if os.environ.get("LEITURGIA_ROLE") == "server":
        _run_server(os.environ["LEITURGIA_HOST"], int(os.environ["LEITURGIA_PORT"]))
        return 0

    host = _bind_host()
    port = _pick_port()

    if os.environ.get("LEITURGIA_HEADLESS"):
        logger.info("headless mode: serving without a projection window")
        _run_server(host, port)
        return 0

    proc = _spawn_server(host, port)
    try:
        if not _wait_for_server(port, proc=proc):
            logger.error("server did not become ready on port %d", port)
            return 1
        logger.info("Leiturgia desktop ready: http://127.0.0.1:%d/ (projection /ch1)", port)
        monitor = _choose_monitor(_load_config().get("monitor", "auto"))
        native = _open_projection(port, monitor)
        if os.environ.get("LEITURGIA_SELFTEST") and not native:
            return 1
        return 0
    finally:
        _stop_server(proc)


if __name__ == "__main__":
    sys.exit(main())
