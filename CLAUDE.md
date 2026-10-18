# CLAUDE.md — leiturgia-desktop

Code-side project guide for the Leiturgia Desktop build (Forge-owned, travels via
git). Planning/process docs live in `~/devops/projects/leiturgia-desktop/CLAUDE.md`.

## What this is

A portable Windows desktop build of the Leiturgia church service projection app.
The frozen exe launches the existing Flask/SocketIO server and opens a native
projection window on the chosen monitor.

## Build / run

```bash
# dependencies
pip install -r requirements-desktop.txt pyinstaller

# stage the parent server tree (defaults to ../Leiturgia)
bash scripts/build.sh /path/to/Leiturgia

# build the onefile exe
pyinstaller leiturgia.spec --noconfirm
```

Output: `dist/leiturgia-desktop.exe`.

Run from source:

```bash
LEITURGIA_SERVER_DIR=/path/to/Leiturgia python desktop_entry.py
```

`LEITURGIA_HEADLESS=1` runs the server without a projection window (CI).

## Architecture constants

- **Server:** the parent `darqlab/leiturgia` Flask/SocketIO app, bundled as data
  under `_MEIPASS/leiturgia_server` and extracted into the app dir at runtime.
- **Shell:** `desktop_entry.py` — app-dir resolution, first-run config seed, server
  worker thread, monitor selection, native window, browser fallback.
- **Native window:** pywebview (WebView2 on Windows). Browser fallback: `webbrowser`.
- **Config:** `config.json` in the app dir; desktop keys `desktop_mode`, `bind_lan`,
  `monitor`. `enable_self_update` is `false`.
- **Downloader:** `downloader/` — separate yt-dlp wrapper; writes into
  `<app dir>/media/videos`.
- **Port:** 5000, falling back through 5010.

## Key rules

- The server tree is extracted only when the embedded `_server_version.txt` changes;
  `config.json` is never overwritten by extraction.
- `session_secret` is generated per install; the default PIN is `1234` (operator
  changes it).
- Do not add `yt-dlp` or `ffmpeg` to the desktop build.
- Parent-server hooks live in `patches/` until applied to `darqlab/leiturgia`.

## Tests

No automated test suite yet. CI smoke-tests the built exe (headless health check).
Manual verification: two-monitor projection, browser fallback, LAN remote, media
import, downloader.
