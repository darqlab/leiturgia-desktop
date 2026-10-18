# CLAUDE.md — leiturgia-desktop

Code-side project guide for the Leiturgia Desktop build (Forge-owned, travels via
git). Planning/process docs live in `~/devops/projects/leiturgia-desktop/CLAUDE.md`.

## What this is

A portable desktop build of the Leiturgia church service projection app: a Windows
exe, a Linux x86_64 binary, and a Raspberry Pi (arm64) path run from source. It
launches the existing Flask/SocketIO server and opens a native projection window on
the chosen monitor.

## Build / run

```bash
# dependencies
pip install -r requirements-desktop.txt pyinstaller

# stage the parent server tree (defaults to ../Leiturgia)
bash scripts/build.sh /path/to/Leiturgia

# build the onefile exe
pyinstaller leiturgia.spec --noconfirm
```

Output: `dist/leiturgia-desktop.exe` (Windows) or `dist/leiturgia-desktop` (Linux x86_64).
There is no frozen arm64 build; the Pi runs `bash scripts/run-pi.sh /path/to/Leiturgia`.

Run from source:

```bash
LEITURGIA_SERVER_DIR=/path/to/Leiturgia python desktop_entry.py
```

`LEITURGIA_HEADLESS=1` runs the server in-process without a projection window (CI).
`LEITURGIA_SELFTEST=1` opens the window, prints `NATIVE_WINDOW_OK` once `/ch1` loads, and
exits non-zero on a browser fallback (CI, under xvfb).

## Architecture constants

- **Server:** the parent `darqlab/leiturgia` Flask/SocketIO app, bundled as data
  under `_MEIPASS/leiturgia_server` and extracted into the app dir at runtime.
- **Shell:** `desktop_entry.py` — app-dir resolution, first-run config seed, monitor
  selection, native window, browser fallback. The GUI process **re-executes itself as
  the server child** (`LEITURGIA_ROLE=server`) and never imports `app`: the server's
  `eventlet.monkey_patch()` would starve Qt/pywebview threads.
- **Native window:** pywebview — WebView2 (Windows), bundled Qt WebEngine when frozen
  on Linux (`gui="qt"`, PyQt6 pinned 6.7.x, x86_64 only), system GTK/WebKit from
  source on the Pi. Browser fallback: `webbrowser`.
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

No automated test suite yet. CI (`build-desktop.yml`) builds Windows + Linux x86_64,
smoke-tests them headless (`/api/health`, `/login`), runs the native-window self-test
under xvfb on Linux x86_64 (Qt) and arm64 from source (GTK), and on `v*` tags publishes
the assets with `checksums.txt`.
Manual verification: two-monitor projection, browser fallback, LAN remote, media
import, downloader.
