# {Repo Name}

Author: Conor Hayes

## Setup
```bash
cd ros2_ws
rosdep install --from-paths src/ --rosdistro kilted
colcon build
source install/setup.bash
```

## Run Franka Streaming Demo
```bash
# launch the demo
ros2 launch polyumi_ros2 stream_demo.launch.xml
```
Then open [foxglove](https://app.foxglove.dev) in your browser, and connect to `ws://localhost:8765` (the default).