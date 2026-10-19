"""Throwaway multi-screen spike (TM 5.0). One test per process:

    <venv>/bin/python spike/multiscreen_spike.py --gui qt|gtk --test q1a|q1b|q2|q3|q4|q5|q6|q7 [opts]

Results are printed as JSON and written to $SPIKE_RUN_DIR/<gui>_<test>[_variant].json.
The server is never imported here (eventlet would starve the GUI threads); Q4/Q5 talk to a
separately started server over HTTP.
"""
import argparse
import functools
import http.server
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
PAGES = os.path.join(HERE, "pages")
RUN = os.environ.get("SPIKE_RUN_DIR", "/tmp")
PAGES_PORT, FOREIGN_PORT = 8791, 8792
RESULT = {}


def watchdog(seconds):
    def boom():
        RESULT["watchdog"] = f"killed after {seconds}s"
        dump()
        os._exit(99)
    t = threading.Timer(seconds, boom)
    t.daemon = True
    t.start()


def dump():
    name = f"{ARGS.gui}_{ARGS.test}" + (f"_{ARGS.variant}" if ARGS.variant else "") + (
        f"_{ARGS.method}" if ARGS.test in ("q2", "q3") else "")
    with open(os.path.join(RUN, name + ".json"), "w") as f:
        json.dump(RESULT, f, indent=2, default=str)
    print(json.dumps(RESULT, indent=2, default=str), flush=True)


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        p = urlparse(path).path
        if p.startswith("/media/"):
            return os.path.join(RUN, "media", os.path.basename(p))
        return os.path.join(PAGES, os.path.basename(p) or "index.html")

    def log_message(self, *a):
        pass


def serve(port):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def mon_dict(m):
    return {"name": getattr(m, "name", None), "x": m.x, "y": m.y, "w": m.width, "h": m.height,
            "primary": getattr(m, "is_primary", None)}


def screen_dict(s):
    return {"x": s.x, "y": s.y, "w": s.width, "h": s.height}


def contains(mon, g):
    return (g["x"] >= mon["x"] and g["y"] >= mon["y"]
            and g["x"] + g["w"] <= mon["x"] + mon["w"] and g["y"] + g["h"] <= mon["y"] + mon["h"])


# ---------------------------------------------------------------- toolkit helpers
def on_gtk_main(fn, timeout=5):
    from gi.repository import GLib
    box, ev = {}, threading.Event()

    def run():
        try:
            box["v"] = fn()
        except Exception as e:
            box["e"] = repr(e)
        ev.set()
        return False
    GLib.idle_add(run)
    ev.wait(timeout)
    return box.get("v", {"error": box.get("e", "timeout")})


def native_geom(w):
    try:
        if ARGS.gui == "qt":
            from PyQt6.QtWidgets import QWidget
            bv = w.native
            g = QWidget.geometry(bv)  # pywebview's BrowserView shadows geometry with a QRect attribute
            return {"x": g.x(), "y": g.y(), "w": g.width(), "h": g.height(),
                    "fullscreen": bv.isFullScreen(), "screen": QWidget.screen(bv).name()}
        gw = getattr(w.native, "window", w.native)

        def read():
            x, y = gw.get_position()
            width, height = gw.get_size()
            d = gw.get_display()
            m = d.get_monitor_at_window(gw.get_window())
            return {"x": x, "y": y, "w": width, "h": height,
                    "fullscreen": bool(gw.get_window().get_state() & 16),
                    "screen": m.get_model()}
        return on_gtk_main(read)
    except Exception as e:
        return {"error": repr(e)}


JS_GEOM = ("({sx: window.screenX, sy: window.screenY, iw: window.innerWidth, ih: window.innerHeight, "
           "ow: window.outerWidth, oh: window.outerHeight, dpr: window.devicePixelRatio, href: location.href})")


def js_geom(w):
    try:
        return w.evaluate_js(JS_GEOM)
    except Exception as e:
        return {"error": repr(e)}


def poll_js(w, expr, timeout=10, interval=0.25):
    end = time.time() + timeout
    v = None
    while time.time() < end:
        try:
            v = w.evaluate_js(expr)
        except Exception:
            v = None
        if v is not None:
            return v
        time.sleep(interval)
    return None


