# {Repo Name}

Author: Conor Hayes

## Setup
```bash
cd ros2_ws
rosdep install --from-paths . --rosdistro kilted
colcon build
source install/setup.bash
```

## Run Franka Streaming Demo
```bash
# run foxglove either through the below command or from your desktop
foxglove-studio

# launch the demo
ros2 launch polyumi_ros2 stream_demo.launch.xml
```