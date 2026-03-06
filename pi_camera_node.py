#!/usr/bin/env python3
"""
ROS 2 Jazzy - Pi Camera TCP Receiver Node
Connects to the Pi streamer and publishes sensor_msgs/Image on /pi_camera/image_raw.

Dependencies:
    sudo apt install ros-jazzy-cv-bridge python3-opencv

Usage (after building your package):
    ros2 run pi_camera_ros pi_camera_node --ros-args \
        -p pi_host:=<PI_IP> -p pi_port:=5000

Or run standalone (no colcon build needed):
    python3 pi_camera_node.py
"""

import io
import socket
import struct
import threading

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image


class PiCameraNode(Node):
    def __init__(self):
        super().__init__("pi_camera_node")

        # ---------- Parameters ----------
        self.declare_parameter("pi_host", "raspberrypi.local")
        self.declare_parameter("pi_port", 5000)
        self.declare_parameter("topic", "/pi_camera/image_raw")
        self.declare_parameter(
            "reconnect_delay", 2.0
        )  # seconds between reconnect attempts

        self.pi_host = self.get_parameter("pi_host").get_parameter_value().string_value
        self.pi_port = self.get_parameter("pi_port").get_parameter_value().integer_value
        topic = self.get_parameter("topic").get_parameter_value().string_value
        self.reconnect_delay = (
            self.get_parameter("reconnect_delay").get_parameter_value().double_value
        )

        # ---------- ROS interfaces ----------
        self.publisher_ = self.create_publisher(
            Image, topic, 1
        )  # QoS depth=1 keeps only latest
        self.bridge = CvBridge()

        self.get_logger().info(
            f"Pi Camera Node started. Connecting to tcp://{self.pi_host}:{self.pi_port}"
        )
        self.get_logger().info(f"Publishing on: {topic}")

        # ---------- Receiver thread ----------
        self._running = True
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Receive loop (runs in background thread)
    # ------------------------------------------------------------------

    def _receive_loop(self):
        while self._running:
            try:
                self._connect_and_stream()
            except Exception as e:
                if self._running:
                    self.get_logger().warn(
                        f"Stream error: {e}. Reconnecting in {self.reconnect_delay}s..."
                    )
                    import time

                    time.sleep(self.reconnect_delay)

    def _connect_and_stream(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.settimeout(5.0)
            sock.connect((self.pi_host, self.pi_port))
            self.get_logger().info("Connected to Pi camera stream.")
            sock.settimeout(None)  # Block on recv after connect

            while self._running:
                # Read the 4-byte length header
                raw_len = self._recvall(sock, 4)
                if raw_len is None:
                    raise ConnectionError("Stream closed by Pi.")
                frame_len = struct.unpack(">I", raw_len)[0]

                # Read the JPEG frame
                raw_frame = self._recvall(sock, frame_len)
                if raw_frame is None:
                    raise ConnectionError("Incomplete frame received.")

                self._publish_frame(raw_frame)

    def _recvall(self, sock: socket.socket, n: int) -> bytes | None:
        """Receive exactly n bytes from socket."""
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    # ------------------------------------------------------------------
    # Frame → ROS message
    # ------------------------------------------------------------------

    def _publish_frame(self, jpeg_bytes: bytes):
        # Decode JPEG → BGR numpy array
        arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            self.get_logger().warn("Failed to decode JPEG frame — skipping.")
            return

        # Convert BGR → ROS Image (bgr8 encoding matches OpenCV default)
        msg = self.bridge.cv2_to_imgmsg(frame, encoding="bgr8")
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "pi_camera"
        self.publisher_.publish(msg)

    # ------------------------------------------------------------------

    def destroy_node(self):
        self._running = False
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = PiCameraNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
