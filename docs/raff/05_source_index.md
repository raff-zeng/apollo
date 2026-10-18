# 控制相关源码文件索引

> 基线：当前仓库 `zrf` 分支 HEAD。行号以当前仓库为准。
> 优先级：P0 = 必读；P1 = 理解框架需要；P2 = 按需查阅。

## 1. 推荐阅读顺序

```text
① Control 骨架
   control_component.cc
   control_task.h
   control_task_agent.cc
        ↓
② LAT/LON 默认控制器
   lat_controller.h/.cc
   lon_controller.h/.cc
   linear_quadratic_regulator.cc
   pid_controller.cc
        ↓
③ MPC 插件
   mpc_controller.h
   mpc_controller.cc（Init → ComputeControlCommand → 各子函数）
   proto/mpc_controller.proto
   conf/controller_conf.pb.txt
        ↓
④ 轨迹与误差
   trajectory_analyzer.h/.cc
   control_component/proto/local_view.proto
        ↓
⑤ 优化求解
   mpc_osqp.h/.cc
        ↓
⑥ 执行器与消息
   control_cmd.proto（ControlCommand / SimpleLatDebug / SimpleLonDebug / SimpleMPCDebug）
   calibration_table.proto / calibration_table.pb.txt
        ↓
⑦ 运行与调试
   control.dag / control.launch / control.conf
   cyber/tools/*
```

## 2. Control 模块骨架

| 文件 | 关键内容 | 行号 | 优先级 |
|---|---|---|---|
| [`modules/control/control_component/control_component.cc`](../../modules/control/control_component/control_component.cc) | 组件入口 | 43 `Init` | P0 |
| 同上 | 定时器回调 | 324 `Proc` | P0 |
| 同上 | 输入检查与 estop | 187 `ProduceControlCommand` | P0 |
| 同上 | 输入完整性/时间戳检查 | 529 `CheckInput`、558 `CheckTimestamp` | P1 |
| 同上 | 输出零控制指令 | 648 `ResetAndProduceZeroControlCommand` | P2 |
| [`modules/control/control_component/control_component.h`](../../modules/control/control_component/control_component.h) | 组件声明、reader/writer | — | P1 |
| [`modules/control/control_component/controller_task_base/control_task.h`](../../modules/control/control_component/controller_task_base/control_task.h) | 控制器抽象基类 | 52 类定义；120 `LoadConfig` | P0 |
| [`modules/control/control_component/controller_task_base/control_task_agent.cc`](../../modules/control/control_component/controller_task_base/control_task_agent.cc) | pipeline 控制器加载/顺序执行 | 33 `Init`、56 `ComputeControlCommand`、77 `Reset` | P0 |
| [`modules/control/control_component/controller_task_base/control_task_agent.h`](../../modules/control/control_component/controller_task_base/control_task_agent.h) | Agent 声明 | — | P1 |

## 2.5 LAT/LON 控制器插件

### LAT（横向 LQR）

| 文件 | 关键内容 | 行号 | 优先级 |
|---|---|---|---|
| [`lat_controller.h`](../../modules/control/controllers/lat_based_lqr_controller/lat_controller.h) | 类声明、状态/矩阵成员 | 57 类定义 | P0 |
| [`lat_controller.cc`](../../modules/control/controllers/lat_based_lqr_controller/lat_controller.cc) | 加载配置 | 87 `LoadControlConf` | P0 |
| 同上 | 初始化 | 177 `Init` | P0 |
| 同上 | 主入口 | 304 `ComputeControlCommand` | P0 |
| 同上 | 重置 | 647 `Reset` | P1 |
| 同上 | 状态更新/预览状态 | 655 `UpdateState` | P0 |
| 同上 | 矩阵更新/Tustin | 711 `UpdateMatrix` | P0 |
| 同上 | 预览增广矩阵 | 734 `UpdateMatrixCompound` | P1 |
| 同上 | 曲率前馈 | 747 `ComputeFeedForward` | P0 |
| 同上 | 横向/航向误差 | 773 `ComputeLateralErrors` | P0 |
| 同上 | 倒车方向/B 符号 | 920 `UpdateDrivingOrientation` | P1 |
| [`lat_based_lqr_controller_conf.proto`](../../modules/control/controllers/lat_based_lqr_controller/proto/lat_based_lqr_controller_conf.proto) | 配置字段 | 9 | P0 |
| [`lat 配置`](../../modules/control/controllers/lat_based_lqr_controller/conf/controller_conf.pb.txt) | 默认参数 | 1–104 | P0 |
| [`lat README`](../../modules/control/controllers/lat_based_lqr_controller/README_cn.md) | 官方说明 | — | P1 |