def health(base):
    try:
        with urllib.request.urlopen(base + "/api/health", timeout=2) as r:
            return r.status
    except Exception as e:
        return repr(e)


def http_status(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return {"status": r.status, "final_url": r.geturl(), "bytes": len(r.read())}
    except Exception as e:
        return {"error": repr(e)}


# ---------------------------------------------------------------- Q1
def q1a():
    from screeninfo import get_monitors
    RESULT["screeninfo"] = [mon_dict(m) for m in get_monitors()]
    if ARGS.gui == "qt":
        from PyQt6.QtGui import QGuiApplication
        app = QGuiApplication([])
        prim = app.primaryScreen().name()
        RESULT["toolkit"] = {"kind": "QGuiApplication.screens()", "primary": prim, "screens": [
            {"name": s.name(), "x": s.geometry().x(), "y": s.geometry().y(), "w": s.geometry().width(),
             "h": s.geometry().height(), "dpr": s.devicePixelRatio()} for s in app.screens()]}
    else:
        import gi
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk
        Gdk.init([])
        d = Gdk.Display.get_default()
        prim = d.get_primary_monitor()
        mons = []
        for i in range(d.get_n_monitors()):
            m = d.get_monitor(i)
            g = m.get_geometry()
            mons.append({"model": m.get_model(), "x": g.x, "y": g.y, "w": g.width, "h": g.height,
                         "scale": m.get_scale_factor(), "primary": m.is_primary()})
        RESULT["toolkit"] = {"kind": "Gdk.Display monitors", "monitors": mons}
    dump()


def q1b():
    import webview
    try:
        RESULT["webview_screens_before_start"] = [screen_dict(s) for s in webview.screens]
    except Exception as e:
        RESULT["webview_screens_before_start"] = f"error: {e!r}"
    w = webview.create_window("q1", html="<p>q1</p>", width=300, height=200)

    def func():
        w.events.loaded.wait(20)
        try:
            RESULT["webview_screens_after_start"] = [screen_dict(s) for s in webview.screens]
        except Exception as e:
            RESULT["webview_screens_after_start"] = f"error: {e!r}"
        w.destroy()
    webview.start(func, gui=ARGS.gui)
    dump()


# ---------------------------------------------------------------- Q2 / Q3
def targets():
    """Monitor lists from screeninfo (pre-start) and pywebview (pre-start)."""
    import webview
    from screeninfo import get_monitors
    si = list(get_monitors())
    try:
        wv = list(webview.screens)
    except Exception as e:
        RESULT["webview_screens_error"] = repr(e)
        wv = []
    return si, wv


def open_window(webview, title, url, idx, si, wv, method, fullscreen, **extra):
    late = method == "late"  # screen= placement, fullscreen toggled only after the window is shown
    kw = dict(title=title, url=url, fullscreen=fullscreen and not late, **extra)
    if method in ("screen", "late"):
        kw["screen"] = wv[idx]
        if late and fullscreen:
            kw.update(width=wv[idx].width, height=wv[idx].height)
    else:
        m = si[idx]
        kw.update(x=m.x, y=m.y)
        if not fullscreen:
            kw.update(width=900, height=600, x=m.x + 60, y=m.y + 60)
        else:
            kw.update(width=m.width, height=m.height)
    return webview.create_window(**kw)


def settle(w, secs=2.0):
    w.events.loaded.wait(30)
    time.sleep(secs)
    return {"js": js_geom(w), "native": native_geom(w)}


def verdict(mon, rec):
    g = rec["native"] if isinstance(rec.get("native"), dict) and "x" in rec["native"] else None
    if g is None:
        js = rec["js"]
        g = {"x": js.get("sx"), "y": js.get("sy"), "w": js.get("ow"), "h": js.get("oh")} if "sx" in js else None
        src = "js(outer)"
    else:
        src = "native"
    if g is None:
        return {"source": None, "on_target": None}
    return {"source": src, "actual": g, "on_target": contains(mon, g),
            "exact_fill": (g["x"], g["y"], g["w"], g["h"]) == (mon["x"], mon["y"], mon["w"], mon["h"])}


def q2():
    import webview
    base = ARGS.server
    si, wv = targets()
    RESULT["method"] = ARGS.method
    RESULT["screeninfo"] = [mon_dict(m) for m in si]
    RESULT["webview_screens"] = [screen_dict(s) for s in wv]
    n = len(si)
    plan = [("console", "/", 0, False)] + [(f"proj{i}", f"/ch{i}", i, True) for i in range(1, min(n, 3))]
    wins = [(name, open_window(webview, name, base + path, idx, si, wv, ARGS.method, fs), idx)
            for name, path, idx, fs in plan]

    def func():
        RESULT["windows"] = {}
        for name, w, idx in wins:
            if ARGS.method == "late" and idx != 0:
                w.events.loaded.wait(30)
                time.sleep(1)
                w.toggle_fullscreen()
            rec = settle(w)
            rec["target_screeninfo"] = mon_dict(si[idx])
            rec["verdict_vs_screeninfo"] = verdict(mon_dict(si[idx]), rec)
            if wv:
                rec["verdict_vs_webview_screen"] = verdict(screen_dict(wv[idx]), rec)
            RESULT["windows"][name] = rec
        for _, w, _ in wins:
            w.destroy()
    webview.start(func, gui=ARGS.gui)
    dump()


def q3():
    import webview
    base = ARGS.server
    si, wv = targets()
    method = ARGS.method
    wins = {}
    wins["console"] = open_window(webview, "console", base + "/", 0, si, wv, method, False)
    wins["proj1"] = open_window(webview, "proj1", base + "/ch1", 1, si, wv, method, True)
    wins["proj2"] = open_window(webview, "proj2", base + "/ch2", 2, si, wv, method, True)
    RESULT["method"] = method

    def func():
        RESULT["steps"] = []
        for w in wins.values():
            w.events.loaded.wait(30)
        time.sleep(2)
        RESULT["steps"].append({"step": "initial", "windows": len(webview.windows),
                                "proj1": js_geom(wins["proj1"])})
        t = time.time()
        wins["proj1"].destroy()
        wins["proj2"].destroy()
        time.sleep(2)
        RESULT["steps"].append({"step": "after_destroy_proj", "windows": len(webview.windows)})
        try:
            nw = open_window(webview, "proj1b", base + "/ch4", 1, si, wv, method, True)
            ok = nw.events.loaded.wait(30)
            if method == "late":
                time.sleep(1)
                nw.toggle_fullscreen()
            time.sleep(2)
            RESULT["steps"].append({"step": "recreated_on_monitor1_as_ch4", "loaded": ok,
                                    "windows": len(webview.windows), "geom": js_geom(nw),
                                    "native": native_geom(nw), "seconds": round(time.time() - t, 1),
                                    "target": mon_dict(si[1])})
            wins["proj1b"] = nw
        except Exception as e:
            RESULT["steps"].append({"step": "recreate_failed", "error": repr(e)})
        for k, w in list(wins.items()):
            try:
                w.destroy()
            except Exception:
                pass
        time.sleep(2)
        RESULT["steps"].append({"step": "after_destroy_all", "windows": len(webview.windows)})
    t0 = time.time()
    webview.start(func, gui=ARGS.gui)
    RESULT["start_returned_after_s"] = round(time.time() - t0, 1)
    RESULT["note"] = "start() returned -> process can exit; exit code checked by the shell wrapper"
    dump()


# ---------------------------------------------------------------- Q4
def q4():
    import webview
    base = ARGS.server
    si, wv = targets()
    RESULT["http"] = {p: http_status(base + p) for p in ("/", "/ch1", "/api/health")}
    a = webview.create_window("console", base + "/", x=si[0].x + 60, y=si[0].y + 60, width=900, height=600)
    b = webview.create_window("ch1", base + "/ch1", x=si[0].x + 120, y=si[0].y + 120, width=900, height=600)

    def func():
        RESULT["windows"] = {}
        for name, w in (("console", a), ("ch1", b)):
            ok = w.events.loaded.wait(30)
            RESULT["windows"][name] = {"loaded": ok, "title": w.evaluate_js("document.title"),
                                       "href": w.evaluate_js("location.href")}
        RESULT["ch1_socket_connected_initial"] = poll_js(b, "(typeof socket !== 'undefined' && socket.connected) ? true : null", 15)
        if not ARGS.server_pid:
            RESULT["restart_test"] = "skipped: no --server-pid (remote server is not ours to kill)"
            for w in (a, b):
                w.destroy()
            return
        pid = int(open(ARGS.server_pid).read())
        t = time.time()
        os.kill(pid, signal.SIGTERM)
        time.sleep(4)
        RESULT["after_kill"] = {"health": health(base), "socket_connected": b.evaluate_js(
            "typeof socket !== 'undefined' ? socket.connected : null")}
        subprocess.Popen(ARGS.restart_cmd, shell=True, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        up = None
        for _ in range(60):
            if health(base) == 200:
                up = round(time.time() - t, 1)
                break
            time.sleep(1)
        RESULT["server_back_after_s"] = up
        rec = None
        for _ in range(60):
            c = b.evaluate_js("typeof socket !== 'undefined' ? socket.connected : null")
            if c:
                rec = round(time.time() - t, 1)
                break
            time.sleep(1)
        RESULT["socket_reconnected_after_s"] = rec
        RESULT["reload_needed"] = rec is None
        for w in (a, b):
            w.destroy()
    webview.start(func, gui=ARGS.gui)
    dump()


# ---------------------------------------------------------------- Q5
class Api:
    def __init__(self, allowed):
        self.allowed = allowed
        self.window = None
        self.log = []

    def ping(self, tag="x"):
        url = self.window.get_current_url() if self.window else None
        o = urlparse(url or "")
        origin = f"{o.scheme}://{o.netloc}"
        ok = origin == self.allowed
        self.log.append({"tag": tag, "window_url": url, "origin": origin, "accepted": ok})
        if not ok:
            return {"ok": False, "error": "origin rejected", "seen_origin": origin}
        return {"ok": True, "seen_origin": origin, "secret": "bridge-ok"}


def q5():
    import webview
    base = ARGS.server
    srv_origin = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    pages_origin = f"http://127.0.0.1:{PAGES_PORT}"
    foreign_origin = f"http://127.0.0.1:{FOREIGN_PORT}"
    si, _ = targets()
    cases = {}

    def mk(name, url, allowed, off):
        api = Api(allowed)
        w = webview.create_window(name, url, js_api=api, x=si[0].x + off, y=si[0].y + off,
                                  width=700, height=450)
        api.window = w
        cases[name] = (w, api)
    mk("server_origin", base + "/ch1", srv_origin, 40)
    mk("foreign_origin", f"{foreign_origin}/bridge.html?tag=foreign", srv_origin, 80)
    mk("iframe_in_allowed_page", f"{pages_origin}/bridge_frame.html?foreign={foreign_origin}", pages_origin, 120)

    def func():
        out = RESULT.setdefault("cases", {})
        for name, (w, api) in cases.items():
            w.events.loaded.wait(30)
        time.sleep(2)
        w, api = cases["server_origin"]
        w.evaluate_js("window.__r = null; (window.pywebview && window.pywebview.api) ? "
                      "pywebview.api.ping('server').then(r => { window.__r = r; }).catch(e => { window.__r = {err: String(e)}; }) : "
                      "(window.__r = {err: 'no pywebview.api'}); 1")
        out["server_origin"] = {"allowed": srv_origin, "js_result": poll_js(w, "window.__r", 10),
                                "typeof_pywebview": w.evaluate_js("typeof window.pywebview"),
                                "python_side_log": api.log}
        w, api = cases["foreign_origin"]
        out["foreign_origin"] = {"allowed": srv_origin, "page_result": poll_js(w, "window.__result", 10),
                                 "python_side_log": api.log}
        w, api = cases["iframe_in_allowed_page"]
        out["iframe_in_allowed_page"] = {"allowed": pages_origin, "iframe_page_result": poll_js(w, "window.__frame", 10),
                                         "python_side_log": api.log}
        for w, _ in cases.values():
            w.destroy()
    webview.start(func, gui=ARGS.gui)
    dump()


# ---------------------------------------------------------------- Q6 / Q7
def apply_autoplay_setting(w, variant):
    """Returns a note on how the no-gesture setting was applied (or why not)."""
    if variant == "default":
        return "none (defaults)"
    if variant == "flag":
        return "QTWEBENGINE_CHROMIUM_FLAGS=--autoplay-policy=no-user-gesture-required (env, before start)"
    if ARGS.gui == "qt":
        from PyQt6.QtWebEngineCore import QWebEngineSettings
        s = w.native.webview.settings()
        before = s.testAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture)
        s.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        after = s.testAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture)
        return f"backend reach-in: window.native.webview.settings().setAttribute(PlaybackRequiresUserGesture, False) {before}->{after}"
    from webview.platforms.gtk import BrowserView

    def apply():
        st = BrowserView.instances[w.uid].webview.get_settings()
        before = st.get_media_playback_requires_user_gesture()
        st.set_media_playback_requires_user_gesture(False)
        return before, st.get_media_playback_requires_user_gesture()
    before, after = on_gtk_main(apply)
    return ("backend reach-in: BrowserView.instances[w.uid].webview.get_settings()."
            f"set_media_playback_requires_user_gesture(False) {before}->{after}")


