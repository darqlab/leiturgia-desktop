# leiturgia-desktop

A portable **desktop** build (Windows, Linux x86_64, Linux arm64 / Raspberry Pi) of [Leiturgia](https://github.com/darqlab/leiturgia)
— the Flask + Flask-SocketIO church service projection app.

The desktop build runs the existing server locally, projects to a **native window
on the second monitor** (browser-based projection as a fallback), preserves LAN
multi-client, and imports media as files. Media downloading lives in a **separate
wrapper** around yt-dlp (in `downloader/`), so the desktop app never needs yt-dlp
or ffmpeg.

> Docs project: `~/devops/projects/leiturgia-desktop/`
> (planning, design-of-record, task tracker).

## Architecture

```
leiturgia-desktop.exe  (PyInstaller onefile)
  desktop_entry.py
    - resolves the app dir (exe dir, else %LOCALAPPDATA%\Leiturgia)
    - extracts the bundled server tree into the app dir on first run
    - seeds config.json (random session_secret, default PIN 1234)
    - starts the Flask/SocketIO server in a worker thread
    - opens a native projection window (WebView2) on the chosen monitor
    - falls back to the default browser

server tree (bundled as data, extracted at runtime)
  app.py + modules, templates/, static/, data/hymns_*.db, media/images/

leiturgia-downloader  (separate wrapper, downloader/)
  - yt-dlp + ffmpeg -> writes into <app dir>/media/videos
```

## Requirements

- **Windows 10/11** with the **WebView2 runtime** (preinstalled on most systems).
- **Linux x86_64** and **Linux arm64** (Raspberry Pi 4/5 on 64-bit Raspberry Pi OS; 32-bit
  armv7 is not built). Built on Ubuntu 22.04 for an older glibc baseline.
- No Python needed on the target.

### Linux / Raspberry Pi notes

- The frozen Linux binary cannot use the system GTK/WebKit libraries, so it opens the
  projection (`/ch1`) in the **default browser** instead of a native window. Use a
  fullscreen/kiosk browser on the projector output.
- For the native window, run from source with the system bindings:
  `sudo apt install python3-gi gir1.2-webkit2-4.1`, then use a venv created with
  `--system-site-packages`.
- CI (`build-desktop.yml`) smoke-tests all three targets headless (health + login).
  Not yet verified on a real Pi or with a display.

## Build (development)

```bash
# 1. Install the desktop dependencies
pip install -r requirements-desktop.txt pyinstaller

# 2. Stage the parent server tree (defaults to ../Leiturgia)
bash scripts/build.sh /path/to/Leiturgia

# 3. Build the onefile exe
pyinstaller leiturgia.spec --noconfirm
```

Output: `dist/leiturgia-desktop.exe` (Windows) or `dist/leiturgia-desktop` (Linux).

## Run from source

```bash
pip install -r requirements-desktop.txt
LEITURGIA_SERVER_DIR=/path/to/Leiturgia python desktop_entry.py
```

Set `LEITURGIA_HEADLESS=1` to run the server without opening a projection window
(useful for CI smoke tests).

## Configuration

The desktop app seeds `config.json` on first run. Desktop-specific keys:

| Key | Default | Meaning |
|---|---|---|
| `desktop_mode` | `true` | Marks a desktop run |
| `bind_lan` | `false` | `true` binds `0.0.0.0` (LAN remotes); `false` binds `127.0.0.1` |
| `monitor` | `"auto"` | `"auto"` = non-primary monitor; or an index/name |

All other keys are inherited from the parent app (PIN, session, media budgets,
cloud, log level). `enable_self_update` is `false` on desktop.

## Media downloader

```bash
pip install -r downloader/requirements.txt
python -m downloader "https://www.youtube.com/watch?v=..." --out media/videos --quality 720p
```

Writes files into the Leiturgia media folder; the app's media list picks them up.

## Layout

```
leiturgia-desktop/
├── desktop_entry.py          # bootstrap, config, monitor, native window
├── leiturgia.spec            # PyInstaller onefile spec
├── requirements-desktop.txt  # desktop deps (no yt-dlp / ffmpeg)
├── config.example.json       # desktop defaults
├── downloader/               # separate yt-dlp wrapper
├── scripts/build.sh          # stage the parent server tree
└── .github/workflows/build-desktop.yml
```

## Update path

No systemd/git self-update. Updates arrive as a new portable build from the
GitHub Releases page.