### LON（纵向双环 PID）

| 文件 | 关键内容 | 行号 | 优先级 |
|---|---|---|---|
| [`lon_controller.h`](../../modules/control/controllers/lon_based_pid_controller/lon_controller.h) | 类声明 | 55 类定义 | P0 |
| [`lon_controller.cc`](../../modules/control/controllers/lon_based_pid_controller/lon_controller.cc) | 初始化 | 102 `Init` | P0 |
| 同上 | 主入口 | 169 `ComputeControlCommand` | P0 |
| 同上 | 重置 | 613 `Reset` | P1 |
| 同上 | 纵向误差/预览 | 621 `ComputeLongitudinalErrors` | P0 |
| 同上 | 路径剩余 | 718 `GetPathRemain` | P0 |
| 同上 | 终点停车判断 | 763 `IsStopByDestination` | P1 |
| 同上 | 行人长时间停车 | 785 `IsPedestrianStopLongTerm` | P2 |
| 同上 | 长时间 full stop/EPB | 834 `IsFullStopLongTerm` | P2 |
| 同上 | EPB 分阶段切换 | 865 `SetParkingBrake` | P2 |
| [`lon_based_pid_controller_conf.proto`](../../modules/control/controllers/lon_based_pid_controller/proto/lon_based_pid_controller_conf.proto) | 配置字段 | 12 | P0 |
| [`lon 配置`](../../modules/control/controllers/lon_based_pid_controller/conf/controller_conf.pb.txt) | 默认参数 | 1–92 | P0 |
| [`lon README`](../../modules/control/controllers/lon_based_pid_controller/README_cn.md) | 官方说明 | — | P1 |

### LAT/LON 公共依赖

| 文件 | 关键内容 | 行号 | 优先级 |
|---|---|---|---|
| [`linear_quadratic_regulator.cc`](../../modules/common/math/linear_quadratic_regulator.cc) | DARE/LQR 求解 | 33 / 82 | P0 |
| [`pid_controller.cc`](../../modules/control/control_component/controller_task_base/common/pid_controller.cc) | PID/积分饱和 | 27 `Control` | P0 |
| [`lat_lon_controller_submodule.cc`](../../modules/control/control_component/submodules/lat_lon_controller_submodule.cc) | submodule 调用 | 45、73、123 | P1 |

## 3. MPC 控制器插件

