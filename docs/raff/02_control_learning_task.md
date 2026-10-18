# 控制学习任务：从运行环境到 LAT/LON/MPC 对比

> 目标：用**一个可重复的自动驾驶任务**把 Control 模块跑起来，
> 在真实数据流中观察 LAT、LON、MPC 三种控制器的输入、输出和调试量。
>
> 配套源码笔记：
> - [01_apollo_environment.md](01_apollo_environment.md)（环境基础）
> - [04_mpc_controller_source_notes.md](04_mpc_controller_source_notes.md)（MPC）
> - [03_lat_lon_controller_source_notes.md](03_lat_lon_controller_source_notes.md)（LAT/LON）

## 目录

- [0. 结论先行：做什么任务](#0-结论先行做什么任务)
- [1. 环境准备](#1-环境准备)
- [2. 任务 A：Demo 地图直线/停车](#2-任务-admemo-地图直线停车)
- [3. 任务 B：Borregas Ave 弯道](#3-任务-bborregas-ave-弯道)
- [4. 任务 C：LAT/LON 与 MPC 对比](#4-任务-clatlon-与-mpc-对比)
- [5. 任务 D：离线数据包回放（可选）](#5-任务-d离线数据包回放可选)
- [6. 数据采集与调试工具](#6-数据采集与调试工具)
- [7. 常见问题](#7-常见问题)
- [8. 7 天学习计划](#8-7-天学习计划)
- [9. 速查表](#9-速查表)

---

## 0. 结论先行：做什么任务

在本仓库的源码环境下，推荐按下面顺序做：

| 任务 | 场景 | 练什么 | 为什么选它 |
|---|---|---|---|
| **A** | `demo` 地图，约 153 m 的固定路线 | LON 双环 PID、标定表、终点停车 | 地图和路线都在仓库里，路线短，容易反复跑 |
| **B** | `borregas_ave` 地图，画一条含左右弯的路线 | LAT LQR、前馈、增益调度 | 有真实道路曲率，能明显看到横向误差和转角变化 |
| **C** | 同一路线分别跑 LAT/LON 和 MPC | 两种控制架构对比 | 输入相同，输出可直接比较 |
| **D** | 回放 `demo_3.5.record` | 观察真实数据、调试输出 | 无需仿真环境，但要处理旧时间戳问题 |

> **重要**：本仓库的 `modules/map/data/sunnyvale*` 目录是空的，
> 官方文档里常用的 Sunnyvale Big Loop 在当前 checkout 中不可用。
> 可直接使用的地图是：
> - `modules/map/data/demo`（文本地图，153 m 车库路线）
> - `modules/map/data/borregas_ave`（二进制地图，真实道路）
>
> 如果你从 Apollo Studio 或其他渠道下载了 Sunnyvale 地图，再按官方文档替换即可。

---

## 1. 环境准备

### 1.1 进入容器

```bash
# 宿主机
cd /home/zrf/apollo
bash docker/scripts/dev_start.sh -y
bash docker/scripts/dev_into.sh
```

### 1.2 构建本次任务需要的模块

```bash
# 容器内，仓库根目录
source /apollo/cyber/setup.bash
export APOLLO_BUILD_JOBS=16

# DreamView+ 路径
./apollo.sh build cyber planning routing control dreamview_plus

# 如果使用经典 DreamView，把 dreamview_plus 换成 dreamview
# ./apollo.sh build cyber planning routing control dreamview
```

只改控制器配置（`*.pb.txt`）时不需要重新编译，重启模块即可；
改 C++ 代码必须重新 `./apollo.sh build control`。

### 1.3 启动 DreamView

```bash
# 方式一：DreamView+（推荐，界面在 8888）
./scripts/bootstrap.sh start_plus

# 方式二：经典 DreamView
# 本仓库经典版默认也监听 8888，不要和 start_plus 同时用，见 Q9
./scripts/bootstrap.sh start
```

浏览器打开：

- DreamView+：`http://localhost:8888`
- 经典 DreamView：本仓库默认也是 `http://localhost:8888`
  （`bootstrap.sh` 里的 8899 健康检查是上游遗留，会误报启动失败）

两种方式二选一。切换前先 `./scripts/bootstrap.sh stop_plus` 或
`./scripts/bootstrap.sh stop`，否则 8888 被占用会导致新后端启动失败。

停止：

```bash
./scripts/bootstrap.sh stop_plus
# 或
./scripts/bootstrap.sh stop
```

### 1.4 启动 Planning / Routing / Control

可以直接在 DreamView 的 **Module Controller** 里打开，也可以用命令行：

```bash
# 容器内
cyber_launch start modules/planning/planning_component/launch/planning.launch
cyber_launch start modules/routing/launch/routing.launch
cyber_launch start modules/control/control_component/launch/control.launch
```

> 注意：`scripts/planning.sh` 里的路径是
> `modules/planning/launch/planning.launch`，当前仓库实际路径是
> `modules/planning/planning_component/launch/planning.launch`，
> 所以这里直接写完整路径。

停止：

```bash
cyber_launch stop modules/control/control_component/launch/control.launch
cyber_launch stop modules/routing/launch/routing.launch
cyber_launch stop modules/planning/planning_component/launch/planning.launch
```

### 1.5 检查环境

```bash
# 节点
cyber_node list

# 通道（应能看到 /apollo/planning、/apollo/control、/apollo/localization/pose 等）
cyber_monitor
```

如果 DreamView 里模块状态是绿色，且 `cyber_monitor` 能看到
`/apollo/planning` 和 `/apollo/control`，环境就准备好了。

---

## 2. 任务 A：Demo 地图直线/停车

### 2.1 任务描述

在 `demo` 地图上跑一条约 153 m 的路线，包含：

- 从静止起步；
- 中低速直行/轻微转向；
- 接近终点减速；
- 完全停车（full stop）。

### 2.2 操作步骤（DreamView+）

1. 打开 `http://localhost:8888`。
2. 进入 **PNC 模式**。
3. 高精地图选择 **Demo**，车辆选择 **MKZ Example**。
4. 操作模式选择 **Sim_Control**。
5. 在 Module Controller 中启动 **Planning**、**Routing**、**Control**。
6. 打开 **车辆可视化 → 路由编辑**，在地图上设置起点和终点，
   发送路由请求。
7. 动态模型先选 **Simulation Perfect Control**，点击 **启动**。

> `Simulation Perfect Control` 会让仿真车辆直接跟随规划轨迹，
> **不响应控制器的油门/刹车/转向**。它的作用是先让你看到完整的数据流。
> 想验证「控制器真的在控制车辆」，需要选择 **MKZ Model** 或
> **Point Mass Model**（如果本地已安装对应动态模型包）；
> 参见第 7 节。

### 2.3 观察什么（LON）

用 `cyber_monitor -c /apollo/control` 展开
`debug.simple_lon_debug`，重点看：

| 字段 | 含义 | 期望 |
|---|---|---|
| `station_error` | 参考位置 - 当前位置 | 起步/停车附近会有变化，正常跟踪时应较小 |
| `speed_error` | 参考速度 - 当前速度 | 加速/减速时变化 |
| `speed_offset` | 位置环 PID 输出 | 位置落后时为正 |
| `speed_controller_input_limited` | 速度环输入（限幅后） | 不超过 ±1.5 m/s |
| `acceleration_cmd_closeloop` | 速度环 PID 输出 | 与速度误差同向 |
| `acceleration_cmd` | 叠加参考加速度/坡度后的最终加速度 | 驱动标定表 |
| `throttle_cmd` / `brake_cmd` | 标定表输出的油门/刹车 | 加速给油门，减速给刹车 |
| `path_remain` | 距停车点的剩余距离 | 终点附近趋近 0 |
| `is_full_stop` | 是否完全停车 | 终点附近变 true |
| `is_stop_reason_by_destination` | 是否因终点停车 | 终点附近为 true |

### 2.4 练习

1. 记录一次完整的起步→停车数据：
   ```bash
   mkdir -p /apollo/data/record
   cyber_recorder record -c /apollo/control -c /apollo/planning \
     -c /apollo/localization/pose -c /apollo/canbus/chassis \
     -o /apollo/data/record/lat_lon_task_a.record
   ```
2. 找到 `station_error` 最大和最小的时刻，解释位置环在做什么。
3. 找到 `is_full_stop` 第一次为 true 的时刻，对照 `path_remain` 和
   `acceleration_cmd`，理解停车逻辑。
4. 修改 `standstill_acceleration`（默认 -0.3）为 -0.5，观察停车过程。
   改配置后重启 control 即可，不需要重新编译。

---

## 3. 任务 B：Borregas Ave 弯道

### 3.1 任务描述

在 `borregas_ave` 地图上画一条包含**左弯 + 右弯**的路线，
保持中低速，观察横向控制器的跟踪过程。

### 3.2 操作步骤

1. DreamView+ → PNC 模式。
2. 地图选择 **Borregas Ave**，车辆 **MKZ Example**。
3. 操作模式 **Sim_Control**。
4. 启动 Planning、Routing、Control。
5. 路由编辑：起点 → 经过一个左弯 → 经过一个右弯 → 终点。
6. 先使用 **Simulation Perfect Control** 跑通；如果已安装
   **MKZ Model / Point Mass Model**，改用动态模型做闭环。
7. 启动，观察车辆和轨迹。

### 3.3 观察什么（LAT）

用 `cyber_monitor -c /apollo/control` 展开
`debug.simple_lat_debug`：

| 字段 | 含义 | 期望 |
|---|---|---|
| `lateral_error` | 横向误差 `e_y` | 弯道中会增大，LQR 应把它拉回 0 |
| `heading_error` | 航向误差 `e_psi` | 入弯/出弯时变化 |
| `lateral_error_rate` | `v * sin(e_psi)` | 与航向误差相关 |
| `curvature` | 参考曲率 `kappa` | 弯道中非零 |
| `steer_angle_feedforward` | 曲率前馈 | 弯道中明显 |
| `steer_angle_feedback` | LQR 反馈 | 误差驱动 |
| `steer_angle_lateral_contribution` | 横向误差分项 | 可用来拆解反馈 |
| `steer_angle_heading_contribution` | 航向误差分项 | 可用来拆解反馈 |
| `steer_angle` | 最终转角 | 限幅/滤波后 |
| `steer_angle_limited` | 横向加速度限幅后的转角 | 高速弯道可能触限 |

### 3.4 练习

1. 在一个稳定弯道中，比较 `steer_angle_feedforward` 和
   `steer_angle_feedback` 的大小，理解「前馈为主、反馈修正」。
2. 把 `max_lateral_acceleration` 从 5.0 降到 2.0，观察
   `steer_angle_limited` 是否触限，以及横向误差是否变大。
3. 把 `lat_err_gain_scheduler` 在 8 m/s 的 ratio 从 0.6 改成 1.0，
   观察横向误差和转向抖动。
4. 把 `matrix_q(2,2)`（航向误差权重）从 1.0 改到 2.0，
   观察航向误差和转向幅度。
5. 把 `preview_window` 改为 5，并同步把 `matrix_q` 和
   `reverse_matrix_q` 扩展到 9 个值，观察预览控制的效果。
   （注意：不扩展 Q 会初始化失败。）

---

## 4. 任务 C：LAT/LON 与 MPC 对比

### 4.1 准备

先备份默认 pipeline：

```bash
cp modules/control/control_component/conf/pipeline.pb.txt \
   /tmp/pipeline_lat_lon.pb.txt
```

### 4.2 跑 LAT/LON

保持默认 pipeline：

```text
controller { name: "LAT_CONTROLLER" type: "LatController" }
controller { name: "LON_CONTROLLER" type: "LonController" }
```

启动 control，跑任务 A 或 B，录制数据：

```bash
cyber_recorder record -c /apollo/control -c /apollo/planning \
  -c /apollo/localization/pose -c /apollo/canbus/chassis \
  -o /apollo/data/record/task_c_lat_lon.record
```

### 4.3 切换到 MPC

把 pipeline 改成只保留 MPC：

```bash
cat > modules/control/control_component/conf/pipeline.pb.txt <<'EOF'
controller {
  name: "MPC_CONTROLLER"
  type: "MPCController"
}
EOF
```

重启 control（配置是运行时读取的，不需要重新编译）：

```bash
cyber_launch stop modules/control/control_component/launch/control.launch
cyber_launch start modules/control/control_component/launch/control.launch
```

跑**同一张地图、同一条路线、同一个起点**，录制：

```bash
cyber_recorder record -c /apollo/control -c /apollo/planning \
  -c /apollo/localization/pose -c /apollo/canbus/chassis \
  -o /apollo/data/record/task_c_mpc.record
```

### 4.4 恢复 LAT/LON

```bash
cp /tmp/pipeline_lat_lon.pb.txt \
   modules/control/control_component/conf/pipeline.pb.txt
cyber_launch stop modules/control/control_component/launch/control.launch
cyber_launch start modules/control/control_component/launch/control.launch
```

### 4.5 对比指标

| 指标 | 从哪里看 | 说明 |
|---|---|---|
| 横向误差 RMS/最大值 | `simple_lat_debug.lateral_error` / `simple_mpc_debug.lateral_error` | 跟踪精度 |
| 航向误差 RMS/最大值 | `heading_error` | 姿态跟踪 |
| 纵向位置误差 | `simple_lon_debug.station_error` / `simple_mpc_debug.station_error` | 停车/跟车 |
| 速度误差 | `speed_error` | 速度跟踪 |
| 转向幅度 | `steering_target` | 转向是否激进 |
| 转向变化率 | 相邻帧 `steering_target` 差分 | 抖动/平滑度 |
| 油门/刹车切换次数 | `throttle` / `brake` | 纵向平滑度 |
| 控制计算耗时 | `control_command.latency_stats.total_time_ms` | 实时性 |
| 停车距离误差 | `path_remain` 在 full stop 时的值 | 停车精度 |

建议做一个简单的表格：

```text
指标                 LAT/LON     MPC
横向误差 RMS (m)     ____        ____
航向误差 RMS (rad)   ____        ____
纵向误差 RMS (m)     ____        ____
最大转角 (%)         ____        ____
转向抖动 (次数)      ____        ____
平均计算耗时 (ms)    ____        ____
```

> 注意：两次运行必须使用**同一条路线、同一个起点、同一个动态模型**，
> 否则对比没有意义。Perfect Control 下控制指令不影响车辆，
> 两次运行的车辆轨迹会完全一致，这时对比的是「控制器输出」而不是
> 「闭环跟踪效果」；要比较闭环效果，必须使用 MKZ/Point Mass 动态模型。

---

## 5. 任务 D：离线数据包回放（可选）

### 5.1 下载数据包

```bash
# 容器内，任选一种
python3 "docs/02_Quick Start/demo_guide/record_helper.py" demo_3.5.record

# 或直接下载（约 92 MB）
curl -L -o demo_3.5.record \
  https://apollo-system.cdn.bcebos.com/dataset/6.0_edu/demo_3.5.record
```

数据包内容（已用 `cyber_recorder info` 验证）：

- 时长约 45.5 s；
- `/apollo/planning` 455 条；
- `/apollo/localization/pose` 4558 条；
- `/apollo/canbus/chassis` 4536 条；
- `/apollo/control` 4539 条（原始车辆的控制输出）。

### 5.2 回放

```bash
# 启动 control（默认 LAT+LON）
cyber_launch start modules/control/control_component/launch/control.launch

# 只回放控制需要的输入，避免把录制好的 /apollo/control 也播出来
cyber_recorder play -f demo_3.5.record \
  -c /apollo/planning -c /apollo/localization/pose -c /apollo/canbus/chassis
```

另开终端观察：

```bash
cyber_monitor -c /apollo/control
```

### 5.3 重要：旧数据包的时间戳问题

基础 `LonController` 在
[`ComputeLongitudinalErrors`](../../modules/control/controllers/lon_based_pid_controller/lon_controller.cc#L621)
里用：

```cpp
double current_control_time = ::apollo::cyber::Clock::NowInSeconds();
```

去查规划轨迹的参考点。`demo_3.5.record` 录制于 2019 年，
规划消息头里的时间也是 2019 年；而当前墙钟是 2026 年。
`QueryNearestPointByAbsoluteTime(now)` 会把 `now - header_time` 算成一个巨大的
相对时间，结果取到轨迹**最后一个点**，导致 `station_error` 异常大。

实测现象（供对照）：

```text
CHASSIS mode=1 speed=8.800            # mode=1: COMPLETE_AUTO_DRIVE
LON e_s=63.7277 e_v=0.1000 ...
LAT e_y=-0.0252 e_psi=0.0020 ...      # 横向误差仍然正常
```

处理办法：

1. **推荐**：用第 2/3 节的 SimControl 任务，时间戳是当前时间，
   基础控制器工作正常。
2. **高级**：使用 Plus 控制器（`LatPlusController` / `LonPlusController`），
   它们支持 `FLAGS_sim_by_record`，会用底盘消息头时间替代墙钟时间。
   需要把 pipeline 的类型换成 `LatPlusController` / `LonPlusController`，
   并使用对应的参数管线配置。
3. **学习练习**：给基础 `LonController` 打一个小补丁：
   ```cpp
   double current_control_time = FLAGS_sim_by_record
       ? chassis_->header().timestamp_sec()
       : ::apollo::cyber::Clock::NowInSeconds();
   ```
   然后在 `control.conf` 里加 `--sim_by_record=true`，重新编译 control。
   横向控制器默认按位置匹配，通常不需要改；如果打开了
   `query_time_nearest_point_only`，同理改成使用 `chassis->header()`。
4. **只观察横向**：回放时重点看 LAT 的 `lateral_error`、`heading_error`、
   前馈/反馈；LON 的纵向误差在旧数据包上不可信。

### 5.4 回放任务练习

1. 用原始录制的 `/apollo/control` 和重新计算的 `/apollo/control` 对比，
   看转向和油门/刹车差多少。
2. 把 `matrix_q` 的横向权重从 0.05 改成 0.2，观察横向误差变化。
3. 用 `cyber_recorder record` 把重新计算的控制输出录下来，回放复盘。

---

## 6. 数据采集与调试工具

### 6.1 `cyber_monitor`

```bash
cyber_monitor -c /apollo/control
```

进入通道后，展开 `debug`：

- `simple_lat_debug`：LAT 的误差、前馈、反馈、各分项；
- `simple_lon_debug`：LON 的误差、PID 输出、标定值、停车标志；
- `simple_mpc_debug`：MPC 的误差、前馈、反馈、Q/R 更新值。

### 6.2 `control_probe.py`

仓库里提供了一个小脚本
[`tools/raff/control_probe.py`](../../tools/raff/control_probe.py)，
用于在终端打印控制器的关键字段：

```bash
# 容器内
source /apollo/cyber/setup.bash
export PYTHONPATH=/apollo:/apollo/bazel-bin:$PYTHONPATH
python3 /apollo/tools/raff/control_probe.py
```

它会订阅 `/apollo/control` 和 `/apollo/canbus/chassis`，打印：

- `steering_target`、`throttle`、`brake`、`acceleration`；
- LAT：`e_y`、`e_psi`、前馈、反馈、曲率；
- LON：`e_s`、`e_v`、加速度、油门、刹车；
- MPC：6 状态误差、前馈、反馈。

### 6.3 `cyber_recorder`

```bash
# 录制控制学习数据
mkdir -p /apollo/data/record
cyber_recorder record -c /apollo/control -c /apollo/planning \
  -c /apollo/localization/pose -c /apollo/canbus/chassis \
  -o /apollo/data/record/control_task.record

# 查看信息
cyber_recorder info /apollo/data/record/control_task.record

# 回放
cyber_recorder play -f /apollo/data/record/control_task.record
```

### 6.4 日志

```bash
tail -f /apollo/data/log/control.INFO
# 或按时间找最新的日志
ls -lt /apollo/data/log | head
```

---

## 7. 常见问题

### Q1：`/apollo/control` 一直输出 0？

按顺序检查：

1. `chassis.driving_mode` 是否为 `COMPLETE_AUTO_DRIVE`（枚举值 1）；
2. 是否有 estop（规划 estop、输入超时、空轨迹）；
3. Planning 是否发布 `/apollo/planning`；
4. Control 是否启动（`cyber_node list`）；
5. 是否在手动模式；手动模式会走 `ResetAndProduceZeroControlCommand`。

### Q2：SimControl 里车辆不响应控制器的油门/刹车？

默认动态模型是 **Simulation Perfect Control**，它直接跟随规划轨迹，
不读取控制指令。要验证控制效果，选择 **MKZ Model** 或 **Point Mass Model**。
这些动态模型是外部资源包；如果没有安装，先在 DreamView+ 的资源管理里下载。

### Q3：地图列表里没有 Sunnyvale Big Loop？

当前 checkout 的 `modules/map/data/sunnyvale*` 目录是空的。
使用 `demo` 或 `borregas_ave`；需要 Sunnyvale 时先从 Apollo Studio
或其他渠道下载地图并放到对应目录。

### Q4：改了 `pipeline.pb.txt` 没生效？

pipeline 在 `ControlComponent::Init` 时读取，必须**重启 control**。
只重启 DreamView 不够。

### Q5：改了 `controller_conf.pb.txt` 没生效？

同样需要重启 control；配置是运行时读取的，不需要重新编译。
如果改的是 `proto` 字段，则需要重新编译。

### Q6：`scripts/planning.sh start` 启动失败？

该脚本使用旧路径 `modules/planning/launch/planning.launch`，
当前实际路径是 `modules/planning/planning_component/launch/planning.launch`。
直接用 `cyber_launch start` 指定完整路径。

### Q7：回放旧数据包时 `station_error` 很大？

见第 5.3 节。基础 LON 用墙钟时间查参考点，旧数据包会取到轨迹最后一点。
用 SimControl，或使用 Plus 控制器 / `sim_by_record` 补丁。

### Q8：LAT 初始化报 `matrix_q size` 错误？

`matrix_q` 和 `reverse_matrix_q` 的长度必须等于
`4 + preview_window`。默认 `preview_window = 0`，所以是 4 个值；
改成 5 后必须同步扩展到 9 个值。

### Q9：DreamView+ 显示 WebSocket ×、Proto parsing 0%？

典型原因是 8888 已被另一个 DreamView 进程占用（例如之前跑过
`bootstrap.sh start`），`dreamview_plus` 绑定端口失败后立即退出：

```text
terminate called after throwing an instance of 'CivetException'
  what():  null context when constructing CivetServer. Possible problem binding to port.
```

`cyber_launch` 会 respawn 3 次，然后报 `All processes has died`；
而 `bootstrap.sh start_plus` 最后的 `curl 8888` 健康检查会打到旧进程上，
仍然打印 "Dreamview Plus is running"，很容易误判。

排查：

```bash
ss -ltnp | grep 8888
ps -ef | grep -E "dreamview|cyber_launch" | grep -v grep
tail -n 50 /apollo/nohup.out
tail -n 50 data/log/dreamview_plus.INFO
```

处理：

```bash
./scripts/bootstrap.sh stop        # 停经典版与 monitor
./scripts/bootstrap.sh stop_plus   # 如 Plus 相关进程仍在
ss -ltnp | grep 8888               # 确认端口已释放
./scripts/bootstrap.sh start_plus
```

然后浏览器强制刷新（Ctrl+Shift+R）。验证后端是否真的是 Plus：

```bash
ss -ltnp | grep 8888     # 进程名应为 dreamview_plus
```

为什么 `start` 也会占 8888：本仓库
`modules/dreamview/backend/common/dreamview_gflags.cc` 里
`server_ports` 默认是 `"8888"`，`dreamview.launch` 没有覆盖端口；
`bootstrap.sh` 中的 `DREAMVIEW_URL=8899` 只是上游遗留的检查地址，
不代表经典版真的监听 8899。并且经典后端的 `static_file_dir` 默认也指向
`modules/dreamview_plus/frontend/dist`，所以它占着 8888 时，浏览器看到的是
“DreamView+ 前端 + 经典后端”的组合，表现正是 WebSocket ×、proto parsing 0%。

---

## 8. 7 天学习计划

| 天 | 任务 | 产出 |
|---|---|---|
| 1 | 环境准备：构建、启动 DreamView、启动三个模块 | 能看到 `/apollo/control` 数据 |
| 2 | 任务 A：Demo 地图直线/停车 | 理解 LON 双环 PID、标定表、full stop |
| 3 | 任务 B：Borregas Ave 弯道 | 理解 LAT LQR、前馈、增益调度 |
| 4 | 精读 03 文档 + `lat_controller.cc` / `lon_controller.cc` | 能画出 LAT/LON 调用流程 |
| 5 | 任务 C：LAT/LON 与 MPC 对比 | 一张对比表 + 两组录包 |
| 6 | 参数实验：Q/R、PID、前馈、限幅 | 3～5 组可解释的实验结果 |
| 7 | 复盘：写自己的调参笔记，按仓库规范提交 | 一篇可复用的学习笔记 |

---

## 9. 速查表

```bash
# ===== 构建 =====
./apollo.sh build cyber planning routing control dreamview_plus

# ===== 启动 =====
./scripts/bootstrap.sh start_plus          # DreamView+ 8888
./scripts/bootstrap.sh start               # 经典 DreamView（本仓库也默认 8888）

cyber_launch start modules/planning/planning_component/launch/planning.launch
cyber_launch start modules/routing/launch/routing.launch
cyber_launch start modules/control/control_component/launch/control.launch

# ===== 观察 =====
cyber_node list
cyber_monitor
cyber_monitor -c /apollo/control

source /apollo/cyber/setup.bash
export PYTHONPATH=/apollo:/apollo/bazel-bin:$PYTHONPATH
python3 /apollo/tools/raff/control_probe.py

# ===== 录包 =====
mkdir -p /apollo/data/record
cyber_recorder record -c /apollo/control -c /apollo/planning \
  -c /apollo/localization/pose -c /apollo/canbus/chassis \
  -o /apollo/data/record/control_task.record
cyber_recorder info /apollo/data/record/control_task.record
cyber_recorder play -f /apollo/data/record/control_task.record

# ===== 切换 MPC =====
cp modules/control/control_component/conf/pipeline.pb.txt /tmp/pipeline_lat_lon.pb.txt
cat > modules/control/control_component/conf/pipeline.pb.txt <<'EOF'
controller {
  name: "MPC_CONTROLLER"
  type: "MPCController"
}
EOF
cyber_launch stop  modules/control/control_component/launch/control.launch
cyber_launch start modules/control/control_component/launch/control.launch

# 恢复
cp /tmp/pipeline_lat_lon.pb.txt modules/control/control_component/conf/pipeline.pb.txt
cyber_launch stop  modules/control/control_component/launch/control.launch
cyber_launch start modules/control/control_component/launch/control.launch
```