def play_one(w, src, unmute):
    w.load_url(f"http://127.0.0.1:{PAGES_PORT}/media.html?src=/media/{src}&unmute={1 if unmute else 0}")
    time.sleep(0.5)
    return poll_js(w, "window.__result", 15)


def gtk_autoplay_policy_patch():
    """WebKitGTK autoplay is a construct-only WebsitePolicies property: wrap pywebview's WebView ctor."""
    import webview.platforms.gtk as g
    from gi.repository import WebKit2
    orig = g.webkit.WebView

    def ctor(*a, **kw):
        kw["website_policies"] = WebKit2.WebsitePolicies(autoplay=WebKit2.AutoplayPolicy.ALLOW)
        return orig(*a, **kw)
    g.webkit = type("WK", (), {"WebView": staticmethod(ctor), "__getattr__": lambda s, n: getattr(WebKit2, n)})()
    return "monkeypatched pywebview.platforms.gtk.webkit.WebView ctor with WebsitePolicies(autoplay=ALLOW) (construct-only property)"


def q6():
    import webview
    if ARGS.gui == "gtk" and ARGS.variant.startswith("policy"):
        RESULT["policy_patch"] = gtk_autoplay_policy_patch()
    w = webview.create_window("q6", "about:blank", width=500, height=400)

    def func():
        w.events.loaded.wait(20)
        try:
            RESULT["how_applied"] = apply_autoplay_setting(w, ARGS.variant)
        except Exception as e:
            RESULT["how_applied"] = f"FAILED: {e!r}"
        RESULT["webm_vp9_opus_muted_play_then_unmute_no_click"] = play_one(w, "test.webm", True)
        RESULT["note"] = "no audio device under test: element state is checked, not audible sound"
        w.destroy()
    webview.start(func, gui=ARGS.gui)
    dump()