| 文件 | 关键内容 | 行号 | 优先级 |
|---|---|---|---|
| [`modules/control/controllers/mpc_controller/mpc_controller.h`](../../modules/control/controllers/mpc_controller/mpc_controller.h) | 类声明、成员变量 | 57 类定义；191 `horizon_`；340 插件注册 | P0 |
| [`modules/control/controllers/mpc_controller/mpc_controller.cc`](../../modules/control/controllers/mpc_controller/mpc_controller.cc) | 构造/析构 | 65 / 75 | P1 |
| 同上 | 加载配置 | 77 `LoadControlConf` | P0 |
| 同上 | 初始化滤波器 | 180 `InitializeFilters` | P1 |
| 同上 | 初始化 | 196 `Init` | P0 |
| 同上 | 单位换算 | 289 `Wheel2SteerPct` | P0 |
| 同上 | 加载增益调度 | 297 `LoadMPCGainScheduler` | P1 |
| 同上 | **主计算入口** | 337 `ComputeControlCommand` | P0 |
| 同上 | 重置 | 704 `Reset` | P1 |
| 同上 | 标定表插值初始化 | 710 `InitControlCalibrationTable` | P1 |
| 同上 | 状态向量更新 | 724 `UpdateState` | P0 |
| 同上 | 矩阵更新/离散化 | 750 `UpdateMatrix` | P0 |
| 同上 | 曲率前馈 | 767 `FeedforwardUpdate` | P0 |
| 同上 | 横向/航向误差 | 782 `ComputeLateralErrors` | P0 |
| 同上 | 纵向误差（无 preview） | 910 `ComputeLongitudinalErrors` | P0 |
| 同上 | 纵向误差（带 preview） | 971 `ComputeLongitudinalErrors` | P0 |
| 同上 | 路径剩余/full stop | 1059 `GetPathRemain` | P1 |
| [`modules/control/controllers/mpc_controller/proto/mpc_controller.proto`](../../modules/control/controllers/mpc_controller/proto/mpc_controller.proto) | 配置字段定义 | 13 `MPCControllerConf` | P0 |
| [`modules/control/controllers/mpc_controller/conf/controller_conf.pb.txt`](../../modules/control/controllers/mpc_controller/conf/controller_conf.pb.txt) | 默认参数 | 1–149 | P0 |
| [`modules/control/controllers/mpc_controller/mpc_controller_test.cc`](../../modules/control/controllers/mpc_controller/mpc_controller_test.cc) | 误差计算单测 | 86 测试用例 | P1 |
| [`modules/control/controllers/mpc_controller/BUILD`](../../modules/control/controllers/mpc_controller/BUILD) | 构建规则 | — | P1 |
| [`modules/control/controllers/mpc_controller/plugins.xml`](../../modules/control/controllers/mpc_controller/plugins.xml) | 插件注册描述 | — | P1 |
| [`modules/control/controllers/mpc_controller/cyberfile.xml`](../../modules/control/controllers/mpc_controller/cyberfile.xml) | 包依赖 | — | P2 |
| [`modules/control/controllers/mpc_controller/README_cn.md`](../../modules/control/controllers/mpc_controller/README_cn.md) | 官方说明 | — | P1 |

## 4. 轨迹分析

| 文件 | 关键内容 | 行号 | 优先级 |
|---|---|---|---|
| [`modules/control/control_component/controller_task_base/common/trajectory_analyzer.h`](../../modules/control/control_component/controller_task_base/common/trajectory_analyzer.h) | 接口声明 | — | P0 |
| [`.../trajectory_analyzer.cc`](../../modules/control/control_component/controller_task_base/common/trajectory_analyzer.cc) | 按位置匹配路径点 | 72 `QueryMatchedPathPoint` | P0 |
| 同上 | **Frenet 转换** | 109 `ToTrajectoryFrame` | P0 |
| 同上 | 按绝对时间取点 | 154 `QueryNearestPointByAbsoluteTime` | P0 |
| 同上 | 按相对时间取点 | 159 `QueryNearestPointByRelativeTime` | P0 |
| 同上 | 按位置取最近轨迹点 | 188 `QueryNearestPointByPosition` | P0 |
| 同上 | 线段内最小距离插值 | 208 `FindMinDistancePoint` | P1 |
| 同上 | 轨迹平移到 COM | 242 `TrajectoryTransformToCOM` | P0 |
| 同上 | 计算 COM 位置 | 253 `ComputeCOMPosition` | P1 |
| [`modules/control/control_component/controller_task_base/common/dependency_injector.h`](../../modules/control/control_component/controller_task_base/common/dependency_injector.h) | 依赖注入（车辆状态等） | — | P1 |

## 5. QP 求解器

| 文件 | 关键内容 | 行号 | 优先级 |
|---|---|---|---|
| [`modules/common/math/mpc_osqp.h`](../../modules/common/math/mpc_osqp.h) | 求解器接口 | 33 类定义 | P0 |
| [`modules/common/math/mpc_osqp.cc`](../../modules/common/math/mpc_osqp.cc) | 构造/维度计算 | 22 | P0 |
| 同上 | 构造 P（Q/R 对角） | 53 `CalculateKernel` | P0 |
| 同上 | 构造 q（`-Q*x_ref`） | 95 `CalculateGradient` | P0 |
| 同上 | 构造约束矩阵 A | 108 `CalculateEqualityConstraint` | P0 |
| 同上 | 构造上下界 l/u | 180 `CalculateConstraintVectors` | P0 |
| 同上 | OSQP 设置 | 219 `Settings` | P1 |
| 同上 | OSQP 数据装配 | 236 `Data` | P0 |
| 同上 | 求解并取第一步控制 | 281 `Solve` | P0 |
| [`modules/common/math/mpc_osqp_test.cc`](../../modules/common/math/mpc_osqp_test.cc) | 求解器单测 | — | P2 |

