# BroadcastTV Playlist Generator

BroadcastTV is a local-media scheduling script that simulates a classic broadcast TV experience from your own video files.

It scans your show library, keeps per-series progress, and generates an M3U playlist where series rotation feels varied while episode order stays consistent within each show.

## Project Purpose

This project is designed to:

- Turn a folder of TV episodes into a ready-to-play "broadcast style" queue.
- Avoid manual episode picking.
- Preserve continuity between runs, so playback can resume naturally.
- Optionally blend movies into the episode stream at a chosen interval.

## Current Scope

The current implementation is focused on one core workflow: scan library -> build playlist -> save progress.

### Included Today

- Recursive show scanning under show series/<Series>/<Season>/<Episode files>.
- Natural sorting for names with numbers (for example, Episode 2 before Episode 10).
- Sequential episode progression per show with no repeats until each show is exhausted.
- Randomized per-cycle show order to keep variety in series rotation.
- Optional movie interleaving from the top-level movies folder.
- Persistent state in broadcast_state.json:
  - Per-show watched index.
  - Seen movies list.
  - Movie cycle ordering.
- M3U output generation to broadcast_playlist.m3u by default.
- Command-line controls for status, reset, output name, episode count, and movie cadence.

### Not Included Yet

- Playback control (the script does not launch or control VLC/player behavior).
- Rich metadata (titles, posters, runtimes, descriptions).
- Time-based scheduling (real clock channels or fixed air times).
- Multi-profile/user watch state.
- Recursive movie scanning in subfolders.
- Duplicate detection and automatic file validation beyond extension filtering.

## Folder Expectations

The script expects this layout at the project root:

- broadcast.py
- show series/
  - Any number of series folders
  - Optional season subfolders
  - Video files in supported formats
- movies/
  - Movie video files at top level

Supported video extensions:

- .mp4
- .mkv
- .avi
- .mov
- .wmv
- .m4v
- .flv
- .webm

## State and Output Files

Generated and maintained files:

- broadcast_state.json
  - Stores progress and movie tracking across runs.
- broadcast_playlist.m3u
  - Latest generated playlist unless a custom output path is provided.

## CLI Usage

Run from the project root:

    py broadcast.py

Common commands:

    py broadcast.py --episodes 20
    py broadcast.py --include-movies
    py broadcast.py --include-movies --movie-every 5
    py broadcast.py --output my_night.m3u
    py broadcast.py --status
    py broadcast.py --reset
    py broadcast.py --reset Duckman

## How Playlist Generation Works

1. Scan all eligible series and episodes.
2. Load saved state from broadcast_state.json.
3. Build rotating show cycles:
   - Shuffle active shows for a cycle.
   - Pull one next episode per show in that cycle order.
4. Insert movies every N episodes when enabled.
5. Save updated state.
6. Write M3U playlist.

This produces variety across shows while preserving each show's episode order.

## Notes and Edge Cases

- If all episodes are exhausted, the script reports completion and exits.
- If all movies have been inserted once, the movie seen list is cleared and a fresh movie round begins.
- If a reset series name does not match exactly, the script attempts partial-name matching.

## Project Summary

BroadcastTV currently provides a practical, lightweight personal "TV channel" generator for local files.

Its present scope is intentionally focused: stable folder scanning, repeat-safe progress tracking, and consistent playlist output. This makes it easy to run regularly while leaving room for future features such as richer metadata, channel presets, and time-aware scheduling.

## Desktop Application

A desktop app is now included at `media_center_app.py`.

It provides:

- Native Windows media playback through Qt Multimedia backend.
- Arrow key skipping (left/right) with a configurable default of 5 seconds.
- Autoplay queue behavior with optional loop.
- Tabs for Home, Library, Broadcast, Tools, and Settings.
- Home tab showing recently viewed files.
- Library tab with search, movies/shows filter, and in-app playback.
- Per-item user review notes and a 0-5 rating.
- Broadcast tab that reuses `broadcast.py` logic and supports include/exclude lists for shows and movies.
- Tools tab for YouTube ripping (`RipYoutube.py` behavior) and timestamp splitting (`timestampSplitter.py` behavior).

### Run the App

From the project root:

  .\venv\Scripts\python.exe -m pip install -r requirements.txt
  .\venv\Scripts\python.exe media_center_app.py

Or use:

  .\run_media_center.ps1

### Build Executable (Windows)

Use:

  .\build_exe.ps1

This builds a windowed executable with PyInstaller at:

- `dist\LocalMediaCenter\LocalMediaCenter.exe`
