"""CLI for the Leiturgia media downloader.

Usage:
    python -m downloader <url> --out <dir> [--quality best|1080p|720p|480p|360p|audio]
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

QUALITIES = ("best", "1080p", "720p", "480p", "360p", "audio")

_QUALITY_MERGE = {
    "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]",
    "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]",
    "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]",
    "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best[height<=360]",
    "audio": "bestaudio[ext=m4a]/bestaudio",
}
_QUALITY_NOFFMPEG = {
    "best": "best[ext=mp4]/best",
    "1080p": "best[height<=1080][ext=mp4]/best[height<=1080]",
    "720p": "best[height<=720][ext=mp4]/best[height<=720]",
    "480p": "best[height<=480][ext=mp4]/best[height<=480]",
    "360p": "best[height<=360][ext=mp4]/best[height<=360]",
    "audio": "bestaudio[ext=m4a]/bestaudio",
}


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _format_for(quality: str) -> str:
    table = _QUALITY_MERGE if _has_ffmpeg() else _QUALITY_NOFFMPEG
    return table.get(quality, table["best"])


def download(url: str, out_dir: str, quality: str = "best", cookies: str | None = None) -> str:
    import yt_dlp

    os.makedirs(out_dir, exist_ok=True)
    opts = {
        "format": _format_for(quality),
        "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
        "restrictfilenames": True,
    }
    if _has_ffmpeg():
        opts["merge_output_format"] = "mp4"
    if cookies:
        opts["cookiefile"] = cookies
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="leiturgia-downloader")
    parser.add_argument("url")
    parser.add_argument("--out", required=True, help="output directory (e.g. <app>/media/videos)")
    parser.add_argument("--quality", choices=QUALITIES, default="best")
    parser.add_argument("--cookies", help="path to a cookies.txt file")
    args = parser.parse_args(argv)

    try:
        path = download(args.url, args.out, args.quality, args.cookies)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
