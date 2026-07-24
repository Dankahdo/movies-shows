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
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yt_dlp


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
		default=Path("downloads"),
		help="Directory to save files (default: downloads).",
	)
	parser.add_argument(
		"--single",
		action="store_true",
		help="Only download one video, even if URL points to a playlist.",
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


def main() -> None:
	args = parse_args()
	args.output_dir.mkdir(parents=True, exist_ok=True)
	download_url = resolve_download_url(args.url, args.single)

	ydl_opts = {
		"outtmpl": str(args.output_dir / "%(playlist_title|uploader)s" / "%(title)s.%(ext)s"),
		"format": "best[ext=mp4]/best",
		"merge_output_format": "mp4",
		"noplaylist": args.single,
		"ignoreerrors": True,
		"restrictfilenames": False,
	}

	with yt_dlp.YoutubeDL(ydl_opts) as ydl:
		ydl.download([download_url])


if __name__ == "__main__":
	main()
