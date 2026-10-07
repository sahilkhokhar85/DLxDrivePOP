import time
from pathlib import Path

import yt_dlp


def download_quality(
    stream_url: str,
    height: int,
    download_dir: Path,
    progress_callback=None,
) -> Path:

    download_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    stamp = int(time.time() * 1000)

    output = download_dir / (
        f"I_Popstar_{height}p_{stamp}.mp4"
    )

    format_selector = (
        f"bestvideo[height<={height}]+bestaudio/"
        f"best[height<={height}]/best"
    )

    def progress(d):

        if d.get("status") == "downloading":

            downloaded = d.get("downloaded_bytes", 0)

            total = (
                d.get("total_bytes")
                or d.get("total_bytes_estimate")
            )

            if total:
                percent = min(
                    100.0,
                    (downloaded / total) * 100
                )
            else:
                percent = 0.0

            speed = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()

            print(
                f"{height}p | "
                f"{percent:.1f}% | "
                f"{speed} | "
                f"ETA {eta}"
            )

            if progress_callback:
                progress_callback(
                    percent,
                    speed,
                    eta
                )

        elif d.get("status") == "finished":

            if progress_callback:
                progress_callback(
                    100.0,
                    "",
                    "00:00"
                )

    opts = {
        "format": format_selector,
        "outtmpl": str(output),
        "merge_output_format": "mp4",

        "hls_use_mpegts": True,

        "concurrent_fragment_downloads": 16,

        "http_headers": {
            "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        },

        "quiet": True,
        "no_warnings": True,

        "progress_hooks": [
            progress
        ],
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([stream_url])

    if (
        not output.exists()
        or output.stat().st_size < 1024
    ):
        raise RuntimeError(
            f"{height}p download failed."
        )

    return output
