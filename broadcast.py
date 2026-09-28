#!/usr/bin/env python3
"""BroadcastTV - Simulate broadcast television from your local video collection.

Scans the 'show series/' folder for series organized as:
  show series/<Series Name>/<Season Folder>/<episode file>

Generates an M3U playlist where series rotate randomly but each plays
episodes in sequential order with no repeats. Progress is saved so the
next run continues from where you left off.

Usage:
  py broadcast.py                          # Generate a playlist (default 30 slots)
  py broadcast.py --episodes 20            # 20 episode slots
  py broadcast.py --include-movies         # Interleave movies from movies/
  py broadcast.py --movie-every 5          # Insert a movie every N episodes (default 8)
  py broadcast.py --output my_night.m3u   # Custom output filename
  py broadcast.py --status                 # Show current progress per series
  py broadcast.py --reset                  # Reset ALL progress
  py broadcast.py --reset "Duckman"        # Reset a specific series
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (relative to this script's location)
# ---------------------------------------------------------------------------
BASE_DIR       = Path(__file__).parent
DATA_DIR       = BASE_DIR / "data"
OUTPUT_DIR     = BASE_DIR / "output"
SHOWS_DIR      = BASE_DIR / "show series"
MOVIES_DIR     = BASE_DIR / "movies"
STATE_FILE     = DATA_DIR / "broadcast_state.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "broadcast_playlist.m3u"

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".flv", ".webm"}


# ---------------------------------------------------------------------------
# Natural sort so "Episode 10" comes after "Episode 9"
# ---------------------------------------------------------------------------
def _natural_key(text: str) -> list:
    parts = re.split(r"(\d+)", text)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------
def scan_episodes(show_dir: Path) -> list[Path]:
    """Return all video files under a show folder, sorted naturally across seasons."""
    episodes: list[Path] = []
    for root, dirs, files in os.walk(show_dir):
        dirs.sort(key=lambda d: _natural_key(d))  # consistent season ordering
        for f in sorted(files, key=lambda x: _natural_key(x)):
            if Path(f).suffix.lower() in VIDEO_EXTENSIONS:
                episodes.append(Path(root) / f)
    return episodes


def scan_all_shows(shows_dir: Path) -> dict[str, list[Path]]:
    """Return {show_name: [episode_paths...]} for all shows found."""
    shows: dict[str, list[Path]] = {}
    if not shows_dir.exists():
        return shows
    for entry in sorted(shows_dir.iterdir(), key=lambda p: _natural_key(p.name)):
        if entry.is_dir():
            eps = scan_episodes(entry)
            if eps:
                shows[entry.name] = eps
    return shows


def scan_movies(movies_dir: Path) -> list[Path]:
    """Return all video files directly in the movies folder."""
    if not movies_dir.exists():
        return []
    return sorted(
        [f for f in movies_dir.iterdir() if f.suffix.lower() in VIDEO_EXTENSIONS],
        key=lambda p: _natural_key(p.name),
    )


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass
    return {"shows": {}, "movies_seen": [], "movie_cycle": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Playlist generation
# ---------------------------------------------------------------------------
def build_playlist(
    shows: dict[str, list[Path]],
    all_movies: list[Path],
    state: dict,
    num_slots: int,
    include_movies: bool,
    movie_every: int,
) -> list[Path]:
    """
    Generate an ordered list of video files simulating a broadcast schedule.

    The schedule works in *cycles*: each cycle shuffles the active show names,
    then pulls the next unwatched episode from each show in that shuffled order.
    This means you never see the same show twice in a row within a cycle and the
    overall order is unpredictable – just like broadcast TV.
    """
    show_state: dict[str, int] = state.get("shows", {})
    movies_seen: set[str] = set(state.get("movies_seen", []))
    movie_cycle: list[str] = state.get("movie_cycle", [])

    playlist: list[Path] = []
    episode_count = 0  # tracks episodes only (not movies) for movie insertion

    # Active shows = shows that still have unseen episodes
    active_shows = [
        name for name, eps in shows.items()
        if show_state.get(name, 0) < len(eps)
    ]

    if not active_shows:
        print("All episodes in every series have been watched! Use --reset to start over.")
        return []

    # We iterate cycles until we've filled num_slots or exhausted all episodes
    cycle_order: list[str] = []

    while len(playlist) < num_slots:
        # Refresh active list (a show may have been exhausted mid-cycle)
        active_shows = [
            name for name, eps in shows.items()
            if show_state.get(name, 0) < len(eps)
        ]
        if not active_shows:
            break

        # Start a new cycle when the current one is empty
        if not cycle_order:
            cycle_order = active_shows[:]
            random.shuffle(cycle_order)

        show_name = cycle_order.pop(0)

        # Skip if show was exhausted since cycle was built
        if show_state.get(show_name, 0) >= len(shows[show_name]):
            continue

        ep_index = show_state.get(show_name, 0)
        episode = shows[show_name][ep_index]
        playlist.append(episode)
        show_state[show_name] = ep_index + 1
        episode_count += 1

        # Optionally insert a movie every movie_every episodes
        if include_movies and all_movies and episode_count % movie_every == 0:
            # Build a fresh movie cycle when exhausted
            remaining_movies = [str(m) for m in all_movies if str(m) not in movies_seen]
            if not remaining_movies:
                # All movies seen – start a fresh round
                movies_seen.clear()
                remaining_movies = [str(m) for m in all_movies]
            if not movie_cycle:
                movie_cycle = remaining_movies[:]
                random.shuffle(movie_cycle)
            movie_path_str = movie_cycle.pop(0)
            movies_seen.add(movie_path_str)
            playlist.append(Path(movie_path_str))

    # Persist updated state
    state["shows"] = show_state
    state["movies_seen"] = list(movies_seen)
    state["movie_cycle"] = movie_cycle
    return playlist


# ---------------------------------------------------------------------------
# M3U output
# ---------------------------------------------------------------------------
def write_m3u(playlist: list[Path], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as fh:
        fh.write("#EXTM3U\n")
        for path in playlist:
            fh.write(f"#EXTINF:-1,{path.stem}\n")
            fh.write(f"{path}\n")


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------
def print_status(shows: dict[str, list[Path]], state: dict) -> None:
    show_state = state.get("shows", {})
    print(f"\n{'Series':<35} {'Watched':>8} {'Total':>7} {'Remaining':>10}")
    print("-" * 64)
    grand_watched = grand_total = 0
    for name, eps in shows.items():
        total = len(eps)
        watched = show_state.get(name, 0)
        remaining = total - watched
        flag = " [DONE]" if remaining == 0 else ""
        print(f"{name:<35} {watched:>8} {total:>7} {remaining:>10}{flag}")
        grand_watched += watched
        grand_total += total
    print("-" * 64)
    print(f"{'TOTAL':<35} {grand_watched:>8} {grand_total:>7} {grand_total - grand_watched:>10}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a broadcast-style M3U playlist from your video collection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--episodes", type=int, default=30, metavar="N",
        help="Number of episode slots to add to the playlist (default: 30).",
    )
    parser.add_argument(
        "--include-movies", action="store_true",
        help="Interleave movies from the movies/ folder into the playlist.",
    )
    parser.add_argument(
        "--movie-every", type=int, default=8, metavar="N",
        help="Insert a movie every N episodes when --include-movies is set (default: 8).",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, metavar="FILE",
        help=f"Output M3U filename (default: {DEFAULT_OUTPUT.name}).",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Print current watch progress per series and exit.",
    )
    parser.add_argument(
        "--reset", nargs="?", const="__ALL__", metavar="SERIES",
        help="Reset watch progress. Omit SERIES to reset everything.",
    )
    args = parser.parse_args()

    # Scan collection
    shows = scan_all_shows(SHOWS_DIR)
    movies = scan_movies(MOVIES_DIR)

    if not shows and not args.status:
        print(f"No shows found in '{SHOWS_DIR}'. Nothing to do.")
        sys.exit(1)

    state = load_state()

    # --reset
    if args.reset is not None:
        if args.reset == "__ALL__":
            state["shows"] = {}
            state["movies_seen"] = []
            state["movie_cycle"] = []
            save_state(state)
            print("Progress reset for all series and movies.")
        else:
            matched = [n for n in shows if n.lower() == args.reset.lower()]
            if not matched:
                # Fuzzy: partial match
                matched = [n for n in shows if args.reset.lower() in n.lower()]
            if not matched:
                print(f"No series matching '{args.reset}' found.")
                sys.exit(1)
            for name in matched:
                state.setdefault("shows", {})[name] = 0
                print(f"Progress reset for: {name}")
            save_state(state)
        return

    # --status
    if args.status:
        print_status(shows, state)
        return

    # Generate playlist
    playlist = build_playlist(
        shows=shows,
        all_movies=movies,
        state=state,
        num_slots=args.episodes,
        include_movies=args.include_movies,
        movie_every=args.movie_every,
    )

    if not playlist:
        return

    write_m3u(playlist, args.output)
    save_state(state)

    episode_entries = [p for p in playlist if p.parent.parent.parent == SHOWS_DIR or
                       any(p.is_relative_to(SHOWS_DIR / s) for s in shows)]
    movie_entries = len(playlist) - len(episode_entries)

    print(f"Playlist written to: {args.output}")
    print(f"  {len(playlist)} entries total  ({len(episode_entries)} episodes"
          + (f", {movie_entries} movies" if movie_entries else "") + ")")
    print(f"\nOpen '{args.output.name}' in VLC (or any media player) to start watching.")
    print("Run this script again when the playlist ends to continue where you left off.")


if __name__ == "__main__":
    main()
