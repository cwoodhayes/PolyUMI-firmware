"""Stream video from the gopro to Connect."""

import logging
import time

import connect_python
import cv2

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('polyumi_connect')


@connect_python.main
def stream_data(client: connect_python.Client):
    """Stream video data from GoPro."""
    # hardcoding these for now
    cap = cv2.VideoCapture(0)  # Replace with actual GoPro stream URL if available
    if not cap.isOpened():
        log.error('Failed to open video stream')
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            log.error('Failed to read frame from video stream')
            break
        timestamp_ns = time.monotonic_ns()
        try:
            rgb_array = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            log.debug(f'RGB shape: {rgb_array.shape}')
        except Exception as e:
            log.error(f'Failed to decode JPEG: {e}')
            continue

        # publish to Connect
        client.stream_rgb(
            'gopro_camera',
            timestamp=timestamp_ns,
            data=rgb_array.tobytes(),
            width=rgb_array.shape[1],
        )


if __name__ == '__main__':
    stream_data()