## 6. Control 子模块与配置

| 文件 | 关键内容 | 行号 | 优先级 |
|---|---|---|---|
| [`modules/control/control_component/submodules/mpc_controller_submodule.cc`](../../modules/control/control_component/submodules/mpc_controller_submodule.cc) | 插件创建/初始化 | 48 `Init` | P1 |
| 同上 | 组件回调 | 66 `Proc` | P1 |
| 同上 | 调用 MPC 计算 | 117 `ProduceControlCoreCommand` | P1 |
| [`modules/control/control_component/submodules/preprocessor_submodule.cc`](../../modules/control/control_component/submodules/preprocessor_submodule.cc) | 预处理 | 62 `Proc` | P1 |
| [`modules/control/control_component/submodules/postprocessor_submodule.cc`](../../modules/control/control_component/submodules/postprocessor_submodule.cc) | 后处理/发布 | 49 `Proc` | P1 |
| [`modules/control/control_component/conf/pipeline.pb.txt`](../../modules/control/control_component/conf/pipeline.pb.txt) | pipeline 控制器列表 | — | P0 |
| [`modules/control/control_component/conf/control.conf`](../../modules/control/control_component/conf/control.conf) | 全局 flags | — | P0 |
| [`modules/control/control_component/conf/calibration_table.pb.txt`](../../modules/control/control_component/conf/calibration_table.pb.txt) | 纵向标定表 | — | P1 |
| [`modules/control/control_component/common/control_gflags.cc`](../../modules/control/control_component/common/control_gflags.cc) | flags 默认值 | — | P1 |
| [`modules/control/control_component/common/control_gflags.h`](../../modules/control/control_component/common/control_gflags.h) | flags 声明 | — | P1 |
| [`modules/control/control_component/dag/control.dag`](../../modules/control/control_component/dag/control.dag) | 默认 DAG | — | P1 |
| [`modules/control/control_component/dag/mpc_module.dag`](../../modules/control/control_component/dag/mpc_module.dag) | MPC submodule DAG | — | P1 |
| [`modules/control/control_component/launch/control.launch`](../../modules/control/control_component/launch/control.launch) | 默认 launch | — | P1 |
| [`modules/control/control_component/launch/control_mpc_control.launch`](../../modules/control/control_component/launch/control_mpc_control.launch) | MPC launch | — | P1 |
| [`modules/control/control_component/proto/pipeline.proto`](../../modules/control/control_component/proto/pipeline.proto) | pipeline 消息 | — | P1 |
| [`modules/control/control_component/proto/calibration_table.proto`](../../modules/control/control_component/proto/calibration_table.proto) | 标定表消息 | — | P1 |
| [`modules/control/control_component/proto/gain_scheduler_conf.proto`](../../modules/control/control_component/proto/gain_scheduler_conf.proto) | 增益调度消息 | — | P1 |
| [`modules/control/control_component/proto/pid_conf.proto`](../../modules/control/control_component/proto/pid_conf.proto) | PID 配置 | — | P2 |
| [`modules/control/control_component/proto/leadlag_conf.proto`](../../modules/control/control_component/proto/leadlag_conf.proto) | LeadLag 配置 | — | P2 |

## 7. 相关基础库

