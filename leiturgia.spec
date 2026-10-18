# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Leiturgia desktop build.

Requires the parent server tree to be staged at ``build/leiturgia_server``
first (see ``scripts/build.sh``). The staged tree is bundled as data and
extracted into the app directory at runtime by ``desktop_entry.py``.
"""

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# eventlet picks its hub (epolls/kqueue/selects) and dnspython pieces via
# importlib at runtime, which PyInstaller's static analysis cannot see.
_dynamic = (
    collect_submodules("eventlet")
    + collect_submodules("dns")
    + collect_submodules("engineio")  # async_drivers.eventlet is chosen by name
    + collect_submodules("socketio")
    + collect_submodules("webview")  # platform backend (qt/winforms) chosen at runtime
)

a = Analysis(
    ["desktop_entry.py"],
    pathex=[],
    binaries=[],
    datas=[("build/leiturgia_server", "leiturgia_server")],
    hiddenimports=_dynamic + [
        # stdlib modules imported only by the bundled server tree (data, not analysed)
        "asyncio", "sqlite3", "glob", "hashlib", "unicodedata", "subprocess",
        "tempfile", "shutil", "datetime", "functools", "socket", "werkzeug",
        "eventlet",
        "eventlet.hubs",
        "greenlet",
        "flask",
        "flask_socketio",
        "engineio",
        "socketio",
        "dotenv",
        "mutagen",
        "flask_limiter",
        "websockets",
        "requests",
        "screeninfo",
        "webview",
        "qtpy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["yt_dlp", "tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="leiturgia-desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
