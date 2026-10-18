# Apollo Cyber RT 开发者工具

Apollo Cyber RT 框架附带了一系列用于日常开发的有用工具，包括一个可视化工具 cyber_visualizer 和两个命令行工具 cyber_monitor 和 cyber_recorder。

_注意：使用这些工具需要 Apollo docker 环境，请按照 Apollo wiki 进入 docker_

所有 Apollo Cyber RT 工具都依赖于 Apollo Cyber RT 库，因此在使用任何 Apollo Cyber RT 工具之前，必须先 source setup.bash 文件进行环境设置，如下所示：

```bash
username@computername:~$: source /your-path-to-apollo-install-dir/cyber/setup.bash
```

## Cyber_visualizer

### 安装和运行

`cyber_visualizer` 是一个用于显示 Apollo Cyber RT 中 channel 数据的可视化工具。

```bash
username@computername:~$: source /your-path-to-apollo-install-dir/cyber/setup.bash
username@computername:~$: cyber_visualizer
```

### 与 cyber_visualizer 交互

- 启动 cyber_visualizer 后，您将看到以下界面：

  ![interface](./images/cyber_visualizer1.png)

- 当数据在 Apollo Cyber RT 的 channel 中流动时，所有 channel 的列表将显示在 `ChannelNames` 下，如下图所示。例如，您可以使用 Apollo Cyber RT 的录制工具（cyber_recorder）从另一个终端回放数据，然后 `cyber_visualizer` 将接收所有活动 channel（来自回放数据）的信息并显示它们。

  ![channel information](./images/cyber_visualizer2.png)

- 通过点击工具栏中的选项，您可以启用参考网格、显示点云、添加图像或同时显示多个相机的数据。如果启用了 `Show Grid` 选项，可以通过双击 `ChannelNames` 下方 `Grid` 列表中的 `Color` 项来设置网格的颜色。默认颜色是灰色。您还可以编辑 `CellCount` 的值来调整网格中的单元格数量。对于点云或图像，可以通过其 `ChannelName` 子项选择源 channel，通过 `Action` 子项播放或停止来自相应 channel 的数据。如下图所示，同时显示了底部三个相机的 channel 数据和顶部一个点云 channel 数据。

      ![visualization](./images/cyber_visualizer3.png)

- 要调整 3D 点云场景中的虚拟相机，可以在点云显示区域右键单击。将弹出如下图所示的对话框。

  ![visualization](./images/cyber_visualizer4.png)

  点云场景支持两种类型的相机：Free 和 Target（从上面的弹出对话框中选择 Type）

  - **Free 类型相机**：对于点云场景中的这种相机类型，可以通过按住左键或右键并移动来改变相机的姿态。要改变相机的俯仰角，可以滚动鼠标滚轮。
  - **Target 类型相机**：对于点云场景中的这种相机类型，要改变相机的视角，可以按住左键然后移动。要改变相机到观察点的距离（默认观察点是坐标系原点（0,0,0）），可以滚动鼠标滚轮。

  您还可以直接在对话框中修改相机信息来改变相机在点云场景中的观察状态。"Step" 项是对话框中的步长值。

  将鼠标放在相机 channel 的图像上，可以双击左键来突出显示左侧菜单栏中相应的数据 channel。右键单击图像以弹出删除相机 channel 的菜单。

  播放和暂停按钮：点击 `Play` 按钮时，所有 channel 都会显示。点击 `Pause` 按钮时，所有 channel 都会停止在工具上显示。

## Cyber_monitor

### 安装和运行

命令行工具 `cyber_monitor` 提供了一个清晰的 Apollo Cyber RT 实时 channel 信息列表视图。

```bash
username@computername:~$: source /your-path-to-apollo-install-dir/cyber/setup.bash
username@computername:~$: cyber_monitor
```

### 有用的命令

#### 显示帮助信息

使用 -h 选项获取 cyber_monitor 的帮助

```bash
username@computername:~$: cyber_monitor -h
```

#### 指定 channel

使用 -c 选项，可以让 cyber_monitor 只监控指定的 channel，例如：

```bash
username@computername:~$: cyber_monitor -c ChannelName
```

## 熟悉 cyber_monitor 的 UI

启动命令行工具后，您会注意到它类似于 cyber_visualizer。它通过拓扑结构自动收集所有 channel 的信息，并以两列（channel 名称、channel 数据类型）显示。

channel 信息的默认显示是红色的。但是，如果有数据流经某个 channel，相应的 channel 行将以绿色显示。如下图所示：

![monitor](./images/cyber_monitor.png)

### 与 cyber_monitor 交互

#### 常用命令

```
ESC | q 键 ---- 退出
Backspace ---- 返回
h | H ---- 显示帮助页面
```

#### 拓扑和 channel 的常用命令

