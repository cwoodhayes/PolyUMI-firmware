"""Setup for the polyumi_pi_msgs package."""

import shutil
from pathlib import Path

from setuptools import find_packages, setup

package_name = 'polyumi_pi_msgs'


def compile_protos():
    """Compile the protobuf files."""
    from grpc_tools import protoc  # type: ignore

    package_dir = Path(__file__).resolve().parent
    proto_root = package_dir / package_name
    proto_files = sorted(proto_root.glob('*.proto'))

    for proto_file in proto_files:
        proto_cmd = [
            'grpc_tools.protoc',
            f'-I={proto_root}',
            f'--python_out={proto_root}',
        ]
        proto_cmd.append(str(proto_file))

        result = protoc.main(proto_cmd)

        if result != 0:
            raise RuntimeError(
                f'Failed to compile protobuf file: {proto_file}'
            )


compile_protos()

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        (
            'share/ament_index/resource_index/packages',
            ['resource/' + package_name],
        ),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='conorbot',
    maintainer_email='cwoodhayes@gmail.com',
    description='Protobuf messages for communication with PolyTouch CE Finger',
    license='MIT',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [],
    },
)