| 文件 | 内容 | 优先级 |
|---|---|---|
| [`modules/common/filters/digital_filter.cc`](../../modules/common/filters/digital_filter.cc) | 数字滤波器实现 | P1 |
| [`modules/common/filters/digital_filter_coefficients.cc`](../../modules/common/filters/digital_filter_coefficients.cc) | 低通系数生成 | P1 |
| [`modules/common/filters/mean_filter.h`](../../modules/common/filters/mean_filter.h) | 均值滤波 | P2 |
| [`modules/common/math/math_utils.h`](../../modules/common/math/math_utils.h) | `NormalizeAngle`、`Clamp`、`lerp` | P1 |
| [`modules/common/math/linear_interpolation.h`](../../modules/common/math/linear_interpolation.h) | 线性插值/slerp | P1 |
| [`modules/common/vehicle_state/vehicle_state_provider.cc`](../../modules/common/vehicle_state/vehicle_state_provider.cc) | 车辆状态、COM 位置 | P1 |
| [`modules/common/configs/vehicle_config_helper.cc`](../../modules/common/configs/vehicle_config_helper.cc) | 车辆参数加载 | P1 |
| [`modules/control/control_component/controller_task_base/common/interpolation_1d.cc`](../../modules/control/control_component/controller_task_base/common/interpolation_1d.cc) | 一维插值（增益调度） | P1 |
| [`modules/control/control_component/controller_task_base/common/interpolation_2d.cc`](../../modules/control/control_component/controller_task_base/common/interpolation_2d.cc) | 二维插值（标定表） | P1 |
| [`modules/control/control_component/controller_task_base/common/pid_controller.cc`](../../modules/control/control_component/controller_task_base/common/pid_controller.cc) | 加速度 PID | P2 |
| [`modules/control/control_component/controller_task_base/common/leadlag_controller.cc`](../../modules/control/control_component/controller_task_base/common/leadlag_controller.cc) | LeadLag 补偿 | P2 |

## 8. 消息定义

| 文件 | 消息 | 优先级 |
|---|---|---|
| [`modules/common_msgs/control_msgs/control_cmd.proto`](../../modules/common_msgs/control_msgs/control_cmd.proto) | `ControlCommand`（26 行起）、`SimpleLongitudinalDebug`（76 行起）、`SimpleLateralDebug`（121 行起）、`SimpleMPCDebug`（179 行起） | P0 |
| [`modules/common_msgs/planning_msgs/planning.proto`](../../modules/common_msgs/planning_msgs/planning.proto) | `ADCTrajectory`、`TrajectoryPoint` | P0 |
| [`modules/common_msgs/basic_msgs/pnc_point.proto`](../../modules/common_msgs/basic_msgs/pnc_point.proto) | `PathPoint`、`TrajectoryPoint` | P0 |
| [`modules/common_msgs/localization_msgs/localization.proto`](../../modules/common_msgs/localization_msgs/localization.proto) | `LocalizationEstimate` | P1 |
| [`modules/common_msgs/chassis_msgs/chassis.proto`](../../modules/common_msgs/chassis_msgs/chassis.proto) | `Chassis`、挡位、驾驶模式 | P1 |
| [`modules/common_msgs/config_msgs/vehicle_config.proto`](../../modules/common_msgs/config_msgs/vehicle_config.proto) | `VehicleParam`（50 行起） | P1 |
| [`modules/common_msgs/control_msgs/pad_msg.proto`](../../modules/common_msgs/control_msgs/pad_msg.proto) | 驾驶模式/使能消息 | P2 |

## 9. 官方文档与工具

| 文件/工具 | 内容 | 优先级 |
|---|---|---|
| [`modules/control/control_component/README_cn.md`](../../modules/control/control_component/README_cn.md) | Control 组件架构、目录、输入输出 | P0 |
| [`modules/control/controllers/mpc_controller/README_cn.md`](../../modules/control/controllers/mpc_controller/README_cn.md) | MPC 插件说明、配置、启动 | P0 |
| [`docs/10_Control/dynamic_model.md`](../10_Control/dynamic_model.md) | 车辆动力学模型 | P1 |
| [`docs/10_Control/how_to_tune_control_parameters_cn.md`](../10_Control/how_to_tune_control_parameters_cn.md) | 控制参数调优 | P1 |
| [`docs/10_Control/how_to_add_a_new_control_algorithm_cn.md`](../10_Control/how_to_add_a_new_control_algorithm_cn.md) | 新增控制器 | P1 |
| [`docs/04_CyberRT/CyberRT_Developer_Tools.md`](../04_CyberRT/CyberRT_Developer_Tools.md) | `cyber_monitor` / `cyber_recorder` | P1 |
| [`docs/04_CyberRT/CyberRT_Quick_Start_cn.md`](../04_CyberRT/CyberRT_Quick_Start_cn.md) | CyberRT 入门 | P2 |
| `cyber/tools/cyber_monitor/` | 终端 channel 监视 | P1 |
| `cyber/tools/cyber_recorder/` | 录制/回放 | P1 |
| `cyber/tools/cyber_launch/` | 启动 DAG | P1 |