```
PageDown | Ctrl+d --- 下一页
PageUp | Ctrl+u --- 上一页
上、下或 w、s 键 ---- 上下移动当前高亮行
右箭头或 d 键 ---- 进入高亮行，详细显示高亮行数据
左箭头或 a 键 ------ 从当前返回上一层级
Enter 键 ----- 同 d 键
```

#### 仅用于拓扑的命令

```
f | F ----- 显示帧率
t | T ----- 显示 channel 消息类型
Space ----- 关闭|打开 channel（仅对有数据到达的 channel 有效；channel 关闭后显示为黄色）
```

#### 仅用于 channel 的命令

```
i | I ----- 显示 channel 的 Reader 和 Writer 信息
b | B ------ 显示 channel 消息内容
```

#### 查看 channel 中的重复数据字段

```
n | N ---- 重复域中的下一个数据
m | M ---- 重复域中的一个数据
```

## Cyber_recorder

`cyber_recorder` 是 Apollo Cyber RT 提供的录制/回放工具。它提供了许多有用的功能，包括录制 record 文件、回放 record 文件、分割 record 文件、检查 record 文件信息等。

### 安装和运行

启动 cyber_recorder：

```bash
$ source /your-path-to-apollo-install-dir/cyber/setup.bash
$ cyber_recorder
usage: cyber_recorder <command>> [<args>]
The cyber_recorder commands are:
    info                               显示现有 record 的信息
    play                               回放现有的 record
    record                             录制相同的 topic
    split                              分割现有的 record
    recover                            恢复现有的 record
```

### cyber_recorder 命令

- 查看 record 文件的信息：

```
$ cyber_recorder info -h
usage: cyber_recorder info [options]
	-h, --help				显示帮助信息
```

- 录制 record 文件：

```
$ cyber_recorder record -h
usage: cyber_recorder record [options]
    -o, --output <file>                输出 record 文件
    -a, --all                          所有 channel
    -c, --white-channel <name>         只录制指定的 channel
    -k, --black-channel <name>         不录制指定的 channel
    -i, --segment-interval <seconds>   每隔 n 秒分段录制
    -m, --segment-size <MB>            每隔 n MB 分段录制
    -h, --help                         显示帮助信息

```

- 回放 record 文件：

```
$ cyber_recorder play -h
usage: cyber_recorder play [options]
    -f, --file <file>			输入 record 文件
    -a, --all				播放所有
    -c, --white-channel <name>		只播放指定的 channel
    -k, --black-channel <name>		不播放指定的 channel
    -l, --loop				循环播放
    -r, --rate <1.0>			按 FACTOR 倍数改变播放速率
    -b, --begin <2018-07-01 00:00:00>	从指定时间开始播放
    -e, --end <2018-07-01 00:01:00>	播放到指定时间结束
    -s, --start <seconds>		在 n 秒后开始播放
    -d, --delay <seconds>		延迟 n 秒播放
    -p, --preload <seconds>		在尝试预加载 n 秒后播放
    -h, --help				显示帮助信息
```

- 分割 record 文件：

```
$ cyber_recorder split -h
usage: cyber_recorder split [options]
    -f, --file <file>                  输入 record 文件
    -o, --output <file>                输出 record 文件
    -a, --all                          所有 channel
    -c, --white-channel <name>         只分割指定的 channel
    -k, --black-channel <name>         不分割指定的 channel
    -b, --begin <2018-07-01 00:00:00>  在指定时间开始
                                       （以字符串形式，例如 "2018-07-01 00:00:00"）
    -e, --end <2018-07-01 01:00:00>    在指定时间结束
                                       （以字符串形式，例如 "2018-07-01 01:00:00"）
```

- 修复 record 文件：

```
$ cyber_recorder recover -h
usage: cyber_recorder recover [options]
    -f, --file <file>                  输入 record 文件
    -o, --output <file>                输出 record 文件
```

### 使用 cyber_recorder 的示例

#### 查看 record 文件的详细信息

```
$ cyber_recorder info demo.record
record_file:    demo.record
version:        1.0
duration:       19.995227 秒
begin_time:     2018-04-17 06:25:36
end_time:       2018-04-17 06:25:55
size:           28275479 字节 (26.965598 MB)
is_complete:    true
message_number: 15379
channel_number: 16
channel_info:   /apollo/localization/pose                             2000 条消息 : apollo.localization.LocalizationEstimate
                /tf                                                   4000 条消息 : apollo.transform.TransformStampeds
                /apollo/control                                       2000 条消息 : apollo.control.ControlCommand
                /apollo/sensor/gnss/odometry                          2000 条消息 : apollo.localization.Gps
                /apollo/canbus/chassis                                2000 条消息 : apollo.canbus.Chassis
                /apollo/sensor/gnss/imu                               1999 条消息 : apollo.drivers.gnss.Imu
                /apollo/sensor/gnss/rtk_obs                             41 条消息 : apollo.drivers.gnss.EpochObservation
                /apollo/sensor/gnss/ins_stat                            20 条消息 : apollo.drivers.gnss.InsStat
                /apollo/sensor/gnss/best_pose                           20 条消息 : apollo.drivers.gnss.GnssBestPose
                /apollo/perception/obstacles                           400 条消息 : apollo.perception.PerceptionObstacles
                /apollo/prediction                                     400 条消息 : apollo.prediction.PredictionObstacles
                /apollo/sensor/conti_radar                             270 条消息 : apollo.drivers.ContiRadar
                /apollo/planning                                       200 条消息 : apollo.planning.ADCTrajectory
                /apollo/monitor/static_info                              1 条消息 : apollo.data.StaticInfo
                /apollo/sensor/gnss/rtk_eph                             25 条消息 : apollo.drivers.gnss.GnssEphemeris
                /apollo/monitor                                          3 条消息 : apollo.common.monitor.MonitorMessage

```

