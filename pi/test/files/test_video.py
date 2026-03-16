"""Unit tests for VideoFile."""

import csv

import cv2
import numpy as np
import pytest
from polyumi_pi.files.video import VideoFile

WIDTH = 64
HEIGHT = 48
FPS = 10.0


def make_jpeg(width: int = WIDTH, height: int = HEIGHT) -> bytes:
    """Return a minimal valid JPEG-encoded BGR frame."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    ok, buf = cv2.imencode('.jpg', frame)
    assert ok
    return buf.tobytes()


@pytest.fixture
def video_file(tmp_path):
    """Return a VideoFile instance pointing at a temp directory."""
    return VideoFile(
        path=tmp_path / 'video',
        fps=FPS,
        width=WIDTH,
        height=HEIGHT,
    )


# ---------------------------------------------------------------------------
# Construction / timestamps_path
# ---------------------------------------------------------------------------


def test_timestamps_path_default(tmp_path):
    """timestamps_path is always the sidecar CSV in the frame directory."""
    vf = VideoFile(path=tmp_path / 'video', fps=FPS, width=WIDTH, height=HEIGHT)
    assert vf.timestamps_path == tmp_path / 'video' / 'video_timestamps.csv'


# ---------------------------------------------------------------------------
# recording() context manager
# ---------------------------------------------------------------------------


def test_recording_creates_files(video_file, tmp_path):
    """recording() creates frame dir and timestamps CSV sidecar."""
    with video_file.recording():
        pass

    assert (tmp_path / 'video').is_dir()
    assert (tmp_path / 'video' / 'video_timestamps.csv').is_file()


def test_recording_cleans_up_state(video_file):
    """Internal timestamp writer references are None after context exits."""
    with video_file.recording():
        pass

    assert video_file._timestamps_fp is None
    assert video_file._timestamps_writer is None


def test_recording_reentrant_raises(video_file):
    """Opening a second recording() context while one is active raises."""
    with video_file.recording():
        with pytest.raises(RuntimeError, match='already active'):
            with video_file.recording():
                pass


# ---------------------------------------------------------------------------
# write_frame()
# ---------------------------------------------------------------------------


def test_write_frame_outside_context_raises(video_file):
    """write_frame() outside recording() raises RuntimeError."""
    with pytest.raises(RuntimeError, match='not active'):
        video_file.write_frame(make_jpeg())


def test_write_frame_increments_index(video_file):
    """Frame index increments with each write_frame() call."""
    with video_file.recording() as vf:
        assert vf._frame_idx == 0
        vf.write_frame(make_jpeg())
        assert vf._frame_idx == 1
        vf.write_frame(make_jpeg())
        assert vf._frame_idx == 2


def test_write_frame_timestamps_csv(video_file, tmp_path):
    """Each write_frame() appends one row with correct frame index to the CSV."""
    ts_values = [1_000_000_000, 2_000_000_000, 3_000_000_000]
    with video_file.recording() as vf:
        for ts in ts_values:
            vf.write_frame(make_jpeg(), timestamp_ns_value=ts)

    rows = list(csv.reader((tmp_path / 'video' / 'video_timestamps.csv').open()))
    assert len(rows) == 3
    for i, (row, ts) in enumerate(zip(rows, ts_values)):
        assert int(row[0]) == i
        assert int(row[1]) == ts


def test_write_frame_creates_jpeg_files(video_file, tmp_path):
    """Each write_frame() writes one raw JPEG file with sequential naming."""
    jpg = make_jpeg()
    with video_file.recording() as vf:
        vf.write_frame(jpg)
        vf.write_frame(jpg)

    assert (tmp_path / 'video' / 'frame_000000.jpg').is_file()
    assert (tmp_path / 'video' / 'frame_000001.jpg').is_file()
    assert (tmp_path / 'video' / 'frame_000000.jpg').read_bytes() == jpg


def test_write_frame_uses_time_ns_when_no_timestamp(video_file):
    """write_frame() records a plausible ns timestamp when none is supplied."""
    from time import time_ns

    before = time_ns()
    with video_file.recording() as vf:
        vf.write_frame(make_jpeg())
    after = time_ns()

    rows = list(csv.reader(video_file.timestamps_path.open()))
    ts = int(rows[0][1])
    assert before <= ts <= after


# ---------------------------------------------------------------------------
# from_file() round-trip
# ---------------------------------------------------------------------------


def test_from_file_roundtrip(video_file, tmp_path):
    """from_file() recovers width/height from first frame in directory."""
    with video_file.recording() as vf:
        vf.write_frame(make_jpeg())

    loaded = VideoFile.from_file(tmp_path / 'video')

    assert loaded.fps == 0.0
    assert loaded.width == WIDTH
    assert loaded.height == HEIGHT


def test_from_file_raises_for_empty_directory(tmp_path):
    """from_file() rejects frame directories with no JPEG files."""
    path = tmp_path / 'video'
    path.mkdir()

    with pytest.raises(ValueError, match='No JPEG frames found'):
        VideoFile.from_file(path)
