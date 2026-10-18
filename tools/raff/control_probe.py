#!/usr/bin/env python3
"""Probe /apollo/control while replaying a record.

Usage: run inside the Apollo dev container after `source /apollo/cyber/setup.bash`
and with PYTHONPATH=/apollo:/apollo/bazel-bin:$PYTHONPATH.
"""

import time

from cyber.python.cyber_py3 import cyber
from modules.common_msgs.chassis_msgs import chassis_pb2
from modules.common_msgs.control_msgs import control_cmd_pb2


count = 0
chassis_count = 0


def control_cb(msg):
    global count
    count += 1
    if count > 30:
        return
    debug = msg.debug
    print(
        "CTRL seq=%s steer=%.3f throttle=%.2f brake=%.2f acc=%.3f"
        % (
            msg.header.sequence_num,
            msg.steering_target,
            msg.throttle,
            msg.brake,
            msg.acceleration,
        )
    )
    if debug.HasField("simple_lat_debug"):
        d = debug.simple_lat_debug
        print(
            "  LAT e_y=%.4f e_psi=%.4f ff=%.3f fb=%.3f kappa=%.5f"
            % (
                d.lateral_error,
                d.heading_error,
                d.steer_angle_feedforward,
                d.steer_angle_feedback,
                d.curvature,
            )
        )
    if debug.HasField("simple_lon_debug"):
        d = debug.simple_lon_debug
        print(
            "  LON e_s=%.4f e_v=%.4f acc_cmd=%.3f throttle=%.2f brake=%.2f"
            % (
                d.station_error,
                d.speed_error,
                d.acceleration_cmd,
                d.throttle_cmd,
                d.brake_cmd,
            )
        )
    if debug.HasField("simple_mpc_debug"):
        m = debug.simple_mpc_debug
        print(
            "  MPC e_y=%.4f e_psi=%.4f e_s=%.4f e_v=%.4f ff=%.3f fb=%.3f"
            % (
                m.lateral_error,
                m.heading_error,
                m.station_error,
                m.speed_error,
                m.steer_angle_feedforward,
                m.steer_angle_feedback,
            )
        )


def chassis_cb(msg):
    global chassis_count
    chassis_count += 1
    if chassis_count == 1 or chassis_count % 200 == 0:
        print(
            "CHASSIS mode=%s gear=%s speed=%.3f"
            % (msg.driving_mode, msg.gear_location, msg.speed_mps)
        )


def main():
    cyber.init()
    node = cyber.Node("raff_control_probe")
    node.create_reader(
        "/apollo/control", control_cmd_pb2.ControlCommand, control_cb
    )
    node.create_reader("/apollo/canbus/chassis", chassis_pb2.Chassis, chassis_cb)
    end = time.time() + 20
    while time.time() < end:
        time.sleep(0.5)
    print("SUMMARY control_msgs=%d chassis_msgs=%d" % (count, chassis_count))
    cyber.shutdown()


if __name__ == "__main__":
    main()