#### 录制 record 文件

```
$ cyber_recorder record -a
[RUNNING]  录制 :     总 channel 数 : 1  总消息数 : 5
...
```

#### 回放 record 文件

```
$ cyber_recorder play -f 20180720202307.record
file: 20180720202307.record, chunk_number: 1, begin_time: 1532089398663399667, end_time: 1532089404688079759, message_number: 75
请等待加载和回放 record...
按 Ctrl+C 停止回放，或空格键暂停。
[RUNNING]  录制时间: 1532089404.688080    进度: 6.024680 / 6.024680
回放完成。文件: 20180720202307.record
```

## rosbag_to_record

`rosbag_to_record` 是一个可以将 rosbag 转换为 Apollo Cyber RT 提供的 recorder 文件的工具。现在该工具支持以下 channel：

```
/apollo/perception/obstacles
/apollo/planning
/apollo/prediction
/apollo/canbus/chassis
/apollo/control
/apollo/guardian
/apollo/localization/pose
/apollo/perception/traffic_light
/apollo/drive_event
/apollo/sensor/gnss/odometry
/apollo/monitor/static_info
/apollo/monitor
/apollo/canbus/chassis_detail
/apollo/control/pad
/apollo/navigation
/apollo/routing_request
/apollo/routing_response
/tf
/tf_static
/apollo/sensor/conti_radar
/apollo/sensor/delphi_esr
/apollo/sensor/gnss/best_pose
/apollo/sensor/gnss/imu
/apollo/sensor/gnss/ins_stat
/apollo/sensor/gnss/rtk_eph
/apollo/sensor/gnss/rtk_obs
/apollo/sensor/velodyne64/compensator/PointCloud2
```

### 安装和运行

启动 rosbag_to_record：

```bash
$ source /your-path-to-apollo-install-dir/cyber/setup.bash
$ rosbag_to_record
Usage:
  rosbag_to_record input.bag output.record
```

### 示例

我们可以将 [Apollo2.5 demo bag](https://github.com/ApolloAuto/apollo/releases/download/v2.5.0/demo_2.5.bag) 转换为 record 文件。

```bash
$ rosbag_to_record demo_2.5.bag demo.record
record_file:    demo.record
version:        1.0
duration:       19.995227 秒
begin_time:     2018-04-17 06:25:36
end_time:       2018-04-17 06:25:55
size:           28275479 字节 (26.965598 MB)
is_complete:    true
message_number: 15379
channel_number: 16
channel_info:   /apollo/localization/pose                             2000 条消息 : apollo.localization.LocalizationEstimate
                /tf                                                   4000 条消息 : apollo.transform.TransformStampeds
                /apollo/control                                       2000 条消息 : apollo.control.ControlCommand
                /apollo/sensor/gnss/odometry                          2000 条消息 : apollo.localization.Gps
                /apollo/canbus/chassis                                2000 条消息 : apollo.canbus.Chassis
                /apollo/sensor/gnss/imu                               1999 条消息 : apollo.drivers.gnss.Imu
                /apollo/sensor/gnss/rtk_obs                             41 条消息 : apollo.drivers.gnss.EpochObservation
                /apollo/sensor/gnss/ins_stat                            20 条消息 : apollo.drivers.gnss.InsStat
                /apollo/sensor/gnss/best_pose                           20 条消息 : apollo.drivers.gnss.GnssBestPose
                /apollo/perception/obstacles                           400 条消息 : apollo.perception.PerceptionObstacles
                /apollo/prediction                                     400 条消息 : apollo.prediction.PredictionObstacles
                /apollo/sensor/conti_radar                             270 条消息 : apollo.drivers.ContiRadar
                /apollo/planning                                       200 条消息 : apollo.planning.ADCTrajectory
                /apollo/monitor/static_info                              1 条消息 : apollo.data.StaticInfo
                /apollo/sensor/gnss/rtk_eph                             25 条消息 : apollo.drivers.gnss.GnssEphemeris
                /apollo/monitor                                          3 条消息 : apollo.common.monitor.MonitorMessage
转换完成！总共花费 0.505623051 秒。
```