## 10. 一页速查：MPC 关键数据流

```text
ADCTrajectory ──┐
Localization  ──┼─→ VehicleState ─→ ComputeLateralErrors ─→ e_y, e_y_dot, e_psi, e_psi_dot
Chassis       ──┘                 └→ ComputeLongitudinalErrors ─→ e_s, e_v
                                              │
                                              ▼
                                    matrix_state_ (6×1)
                                              │
                     A_d, B_d, Q, R, bounds ──┼──→ MpcOsqp::Solve
                                              │
                                              ▼
                              control_cmd = [δ(rad), a(m/s²)]
                                              │
                 ┌────────────────────────────┴────────────────────────────┐
                 ▼                                                         ▼
        Wheel2SteerPct + 前馈/补偿/限幅/滤波                    + a_ref + 坡度补偿
                 │                                                         │
                 ▼                                                         ▼
         steering_target (%)                              acceleration_lookup
                                                                           │
                                                                           ▼
                                                              2D 标定表 → throttle/brake (%)
                                                                           │
                                                                           ▼
                                                                 ControlCommand
```

## 11. 按问题定位文件

| 我想知道…… | 去看 |
|---|---|
| LAT/LON 怎么被加载的 | `control_task_agent.cc`、`pipeline.pb.txt`、两个插件的 `plugins.xml`/`BUILD` |
| LAT 的 LQR 增益怎么来的 | `lat_controller.cc` 的 `UpdateMatrix`、`UpdateMatrixCompound`、`SolveLQRProblem` |
| LAT 的曲率前馈怎么算 | `lat_controller.cc` 的 `ComputeFeedForward` |
| LON 的双环 PID 怎么串的 | `lon_controller.cc` 169–295、`pid_controller.cc` |
| LON 的标定表怎么用 | `lon_controller.cc` 455–515、`calibration_table.pb.txt` |
| LON 的停车逻辑 | `GetPathRemain`、`IsStopByDestination`、`IsFullStopLongTerm` |
| 怎么切换 LAT/LON 和 MPC | `pipeline.pb.txt`（运行时读取，重启 control 生效） |
| MPC 怎么被加载的 | `control_task_agent.cc`、`plugins.xml`、`BUILD` |
| MPC 配置参数在哪里定义 | `proto/mpc_controller.proto`、`conf/controller_conf.pb.txt` |
| MPC 误差怎么算 | `ComputeLateralErrors`、`ComputeLongitudinalErrors`、`trajectory_analyzer.cc` |
| MPC 预测模型矩阵怎么来的 | `Init`、`UpdateMatrix`、`mpc_controller.h` |
| MPC 代价函数/约束怎么拼的 | `mpc_osqp.cc` 的 `CalculateKernel`、`CalculateGradient`、`CalculateEqualityConstraint` |
| MPC 求解器怎么配置 | `mpc_osqp.cc` 的 `Settings` |
| MPC 转向指令怎么来的 | `ComputeControlCommand` 486–562、`FeedforwardUpdate` |
| MPC 油门/刹车怎么来的 | `ComputeControlCommand` 625–680、`calibration_table.pb.txt` |
| MPC 停车逻辑 | `GetPathRemain`、`is_full_stop` 分支 |
| 怎么调试 | `SimpleLateralDebug` / `SimpleLongitudinalDebug` / `SimpleMPCDebug`、`cyber_monitor`、`cyber_recorder` |
