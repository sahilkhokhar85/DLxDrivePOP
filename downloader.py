import time
from pathlib import Path

import yt_dlp


class DownloadCancelled(Exception):
    pass


def download_quality(
    stream_url: str,
    height: int,
    download_dir: Path,
    progress=None,
    cancel_event=None,
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

    def progress_hook(d):

        # Check cancellation before processing progress
        if (
            cancel_event is not None
            and cancel_event.is_set()
        ):
            raise DownloadCancelled(
                "Download cancelled by user."
            )

        if progress is None:
            return

        if d.get("status") == "downloading":

            downloaded = d.get(
                "downloaded_bytes",
                0
            )

            total = (
                d.get("total_bytes")
                or d.get("total_bytes_estimate")
            )

            if total:
                percent = (
                    downloaded / total
                ) * 100

                percent = min(
                    100.0,
                    max(0.0, percent)
                )

                progress["percent"] = percent

            progress["speed"] = (
                d.get("_speed_str", "")
                .strip()
            )

            progress["eta"] = (
                d.get("_eta_str", "")
                .strip()
            )

        elif d.get("status") == "finished":

            progress["percent"] = 100.0
            progress["eta"] = "00:00"

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

        "noprogress": True,

        "progress_hooks": [
            progress_hook
        ],
    }

    try:

        with yt_dlp.YoutubeDL(opts) as ydl:

            ydl.download([
                stream_url
            ])

    except DownloadCancelled:

        # Remove incomplete output
        try:
            output.unlink(
                missing_ok=True
            )
        except Exception:
            pass

        raise

    # Check once more after yt-dlp finishes
    if (
        cancel_event is not None
        and cancel_event.is_set()
    ):
        try:
            output.unlink(
                missing_ok=True
            )
        except Exception:
            pass

        raise DownloadCancelled(
            "Download cancelled by user."
        )

    if (
        not output.exists()
        or output.stat().st_size < 1024
    ):
        raise RuntimeError(
            f"{height}p download failed."
        )

    return output