def q7():
    import webview
    w = webview.create_window("q7", "about:blank", width=500, height=400)

    def func():
        w.events.loaded.wait(20)
        try:
            RESULT["how_applied"] = apply_autoplay_setting(w, "settings")
        except Exception as e:
            RESULT["how_applied"] = f"FAILED: {e!r}"
        RESULT["files"] = {}
        for f in ("test.mp4", "test.webm", "test.mp3"):
            RESULT["files"][f] = play_one(w, f, False)
        w.destroy()
    webview.start(func, gui=ARGS.gui)
    dump()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gui", required=True, choices=["qt", "gtk"])
    ap.add_argument("--test", required=True)
    ap.add_argument("--method", default="xy", choices=["xy", "screen", "late"])
    ap.add_argument("--variant", default="")
    ap.add_argument("--server", default="http://127.0.0.1:5077")
    ap.add_argument("--server-pid")
    ap.add_argument("--restart-cmd")
    ARGS = ap.parse_args()
    if ARGS.variant == "flag":
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--autoplay-policy=no-user-gesture-required"
    watchdog(150)
    serve(PAGES_PORT)
    serve(FOREIGN_PORT)
    RESULT["env"] = {"gui": ARGS.gui, "test": ARGS.test, "python": sys.version.split()[0]}
    globals()[ARGS.test]()
