# PolyUMI - Nominal Connect Integration

This directory contains a Nominal Connect app which allows streaming data from the PolyUMI Gripper & End-Effector. 

It depends on 3 pieces of software:
- The `pi` library script which runs on the RPi and streams camera + audio data over ZMQ
- The `polyumi_pi_msgs` package which defines Protobuf messages for the data above, and
- This directory's Connect app, including the `polyumi_connect.py` which consumes the ZMQ data streams, and `polyumi_gopro.py` which consumes footage from the wrist camera connected via USB through an ELGATO Capture Card.

To run the demo:
1. Start the Connect app on PC and open the `polyumi.connect` app.
2. SSH into the RPi and run `python polyumi_pi/main.py stream` from the `pi` directory to start streaming camera + audio data over the network (see the main repo [README](../README.md) for further detail here).
3. Connect the GoPro to the PC through the HDMI capture card + GoPro media mod.
4. Click run on both scripts in the connect app.

Then you should get a live feed of the finger video + audio, as well as the wrist camera footage, in the Connect app!