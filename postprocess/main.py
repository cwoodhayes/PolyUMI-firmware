"""
postprocess/main.py - PolyUMI postprocessing scripts.

Usage:
    python main.py fetch --host conorpi
    python main.py fetch --host conorpi --latest
    python main.py process-video recordings/session_2024-01-01_12-00-00
"""

import logging
import os
import pathlib
import subprocess

import cv2
import numpy as np
import typer
from polyumi_pi.files.session import SessionFiles
from polyumi_pi.files.video import _FRAME_GLOB
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.prompt import Confirm

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
    format='%(message)s',
    handlers=[
        RichHandler(
            show_time=True,
            show_level=True,
            show_path=False,
            rich_tracebacks=True,
        )
    ],
)
log = logging.getLogger('postprocess')

app = typer.Typer()

DEFAULT_HOST = 'conorpi'
DEFAULT_RECORDINGS_DIR = pathlib.Path('recordings')
REMOTE_RECORDINGS_DIR = '~/recordings'
VIDEO_OUTPUT_NAME = 'finger.mp4'


def _rsync_session(
    host: str,
    remote_path: str,
    local_path: pathlib.Path,
) -> None:
    """Rsync a single session directory from the Pi to a local path."""
    local_path.mkdir(parents=True, exist_ok=True)
    cmd = [
        'rsync',
        '-av',
        '--progress',
        f'{host}:{remote_path}/',
        str(local_path) + '/',
    ]
    result = subprocess.run(cmd, check=True)
    if result.returncode != 0:
        raise RuntimeError(f'rsync failed for {remote_path}')


def _list_remote_sessions(host: str) -> list[str]:
    """List session directory names on the Pi."""
    result = subprocess.run(
        ['ssh', host, f'ls {REMOTE_RECORDINGS_DIR}'],
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        name.strip()
        for name in result.stdout.splitlines()
        if name.strip().startswith('session_')
    ]


@app.command()
def fetch(
    host: str = typer.Option(DEFAULT_HOST, help='SSH hostname of the Pi.'),
    output_dir: pathlib.Path = typer.Option(
        DEFAULT_RECORDINGS_DIR,
        help='Local directory to write sessions into.',
    ),
    latest: bool = typer.Option(
        False,
        '--latest',
        help='Only fetch the latest session.',
    ),
):
    """Fetch recorded sessions from the Pi via rsync."""
    output_dir = output_dir.resolve()

    if latest:
        session_name_result = subprocess.run(
            ['ssh', host, f'readlink -f {REMOTE_RECORDINGS_DIR}/latest'],
            capture_output=True,
            text=True,
            check=True,
        )
        remote_session_path = session_name_result.stdout.strip()
        session_name = pathlib.Path(remote_session_path).name
        sessions_to_fetch = [session_name]
        log.info(f'Latest session: {session_name}')
    else:
        log.info(f'Listing sessions on {host}...')
        sessions_to_fetch = _list_remote_sessions(host)
        log.info(f'Found {len(sessions_to_fetch)} session(s) on {host}.')

    if not sessions_to_fetch:
        log.info('No sessions to fetch.')
        raise typer.Exit()

    # filter out already-fetched sessions
    to_fetch = []
    skipped = []
    for name in sessions_to_fetch:
        local_path = output_dir / name
        if local_path.exists():
            skipped.append(name)
        else:
            to_fetch.append(name)

    if skipped:
        log.info(f'Skipping {len(skipped)} already-fetched session(s).')

    if not to_fetch:
        log.info('Nothing new to fetch.')
        raise typer.Exit()

    log.info(f'{len(to_fetch)} session(s) to fetch into {output_dir}.')
    if not Confirm.ask('Proceed?', default=True):
        log.info('Aborted.')
        raise typer.Exit()

    output_dir.mkdir(parents=True, exist_ok=True)

    for i, session_name in enumerate(to_fetch, 1):
        remote_path = f'{REMOTE_RECORDINGS_DIR}/{session_name}'
        local_path = output_dir / session_name
        log.info(f'[{i}/{len(to_fetch)}] Fetching {session_name}...')
        _rsync_session(host, remote_path, local_path)
        log.info(f'  -> {local_path}')

    log.info(f'Done. Fetched {len(to_fetch)} session(s) to {output_dir}.')


@app.command()
def process_video(
    session_path: pathlib.Path = typer.Argument(
        ...,
        help='Path to a local session directory.',
    ),
    fps: float = typer.Option(
        10.0,
        help='Framerate to use for the output video. Overridden by session metadata if present.',
    ),
    output_name: str = typer.Option(
        VIDEO_OUTPUT_NAME,
        help='Output video filename (placed in the session directory).',
    ),
    include_audio: bool = typer.Option(
        True,
        help='Mux audio.wav into the output if present.',
    ),
):
    """Encode JPEG frames (and optionally audio) in a session directory into an MP4."""
    session_path = session_path.resolve()
    if not session_path.is_dir():
        log.error(f'Session directory not found: {session_path}')
        raise typer.Exit(1)

    video_dir = session_path / 'video'
    if not video_dir.is_dir():
        log.error(f'No video directory found at {video_dir}')
        raise typer.Exit(1)

    # prefer fps from session metadata if available
    metadata_path = session_path / 'metadata.json'
    if metadata_path.is_file():
        try:
            session = SessionFiles.from_file(session_path)
            if session.metadata.camera_fps is not None:
                fps = float(session.metadata.camera_fps)
                log.info(f'Using fps from metadata: {fps}')
        except Exception as e:
            log.warning(f'Could not load session metadata: {e}. Using --fps={fps}.')

    output_path = session_path / output_name
    audio_path = session_path / 'audio.wav'
    has_audio = include_audio and audio_path.is_file()

    # build ffmpeg command
    cmd = [
        'ffmpeg',
        '-y',  # overwrite output without asking
        '-framerate',
        str(fps),
        '-i',
        str(video_dir / 'frame_%06d.jpg'),
    ]

    if has_audio:
        cmd += ['-i', str(audio_path)]

    cmd += [
        '-c:v',
        'libx264',
        '-pix_fmt',
        'yuv420p',  # broadest playback compatibility
    ]

    if has_audio:
        cmd += ['-c:a', 'aac']

    cmd.append(str(output_path))

    log.info(f'Encoding: {" ".join(cmd)}')
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        log.error(f'ffmpeg exited with code {result.returncode}')
        raise typer.Exit(result.returncode)

    log.info(f'Video written to {output_path}')


if __name__ == '__main__':
    app()
