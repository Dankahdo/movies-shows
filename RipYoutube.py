#!/usr/bin/env python3
"""Quick YouTube downloader using yt_dlp.

Downloads a single video or an entire playlist and outputs MP4 files.

Examples:
  py RipYoutube.py "https://www.youtube.com/watch?v=..."
  py RipYoutube.py "https://www.youtube.com/playlist?list=..."
  py RipYoutube.py "<url>" --output-dir "downloads" --single
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yt_dlp

COOKIE_BROWSERS = ("firefox", "edge", "chrome", "brave")
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
DEFAULT_OUTPUT_DIR = OUTPUT_DIR / "downloads"


def _browser_cookie_available(browser: str) -> bool:
	"""Best-effort check to avoid probing browsers that are not installed."""
	appdata = Path(os.environ.get("APPDATA", ""))
	localappdata = Path(os.environ.get("LOCALAPPDATA", ""))

	if browser == "firefox":
		profiles_dir = appdata / "Mozilla" / "Firefox" / "Profiles"
		return profiles_dir.exists() and any(p.is_dir() for p in profiles_dir.iterdir())
	if browser == "edge":
		return (localappdata / "Microsoft" / "Edge" / "User Data").exists()
	if browser == "chrome":
		return (localappdata / "Google" / "Chrome" / "User Data").exists()
	if browser == "brave":
		return (localappdata / "BraveSoftware" / "Brave-Browser" / "User Data").exists()
	return False


def _cookie_attempt_order() -> tuple[str | None, ...]:
	browsers = tuple(browser for browser in COOKIE_BROWSERS if _browser_cookie_available(browser))
	return browsers + (None,)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Download a YouTube video or playlist as MP4 using yt_dlp.",
	)
	parser.add_argument(
		"url",
		help="YouTube video or playlist URL.",
	)
	parser.add_argument(
		"--output-dir",
		type=Path,
		default=DEFAULT_OUTPUT_DIR,
		help="Directory to save files (default: output/downloads).",
	)
	parser.add_argument(
		"--single",
		action="store_true",
		help="Only download one video, even if URL points to a playlist.",
	)
	parser.add_argument(
		"--buffer-seconds",
		type=float,
		default=4.0,
		help="Delay between downloads in seconds to reduce bot/rate triggering (default: 4).",
	)
	return parser.parse_args()


def resolve_download_url(url: str, single: bool) -> str:
	"""Normalize YouTube URL so playlist downloads work from watch links too."""
	if single:
		return url

	parsed = urlparse(url)
	query = parse_qs(parsed.query)
	playlist_ids = query.get("list")
	if playlist_ids:
		playlist_id = playlist_ids[0].strip()
		if playlist_id:
			return f"https://www.youtube.com/playlist?list={playlist_id}"

	return url


def build_ydl_options(
	output_dir: Path,
	single: bool,
	cookie_browser: str | None = None,
	buffer_seconds: float = 4.0,
) -> dict:
	opts = {
		"outtmpl": str(output_dir / "%(playlist_title|uploader)s" / "%(title)s.%(ext)s"),
		"format": "best[ext=mp4]/best",
		"merge_output_format": "mp4",
		"noplaylist": single,
		"ignoreerrors": True,
		"restrictfilenames": False,
		"js_runtimes": {"node": None, "deno": None},
	}
	if buffer_seconds > 0:
		# Add jitter so repeated playlist requests do not look machine-perfect.
		opts["sleep_interval"] = buffer_seconds
		opts["max_sleep_interval"] = buffer_seconds + 2
	if cookie_browser:
		opts["cookiesfrombrowser"] = (cookie_browser,)
	return opts


def download_with_fallback(
	download_url: str,
	output_dir: Path,
	single: bool,
	buffer_seconds: float = 4.0,
) -> None:
	"""Download with youtube options that reduce bot/sign-in failures."""
	attempt_order = _cookie_attempt_order()
	last_error: BaseException | None = None

	for browser in attempt_order:
		ydl_opts = build_ydl_options(
			output_dir=output_dir,
			single=single,
			cookie_browser=browser,
			buffer_seconds=buffer_seconds,
		)
		try:
			with yt_dlp.YoutubeDL(ydl_opts) as ydl:
				ydl.download([download_url])
			return
		except BaseException as exc:  # noqa: BLE001
			if isinstance(exc, KeyboardInterrupt):
				raise
			last_error = exc
			continue

	if last_error:
		message = str(last_error)
		if "NoneType" in message and "object has no attribute 'get'" in message:
			raise RuntimeError(
				"yt-dlp hit a YouTube extractor failure. Try a manual cookies.txt file with --cookies, "
				"or test a different video URL/account session."
			) from last_error
		raise last_error

	raise RuntimeError("YouTube download failed for an unknown reason.")


def main() -> None:
	args = parse_args()
	args.output_dir.mkdir(parents=True, exist_ok=True)
	download_url = resolve_download_url(args.url, args.single)
	download_with_fallback(
		download_url=download_url,
		output_dir=args.output_dir,
		single=args.single,
		buffer_seconds=args.buffer_seconds,
	)


if __name__ == "__main__":
	main()
