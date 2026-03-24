"""
Connect directly to the streams coming off the PolyUMI.

Run `python polyumi_pi/main.py stream` on the PolyUMI pi to produce data for
this to ingest. (see PolyUMI repo README for more details).
"""

import io
import logging
import threading
import time
from datetime import datetime

import connect_python
import numpy as np
import zmq
from PIL import Image
from polyumi_pi_msgs import (
    audio_chunk_pb2,
    camera_frame_pb2,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('polyumi_connect')


class PolyUMIConnect:
    """Reroute PolyUMI data to Connect."""

    def __init__(
        self, client: connect_python.Client, pi_host: str, port: int, audio_port: int
    ) -> None:
        """Initialize the object."""
        self._client = client
        self._pi_host = pi_host
        self._port = port
        self._audio_port = audio_port
        self._zmq_context = zmq.Context()

    def start(self):
        """Start publishing data to Connect."""
        recv_thread = threading.Thread(
            target=self._camera_recv_loop,
            daemon=True,
        )
        recv_thread.start()

        audio_recv_thread = threading.Thread(
            target=self._audio_recv_loop,
            daemon=True,
        )
        audio_recv_thread.start()

        log.info(
            f'Receiving from tcp://{self._pi_host}:{self._port}, '
            f'publishing on /pi/camera/image/compressed'
        )
        log.info(f'Receiving audio from tcp://{self._pi_host}:{self._audio_port}')
        log.info('Publishing audio on /pi/audio/raw')

    def _camera_recv_loop(self):
        sock = self._zmq_context.socket(zmq.PULL)
        sock.connect(f'tcp://{self._pi_host}:{self._port}')

        while True:
            try:
                raw = sock.recv()
            except zmq.ZMQError as e:
                log.error(f'ZMQ recv error: {e}')
                break

            log.debug(f'Received {len(raw)} bytes from ZMQ')
            proto = camera_frame_pb2.CameraFrame()
            proto.ParseFromString(raw)

            # Decompress JPEG to raw RGB
            try:
                image = Image.open(io.BytesIO(proto.jpeg_data))
                rgb_image = image.convert('RGB')
                rgb_array = np.array(rgb_image)
                log.debug(f'RGB shape: {rgb_array.shape}')
            except Exception as e:
                log.error(f'Failed to decode JPEG: {e}')
                continue

            # publish to Connect
            self._client.stream_rgb(
                'pi_camera',
                timestamp=proto.timestamp_ns,
                data=rgb_array.tobytes(),
                width=rgb_array.shape[1],
            )

    def _audio_recv_loop(self):
        sock = self._zmq_context.socket(zmq.PULL)
        sock.connect(f'tcp://{self._pi_host}:{self._audio_port}')

        last_ts_ns = 0
        chunks = 0
        gap_warnings = 0
        last_stats_t = time.monotonic_ns()

        while True:
            try:
                raw = sock.recv()
            except zmq.ZMQError as e:
                log.error(f'ZMQ audio recv error: {e}')
                break

            proto = audio_chunk_pb2.AudioChunk()
            proto.ParseFromString(raw)

            bytes_per_sample = max(1, proto.bit_depth // 8)
            frame_bytes = max(1, proto.channels * bytes_per_sample)
            sample_frames = len(proto.pcm_data) // frame_bytes
            if proto.sample_rate > 0:
                expected_delta_ns = int(sample_frames * 1e9 / proto.sample_rate)
            else:
                expected_delta_ns = 0

            if last_ts_ns and expected_delta_ns > 0:
                delta_ns = proto.timestamp_ns - last_ts_ns
                if delta_ns > int(expected_delta_ns * 1.5):
                    gap_warnings += 1
                    log.warning(
                        'Audio timestamp gap: '
                        f'delta={delta_ns / 1e6:.2f}ms '
                        f'expected={expected_delta_ns / 1e6:.2f}ms'
                    )
            last_ts_ns = proto.timestamp_ns
            chunks += 1

            # publish to Connect
            timestamps = [
                proto.timestamp_ns + int(i * 1e9 / proto.sample_rate)
                for i in range(sample_frames)
            ]
            arr = np.frombuffer(proto.pcm_data, dtype=np.int16).reshape(
                -1, proto.channels
            )
            values = arr[:, 0].tolist()  # for now just publish the first channel
            log.debug(
                f'Publishing audio chunk: n_frames={sample_frames} timestamps={timestamps[0]}-{timestamps[-1]} '
                f'values len={len(values)}, timestamps len = {len(timestamps)}'
            )

            self._client.stream_batch(
                stream_id='polyumi_audio',
                timestamps=timestamps,
                values=values,
                name='PolyUMI Audio (raw PCM)',
                names=['channel_L'],
                unit='bit',
            )

            now_ns = time.monotonic_ns()
            if now_ns - last_stats_t >= 1e9:
                log.info(f'Audio rx stats: chunks={chunks}/s gaps={gap_warnings}')
                chunks = 0
                gap_warnings = 0
                last_stats_t = now_ns


@connect_python.main
def stream_data(client: connect_python.Client):
    """Stream audio data from zmq."""
    # hardcoding these for now
    pi_host = '10.106.10.62'
    port = 5555
    audio_port = 5556

    cnx = PolyUMIConnect(client, pi_host, port, audio_port)
    cnx.start()

    while True:
        time.sleep(1)


if __name__ == '__main__':
    stream_data()
