#!/usr/bin/env python3
"""
Pi Camera Module 3 - TCP MJPEG Streamer
Run this on the Raspberry Pi Zero 2W.

Install deps:
    sudo apt install python3-picamera2

Usage:
    python3 pi_camera_streamer.py [--host 0.0.0.0] [--port 5000] [--width 640] [--height 480] [--fps 30]
"""

import argparse
import io
import socket
import struct
import time
import threading
import sys

from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput


class TCPStreamOutput(io.BufferedIOBase):
    """Buffers the latest MJPEG frame and broadcasts it to a connected client."""

    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


def stream_to_client(conn, output: TCPStreamOutput):
    """Send frames to a single connected client until disconnect."""
    print(f"[streamer] Client connected: {conn.getpeername()}")
    try:
        while True:
            with output.condition:
                output.condition.wait()
                frame = output.frame

            # Prefix each frame with a 4-byte length header so the receiver
            # can reliably reconstruct frames from the TCP byte stream.
            size = struct.pack(">I", len(frame))
            conn.sendall(size + frame)
    except (BrokenPipeError, ConnectionResetError, OSError):
        print("[streamer] Client disconnected.")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Pi Camera 3 TCP MJPEG Streamer")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=5000, help="TCP port (default: 5000)"
    )
    parser.add_argument(
        "--width", type=int, default=640, help="Frame width (default: 640)"
    )
    parser.add_argument(
        "--height", type=int, default=480, help="Frame height (default: 480)"
    )
    parser.add_argument(
        "--fps", type=int, default=30, help="Target framerate (default: 30)"
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="Camera index to open (default: 0)",
    )
    args = parser.parse_args()

    try:
        cameras = Picamera2.global_camera_info()
    except Exception as exc:
        print(f"[streamer] Failed to query cameras: {exc}", file=sys.stderr)
        print(
            "[streamer] Ensure libcamera is installed and the camera subsystem is enabled.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not cameras:
        print("[streamer] No cameras detected.", file=sys.stderr)
        print(
            "[streamer] Check ribbon cable seating, enable camera support in raspi-config, and reboot.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.camera_index < 0 or args.camera_index >= len(cameras):
        print(
            f"[streamer] Invalid --camera-index {args.camera_index}. "
            f"Detected camera indexes: 0..{len(cameras) - 1}",
            file=sys.stderr,
        )
        for idx, cam in enumerate(cameras):
            print(f"[streamer]   index={idx} info={cam}", file=sys.stderr)
        sys.exit(1)

    print(
        f"[streamer] Using camera index {args.camera_index}: {cameras[args.camera_index]}"
    )

    try:
        picam2 = Picamera2(args.camera_index)
    except Exception as exc:
        print(
            f"[streamer] Failed to open camera index {args.camera_index}: {exc}",
            file=sys.stderr,
        )
        print(
            "[streamer] If another process is using the camera, stop it and try again.",
            file=sys.stderr,
        )
        sys.exit(1)

    config = picam2.create_video_configuration(
        main={"size": (args.width, args.height), "format": "RGB888"},
        controls={"FrameRate": args.fps},
        buffer_count=2,  # Minimise buffering for low latency
    )
    picam2.configure(config)

    output = TCPStreamOutput()
    encoder = MJPEGEncoder()  # MJPEGEncoder doesn't take quality param
    picam2.start_recording(encoder, FileOutput(output))
    print(f"[streamer] Camera started at {args.width}x{args.height} @ {args.fps} fps")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(1)
    print(
        f"[streamer] Listening on {args.host}:{args.port} — waiting for ROS 2 node..."
    )

    try:
        while True:
            conn, _ = server.accept()
            # Disable Nagle's algorithm to flush small packets immediately
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            t = threading.Thread(
                target=stream_to_client, args=(conn, output), daemon=True
            )
            t.start()
    except KeyboardInterrupt:
        print("[streamer] Shutting down.")
    finally:
        picam2.stop_recording()
        server.close()


if __name__ == "__main__":
    main()
