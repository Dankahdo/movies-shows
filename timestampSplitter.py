#!/usr/bin/env python3
"""Split a single media file into episode files using a timestamp list.

Usage example:
  py timestampSplitter --input "all_episodes.mp4" --timestamps "starts.txt" --output-dir "episodes"

Timestamp list lines can be inconsistent in wording. The script uses only the
timestamp token and ignores the rest, for example:
  S1 E1 "I, Duckman" 0:37
  S1 E2 "TV or Not To Be" 23:19
  S1 E3 "Gripes of Wrath" 46:01
  S1 E4 "Psyche" 1:08:45
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


TIMESTAMP_PATTERN = re.compile(r"\b(?:\d{1,2}:)?\d{1,2}:\d{2}\b")


@dataclass
class SegmentMark:
	index: int
	label: str
	timestamp_raw: str
	seconds: float


def parse_timestamp_to_seconds(ts: str) -> float:
	parts = [int(p) for p in ts.split(":")]
	if len(parts) == 2:
		minutes, seconds = parts
		return float(minutes * 60 + seconds)
	if len(parts) == 3:
		hours, minutes, seconds = parts
		return float(hours * 3600 + minutes * 60 + seconds)
	raise ValueError(f"Invalid timestamp: {ts}")


def seconds_to_ffmpeg_time(total_seconds: float) -> str:
	whole = int(total_seconds)
	hours = whole // 3600
	minutes = (whole % 3600) // 60
	seconds = whole % 60
	return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def sanitize_filename(value: str) -> str:
	value = re.sub(r"[\\/:*?\"<>|]", "", value)
	value = re.sub(r"\s+", " ", value).strip()
	return value or "episode"


def parse_marks(timestamp_file: Path) -> list[SegmentMark]:
	marks: list[SegmentMark] = []
	lines = timestamp_file.read_text(encoding="utf-8", errors="replace").splitlines()

	for i, line in enumerate(lines, start=1):
		matches = list(TIMESTAMP_PATTERN.finditer(line))
		if not matches:
			continue

		# Prefer the last timestamp token on the line.
		match = matches[-1]
		ts = match.group(0)
		prefix = line[: match.start()].strip()
		label = prefix if prefix else f"Episode {len(marks) + 1}"
		marks.append(
			SegmentMark(
				index=len(marks) + 1,
				label=label,
				timestamp_raw=ts,
				seconds=parse_timestamp_to_seconds(ts),
			)
		)

	if not marks:
		raise ValueError("No valid timestamps found in the timestamp list file.")

	for prev, curr in zip(marks, marks[1:]):
		if curr.seconds <= prev.seconds:
			raise ValueError(
				"Timestamps must be strictly increasing. "
				f"Found {curr.timestamp_raw} after {prev.timestamp_raw}."
			)

	return marks


def _build_ffmpeg_missing_message(binary_name: str) -> str:
	return (
		f"{binary_name} is required but was not found.\n"
		"Install FFmpeg and either:\n"
		"1) Add its bin folder to PATH, or\n"
		"2) Set FFMPEG_BIN to that bin folder, or\n"
		"3) Pass --ffmpeg-bin with that bin folder path.\n"
		"Windows quick install (winget): winget install Gyan.FFmpeg"
	)


def resolve_ffmpeg_binary(binary_name: str, ffmpeg_bin: Path | None = None) -> str:
	# Priority: explicit --ffmpeg-bin, FFMPEG_BIN env var, then PATH.
	if ffmpeg_bin:
		candidate = ffmpeg_bin / binary_name
		if candidate.exists():
			return str(candidate)

	env_bin = os.environ.get("FFMPEG_BIN")
	if env_bin:
		candidate = Path(env_bin) / binary_name
		if candidate.exists():
			return str(candidate)

	found = shutil.which(Path(binary_name).stem)
	if found:
		return found

	raise RuntimeError(_build_ffmpeg_missing_message(binary_name))


def get_media_duration_seconds(input_file: Path, ffmpeg_bin: Path | None = None) -> float:
	ffprobe = resolve_ffmpeg_binary("ffprobe.exe" if os.name == "nt" else "ffprobe", ffmpeg_bin)

	cmd = [
		ffprobe,
		"-v",
		"error",
		"-show_entries",
		"format=duration",
		"-of",
		"default=noprint_wrappers=1:nokey=1",
		str(input_file),
	]
	result = subprocess.run(cmd, capture_output=True, text=True, check=True)
	return float(result.stdout.strip())


def run_ffmpeg_split(
	input_file: Path,
	output_file: Path,
	start_seconds: float,
	end_seconds: float,
	reencode: bool,
	ffmpeg_bin: Path | None = None,
) -> None:
	ffmpeg = resolve_ffmpeg_binary("ffmpeg.exe" if os.name == "nt" else "ffmpeg", ffmpeg_bin)

	cmd = [
		ffmpeg,
		"-y",
		"-hide_banner",
		"-loglevel",
		"error",
		"-ss",
		seconds_to_ffmpeg_time(start_seconds),
		"-to",
		seconds_to_ffmpeg_time(end_seconds),
		"-i",
		str(input_file),
	]

	if reencode:
		cmd.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k"])
	else:
		cmd.extend(["-c", "copy"])

	cmd.append(str(output_file))
	subprocess.run(cmd, check=True)


def build_output_name(mark: SegmentMark, extension: str) -> str:
	label = sanitize_filename(mark.label)
	return f"{label}{extension}"


def split_media(
	input_file: Path,
	timestamp_file: Path,
	output_dir: Path,
	reencode: bool,
	ffmpeg_bin: Path | None,
) -> None:
	if not input_file.exists():
		raise FileNotFoundError(f"Input file not found: {input_file}")
	if not timestamp_file.exists():
		raise FileNotFoundError(f"Timestamp file not found: {timestamp_file}")

	marks = parse_marks(timestamp_file)
	total_duration = get_media_duration_seconds(input_file, ffmpeg_bin)
	output_dir.mkdir(parents=True, exist_ok=True)
	extension = input_file.suffix or ".mp4"

	print(f"Found {len(marks)} episode start marks.")
	print(f"Input duration: {seconds_to_ffmpeg_time(total_duration)}")

	for idx, mark in enumerate(marks):
		next_start = marks[idx + 1].seconds if idx + 1 < len(marks) else total_duration
		if next_start <= mark.seconds:
			raise ValueError(
				f"Invalid segment range for mark {mark.index}: start >= end ({mark.timestamp_raw})"
			)

		output_name = build_output_name(mark, extension)
		output_file = output_dir / output_name

		print(
			f"[{mark.index}/{len(marks)}] {output_name}: "
			f"{seconds_to_ffmpeg_time(mark.seconds)} -> {seconds_to_ffmpeg_time(next_start)}"
		)
		run_ffmpeg_split(
			input_file=input_file,
			output_file=output_file,
			start_seconds=mark.seconds,
			end_seconds=next_start,
			reencode=reencode,
			ffmpeg_bin=ffmpeg_bin,
		)

	print(f"Done. Split files written to: {output_dir}")


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description="Split one large media file into episodes using start timestamps."
	)
	parser.add_argument("--input", required=True, type=Path, help="Path to large media file")
	parser.add_argument(
		"--timestamps",
		required=True,
		type=Path,
		help="Path to text file with episode lines containing timestamps",
	)
	parser.add_argument(
		"--output-dir",
		default=Path("split_output"),
		type=Path,
		help="Directory where split episode files are written",
	)
	parser.add_argument(
		"--reencode",
		action="store_true",
		help="Re-encode output for frame-accurate boundaries (slower, larger CPU use)",
	)
	parser.add_argument(
		"--ffmpeg-bin",
		type=Path,
		help="Path to ffmpeg bin folder containing ffmpeg/ffprobe",
	)
	return parser


def main() -> int:
	args = build_parser().parse_args()
	try:
		split_media(
			input_file=args.input,
			timestamp_file=args.timestamps,
			output_dir=args.output_dir,
			reencode=args.reencode,
				ffmpeg_bin=args.ffmpeg_bin,
		)
	except Exception as exc:
		print(f"Error: {exc}", file=sys.stderr)
		return 1
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
