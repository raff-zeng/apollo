# MPC 控制器源码学习笔记

> 阅读基线：当前仓库 `zrf` 分支 HEAD。行号以当前仓库为准。
> 本文所有路径默认相对仓库根目录 `/home/zrf/apollo`。

## 目录

- [0. 一句话总结](#0-一句话总结)
- [1. MPC 在 Control 模块中的位置](#1-mpc-在-control-模块中的位置)
- [2. 文件结构](#2-文件结构)
- [3. 一次控制周期的总流程](#3-一次控制周期的总流程)
- [4. 坐标系与横纵向误差](#4-坐标系与横纵向误差)
- [5. 预测模型](#5-预测模型)
- [6. 代价函数](#6-代价函数)
- [7. 约束](#7-约束)
- [8. 从最优解到执行器](#8-从最优解到执行器)
- [9. 代码调用流程（逐函数）](#9-代码调用流程逐函数)
- [10. 参数与调参](#10-参数与调参)
- [11. 源码阅读注意点（坑）](#11-源码阅读注意点坑)
- [12. 动手实验](#12-动手实验)
- [13. 术语表](#13-术语表)

---

## 0. 一句话总结

Apollo 的 MPC 控制器把车辆横向/纵向跟踪问题写成：

> **线性二自由度自行车模型的误差状态方程 + 二次型代价函数 + 控制量/状态约束 + OSQP 求解**。

每个控制周期：

1. 用定位、底盘和规划轨迹计算当前误差状态
   `x = [横向误差, 横向误差变化率, 航向误差, 航向误差变化率, 纵向位置误差, 速度误差]`；
2. 以当前 `x` 为初值，预测未来 `N = 10` 步；
3. 求解使代价最小的控制序列 `[前轮转角, 加速度]`；
4. 只取第一步，叠加曲率前馈、限幅、低通滤波，再通过标定表转成
   `steering_target`、`throttle`、`brake`。

---

## 1. MPC 在 Control 模块中的位置

### 1.1 Control 的两条运行路径

Control 模块的入口是
[`ControlComponent`](../../modules/control/control_component/control_component.cc)，
它是一个 `cyber::TimerComponent`，默认每 10 ms 执行一次 `Proc()`。

Control 有两种组织控制器的方式：

#### 路径 A：pipeline 模式（默认）

```text
ControlComponent::Proc()
  └── ControlTaskAgent::ComputeControlCommand()
        ├── LatController   （LQR 横向）
        ├── LonController   （PID 纵向）
        └── MPCController   （如果配置了）
```

- 控制器从
  [`pipeline.pb.txt`](../../modules/control/control_component/conf/pipeline.pb.txt)
  读取，顺序执行。
- `FLAGS_use_control_submodules` 默认为 `false`，所以默认走这条路径。
- 当前仓库的 `pipeline.pb.txt` 只有 `LatController + LonController`，
  **MPC 默认没有启用**。

#### 路径 B：submodule 模式

```text
ControlComponent::Proc()
  └── 发布 /apollo/control/localview
        └── PreprocessorSubmodule
              └── 发布 /apollo/control/preprocessor
                    └── MPCControllerSubmodule
                          └── 发布 /apollo/control/controlcore
                                └── PostprocessorSubmodule
                                      └── 发布 /apollo/control
```

- 由
  [`mpc_module.dag`](../../modules/control/control_component/dag/mpc_module.dag)
  装配。
- 需要把 `control.conf` 里的 `--use_control_submodules` 改成 `true`。
- 注意：该 DAG 和对应 launch 文件中的部分路径仍是旧目录结构，直接启动会找不到
  模块库或配置文件，使用前需要修正（见第 11 节）。

### 1.2 如何启用 MPC

#### 方式一：pipeline 模式（推荐入门）

编辑
[`pipeline.pb.txt`](../../modules/control/control_component/conf/pipeline.pb.txt)，
只保留 MPC：

```text
controller {
  name: "MPC_CONTROLLER"
  type: "MPCController"
}
```

然后重新构建并启动：

```bash
./apollo.sh build control
cyber_launch start modules/control/control_component/launch/control.launch
```

> 不建议把 MPC 和 LAT/LON 同时放在 pipeline 里：`ControlTaskAgent` 会顺序执行，
> 后面的控制器可能覆盖前面写入的 `steering_target`、`throttle`、`brake`、
> `acceleration`。如果确实要组合，务必确认字段覆盖关系。

#### 方式二：submodule 模式

1. 修改 `modules/control/control_component/conf/control.conf`：

   ```text
   --use_control_submodules=true
   ```

2. 修正
   [`mpc_module.dag`](../../modules/control/control_component/dag/mpc_module.dag)
   中的旧路径：
   - `modules/control/libcontrol_component.so`
     → `modules/control/control_component/libcontrol_component.so`
   - `/apollo/modules/control/conf/control.conf`
     → `/apollo/modules/control/control_component/conf/control.conf`

3. 修正
   [`control_mpc_control.launch`](../../modules/control/control_component/launch/control_mpc_control.launch)
   中的 DAG 路径：
   `/apollo/modules/control/dag/mpc_module.dag`
   → `/apollo/modules/control/control_component/dag/mpc_module.dag`。

4. 启动：

   ```bash
   cyber_launch start modules/control/control_component/launch/control_mpc_control.launch
   ```

### 1.3 插件机制

`MPCController` 继承自
[`ControlTask`](../../modules/control/control_component/controller_task_base/control_task.h)，
实现 5 个虚函数：

- `Init(injector)`
- `ComputeControlCommand(localization, chassis, trajectory, cmd)`
- `Reset()`
- `Stop()`
- `Name()`

注册为 CyberRT 插件：

```cpp
// mpc_controller.h:340
CYBER_PLUGIN_MANAGER_REGISTER_PLUGIN(apollo::control::MPCController,
                                     ControlTask)
```

插件描述在
[`plugins.xml`](../../modules/control/controllers/mpc_controller/plugins.xml)：

```xml
<library path="modules/control/controllers/mpc_controller/libmpc_controller.so">
  <class type="apollo::control::MPCController"
         base_class="apollo::control::ControlTask"></class>
</library>
```

`ControlTaskAgent` 通过 `PluginManager::CreateInstance<ControlTask>()`
按类名创建实例，再调用 `Init()`。

控制器配置由 `ControlTask::LoadConfig<T>()` 通过插件管理器定位：
默认读取插件包下的 `conf/controller_conf.pb.txt`。
因此改配置不需要改代码，但改 `proto` 字段需要重新编译。

### 1.4 输入与输出

| 方向 | 名称 | 类型 | 用途 |
|---|---|---|---|
| 输入 | `/apollo/planning` | `planning::ADCTrajectory` | 参考轨迹：位置、航向、曲率、速度、加速度、时间 |
| 输入 | `/apollo/localization/pose` | `localization::LocalizationEstimate` | 车辆世界坐标位姿 |
| 输入 | `/apollo/canbus/chassis` | `canbus::Chassis` | 底盘速度、转向、挡位、驾驶模式 |
| 输入 | 内部 | `common::VehicleState` | 由定位+底盘融合出的车辆状态 |
| 输出 | `/apollo/control` | `control::ControlCommand` | 转向百分比、油门、刹车、加速度、挡位、调试信息 |

MPC 的调试信息写在
`ControlCommand.debug.simple_mpc_debug`，消息定义见
[`control_cmd.proto:179`](../../modules/common_msgs/control_msgs/control_cmd.proto#L179)。

> 注意：`ControlComponent::Proc` 只有在 `chassis.driving_mode == COMPLETE_AUTO_DRIVE`
> 时才会调用 `ControlTaskAgent` / `MPCController`；否则走
> `ResetAndProduceZeroControlCommand`，输出零控制指令。播包调试 MPC 时，
> 确认底盘消息中的驾驶模式，或在仿真中先使能自动驾驶。

---

## 2. 文件结构

### 2.1 MPC 插件包

```text
modules/control/controllers/mpc_controller/
├── BUILD                       # apollo_plugin 构建规则
├── cyberfile.xml               # 包管理依赖
├── plugins.xml                 # 插件注册描述
├── mpc_controller.h            # 类声明、成员变量
├── mpc_controller.cc           # 控制器实现（1111 行）
├── mpc_controller_test.cc      # 单元测试（误差计算）
├── mpc_controller_test_data/   # 测试用 localization/chassis/planning
├── proto/
│   └── mpc_controller.proto    # MPCControllerConf 配置定义
├── conf/
│   └── controller_conf.pb.txt  # 默认配置
├── README_cn.md                # 官方说明
└── docs/images/                # 结构图
```

### 2.2 关键文件与职责

| 文件 | 行数 | 职责 | 阅读优先级 |
|---|---:|---|---|
| [`mpc_controller.h`](../../modules/control/controllers/mpc_controller/mpc_controller.h) | 344 | 类声明、状态矩阵/权重/滤波器等成员 | P0 |
| [`mpc_controller.cc`](../../modules/control/controllers/mpc_controller/mpc_controller.cc) | 1111 | 初始化、误差计算、矩阵更新、QP 调用、执行器转换 | P0 |
| [`proto/mpc_controller.proto`](../../modules/control/controllers/mpc_controller/proto/mpc_controller.proto) | 69 | 配置字段定义 | P0 |
| [`conf/controller_conf.pb.txt`](../../modules/control/controllers/mpc_controller/conf/controller_conf.pb.txt) | 149 | 默认参数：`ts`、`cf/cr`、`Q/R`、增益调度 | P0 |
| [`mpc_osqp.h`](../../modules/common/math/mpc_osqp.h) | 102 | QP 求解器封装接口 | P0 |
| [`mpc_osqp.cc`](../../modules/common/math/mpc_osqp.cc) | 344 | 把 MPC 问题拼成 OSQP 标准形式 | P0 |
| [`mpc_controller_submodule.cc`](../../modules/control/control_component/submodules/mpc_controller_submodule.cc) | 134 | submodule 模式下的插件调用 | P1 |
| [`trajectory_analyzer.cc`](../../modules/control/control_component/controller_task_base/common/trajectory_analyzer.cc) | 271 | 轨迹匹配、Frenet 转换、COM 平移 | P0 |
| [`control_task.h`](../../modules/control/control_component/controller_task_base/control_task.h) | 141 | 控制器基类与配置加载 | P1 |
| [`control_task_agent.cc`](../../modules/control/control_component/controller_task_base/control_task_agent.cc) | 82 | pipeline 控制器加载与顺序执行 | P1 |
| [`control_component.cc`](../../modules/control/control_component/control_component.cc) | 700+ | 组件入口、输入检查、estop、发布 | P1 |

### 2.3 调用关系总图

```text
cyber::TimerComponent (ControlComponent)
  │
  ├─ pipeline 模式
  │    └─ ControlTaskAgent
  │         └─ MPCController::ComputeControlCommand
  │              ├─ TrajectoryAnalyzer
  │              ├─ ComputeLongitudinalErrors
  │              ├─ ComputeLateralErrors
  │              ├─ UpdateState
  │              ├─ UpdateMatrix
  │              ├─ FeedforwardUpdate
  │              ├─ MpcOsqp::Solve
  │              │    ├─ CalculateGradient
  │              │    ├─ CalculateConstraintVectors
  │              │    ├─ CalculateKernel
  │              │    ├─ CalculateEqualityConstraint
  │              │    └─ osqp_solve
  │              └─ 限幅/滤波/标定表/写 ControlCommand
  │
  └─ submodule 模式
       ├─ PreprocessorSubmodule
       ├─ MPCControllerSubmodule
       │    └─ MPCController::ComputeControlCommand
       └─ PostprocessorSubmodule
```

---

## 3. 一次控制周期的总流程

以 pipeline 模式为例，`MPCController::ComputeControlCommand`
（[`mpc_controller.cc:337`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L337)）
的执行顺序：

1. **构造轨迹分析器**
   `trajectory_analyzer_ = std::move(TrajectoryAnalyzer(planning_trajectory))`。
   轨迹点被拷贝到 `trajectory_points_`，并补齐缺失的 `z`。

2. **按需把轨迹平移到质心（COM）**
   如果 `trajectory_transform_to_com_*` 打开，调用
   `TrajectoryTransformToCOM(lr_)`，把参考点从后轴中心沿航向平移 `lr_`。

3. **倒车时重建模型**
   挡位为 `GEAR_REVERSE` 时，把 `cf_`、`cr_` 取反，并修改 `matrix_a_(0,1)`。

4. **清空调试信息**
   `debug->Clear()`。

5. **计算纵向误差**
   根据 `use_preview_` 选择两个重载之一，填充
   `station_error`、`speed_error`、`acceleration_reference` 等。

6. **更新状态向量**
   `UpdateState(debug)`：计算横向/航向误差，写入 `matrix_state_`。

7. **更新离散矩阵**
   `UpdateMatrix(debug)`：用当前速度 `v` 更新 `A`，用 Tustin 公式算 `A_d`。

8. **计算转向前馈**
   `FeedforwardUpdate(debug)`：由曲率 `kappa` 和速度 `v` 算稳态前轮转角。

9. **应用增益调度**
   如果 `FLAGS_enable_gain_scheduler` 为真，按速度插值缩放
   `Q(0,0)`、`Q(2,2)`、`R(0,0)` 和前馈项。

10. **构造 QP 并求解**
    调用 `MpcOsqp::Solve(&control_cmd)`，得到第一步的
    `[前轮转角(rad), 加速度(m/s²)]`。

11. **后处理**
    转向：转成百分比 → 加前馈/补偿/LeadLag → 横向加速度限幅 → 低通滤波 → 限幅 ±100。
    加速度：加参考加速度和坡度补偿 → 可选 PID → 标定表 → 油门/刹车。
    停车：接近终点时用 `standstill_acceleration_` 覆盖并 `Reset()`。

12. **写输出**
    `cmd->set_steering_target()`、`set_throttle()`、`set_brake()`、
    `set_acceleration()`、`set_gear_location()`，并填充 `SimpleMPCDebug`。

---

## 4. 坐标系与横纵向误差

### 4.1 坐标约定

- 世界坐标系：右手系，通常 `x` 轴向东、`y` 轴向北，航向角 `theta` 从 `x` 轴逆时针为正。
- 轨迹坐标系（Frenet）：沿参考线方向为纵向 `s`，垂直参考线方向为横向 `d`。
- 车辆参考点：Apollo 的 `VehicleParam` 注释明确写明
  「Car center point is car reference point, i.e., center of rear axle」，
  即车辆状态默认以后轴中心为参考点。
- 动力学模型通常以质心（COM）为参考，因此代码里会出现
  `ComputeCOMPosition(lr_)` 和 `TrajectoryTransformToCOM(lr_)`。

### 4.2 横向误差与航向误差

[`ComputeLateralErrors`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L782)
的核心公式：

```cpp
matched_point = trajectory_analyzer.QueryNearestPointByPosition(x, y);
dx = x - matched_point.x;
dy = y - matched_point.y;
lateral_error = cos(theta_r) * dy - sin(theta_r) * dx;
heading_error = NormalizeAngle(theta - theta_r);
```

写成数学形式：

\[
e_y = \cos\theta_r\,(y-y_r) - \sin\theta_r\,(x-x_r)
\]

\[
e_\psi = \mathrm{NormalizeAngle}(\theta-\theta_r)
\]

其中 `(x_r, y_r, theta_r)` 是轨迹上离车辆最近的匹配点。

**几何意义**：`e_y` 是车辆位置相对参考航向的横向有符号距离。
在参考航向为 `+x` 时，`e_y > 0` 表示车辆位于参考线左侧。

代码随后计算：

\[
\dot e_y = v\sin(e_\psi)
\]

```cpp
// mpc_controller.cc:859
double lateral_error_dot = linear_v * sin_delta_theta;
```

以及航向误差变化率：

\[
\dot e_\psi = \omega - \kappa_r v_r
\]

```cpp
// mpc_controller.cc:886-888
debug->set_ref_heading_rate(debug->curvature() * matched_point.v());
debug->set_heading_error_rate(debug->heading_rate() - debug->ref_heading_rate());
```

其中：

- `curvature()` 是匹配点的参考曲率 `kappa_r`；
- `matched_point.v()` 是匹配点的参考速度；
- `heading_rate()` 在前进时取底盘角速度 `angular_v`，倒车时取 `-angular_v`。

### 4.3 纵向误差：Frenet 转换

[`TrajectoryAnalyzer::ToTrajectoryFrame`](../../modules/control/control_component/controller_task_base/common/trajectory_analyzer.cc#L109)
把车辆位姿投影到参考轨迹：

$$ d = \cos\theta_r\,(y-y_r) - \sin\theta_r\,(x-x_r) $$

$$ s = s_r + \cos\theta_r\,(x-x_r) + \sin\theta_r\,(y-y_r) $$

$$ \dot d = v\sin(\theta-\theta_r) $$

$$ \dot s = \frac{v\cos(\theta-\theta_r)}{1-\kappa_r d} $$

最后一行来自曲线坐标下的弧长关系：`1 - kappa_r * d` 是参考线在横向偏移 `d`
处的比例因子。代码对 `1 - kappa_r * d <= 0` 做了保护，把它置为 `0.01`，避免除零或符号翻转。

在
[`ComputeLongitudinalErrors`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L910)
中：

```cpp
matched_point = QueryMatchedPathPoint(x, y);      // 按位置找最近点
ToTrajectoryFrame(..., &s_matched, &s_dot_matched, ...);
reference_point = QueryNearestPointByAbsoluteTime(now);
station_error = reference_point.path_point().s() - s_matched;
speed_error   = reference_point.v() - s_dot_matched;
```

注意两个「参考点」的来源不同：

- **匹配点** `matched_point`：按车辆当前位置找最近轨迹点，用于求当前 `s`、`d`；
- **参考点** `reference_point`：按当前绝对时间找轨迹点，用于取参考 `s_ref`、`v_ref`、`a_ref`。

这样做是因为规划轨迹带有时间信息，控制器需要跟踪「当前时刻应该到达的位置」，
而不是单纯跟踪几何上最近的点。

### 4.4 纵向加速度与 jerk

```cpp
lon_speed = v * cos(heading_error);
lon_acceleration = a * cos(heading_error);
one_minus_kappa_lat_error = 1 - kappa_ref * v * sin(heading_error);
acceleration_error = a_ref - lon_acceleration / one_minus_kappa_lat_error;
jerk_reference = (a_ref - previous_a_ref) / ts;
lon_jerk = (a_feedback - previous_a) / ts;
jerk_error = jerk_reference - lon_jerk / one_minus_kappa_lat_error;
```

这些量主要用于调试和评价，不直接进入 MPC 的 6 维状态。

### 4.5 预览点

`ComputeLongitudinalErrors` 的带 `preview_time` 重载还会计算：

```text
preview_point = QueryNearestPointByAbsoluteTime(now + preview_time)
preview_station_error = preview_point.s - s_matched
preview_speed_error   = preview_point.v - s_dot_matched
preview_speed_reference / preview_acceleration_reference
```

`preview_time_ = preview_window_ * ts_`。默认 `preview_window = 0`，
所以预览点与当前参考点相同。

### 4.6 COM 与后轴的一致性

车辆状态提供两套位置：

- `vehicle_state->x()/y()`：后轴中心（默认参考点）；
- `vehicle_state->ComputeCOMPosition(lr_)`：质心位置。

`UpdateState` 用后者计算横向误差：

```cpp
const auto &com = injector_->vehicle_state()->ComputeCOMPosition(lr_);
ComputeLateralErrors(com.x(), com.y(), ...);
```

而 `ComputeLongitudinalErrors` 用的是后轴中心 `vehicle_state->x()/y()`。
这种不对称是有意为之：横向动力学模型以质心为参考，纵向 `s` 则与规划轨迹的
后轴参考点保持一致。

`ComputeCOMPosition` 是否真的平移，取决于
`FLAGS_state_transform_to_com_drive` / `FLAGS_state_transform_to_com_reverse`
（`control.conf` 中两者都是 `true`）。
而轨迹是否平移，取决于 MPC 配置中的
`trajectory_transform_to_com_drive/reverse`，MPC 默认配置没有设置它们（默认 `false`）。
如果规划轨迹本身是后轴参考点，而车辆位置被平移到 COM，两者之间会存在
约 `lr_` 的常值偏置。实际调试时如果发现横向误差有明显常值，建议先核对这一组开关。

---

## 5. 预测模型

### 5.1 建模假设

Apollo MPC 使用**线性二自由度自行车模型**的误差形式，假设：

1. 纵向速度 `v` 在一个预测周期内近似恒定；
2. 轮胎侧偏力与侧偏角成线性关系（侧偏刚度 `Cf`、`Cr` 为常数）；
3. 小角度近似：`sin(θ) ≈ θ`、`cos(θ) ≈ 1`；
4. 忽略空气阻力、侧倾、载荷转移等；
5. 以质心为横向动力学参考点。

### 5.2 状态量与控制量

状态向量（6 维）：

\[
x =
\begin{bmatrix}
e_y\\
\dot e_y\\
e_\psi\\
\dot e_\psi\\
e_s\\
e_v
\end{bmatrix}
=
\begin{bmatrix}
\text{横向误差}\\
\text{横向误差变化率}\\
\text{航向误差}\\
\text{航向误差变化率}\\
\text{纵向位置误差}\\
\text{速度误差}
\end{bmatrix}
\]

控制向量（2 维）：

\[
u =
\begin{bmatrix}
\delta_f\\
a
\end{bmatrix}
=
\begin{bmatrix}
\text{前轮转角(rad)}\\
\text{纵向加速度}(m/s^2)
\end{bmatrix}
\]

### 5.3 连续时间模型

代码在
[`Init`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L216)
中初始化 `A`、`B`、`C`，并在每个周期用
[`UpdateMatrix`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L750)
更新与速度相关的项。

#### A 矩阵

\[
A=
\begin{bmatrix}
0 & 1 & 0 & 0 & 0 & 0\\
0 & -\dfrac{C_f+C_r}{m v} & \dfrac{C_f+C_r}{m} & \dfrac{l_rC_r-l_fC_f}{m v} & 0 & 0\\
0 & 0 & 0 & 1 & 0 & 0\\
0 & \dfrac{l_rC_r-l_fC_f}{I_z v} & \dfrac{l_fC_f-l_rC_r}{I_z} & -\dfrac{l_f^2C_f+l_r^2C_r}{I_z v} & 0 & 0\\
0 & 0 & 0 & 0 & 0 & 1\\
0 & 0 & 0 & 0 & 0 & 0
\end{bmatrix}
\]

#### B 矩阵

\[
B=
\begin{bmatrix}
0 & 0\\
\dfrac{C_f}{m} & 0\\
0 & 0\\
\dfrac{l_fC_f}{I_z} & 0\\
0 & 0\\
0 & -1
\end{bmatrix}
\]

#### C 向量（参考曲率耦合项）

\[
C=
\begin{bmatrix}
0\\
\dfrac{l_rC_r-l_fC_f}{m v}-v\\
0\\
-\dfrac{l_f^2C_f+l_r^2C_r}{I_z v}\\
0\\
0
\end{bmatrix}
\]

完整连续模型：

\[
\dot x = A x + B u + C\,\dot\psi_{ref}
\]

#### 5.3.1 从二自由度自行车模型推导

在车身坐标下，设纵向速度 \(v_x \approx v\) 为常数，横向速度 \(v_y\)，
横摆角速度 \(r\)。前后轮侧偏角为：

\[
\alpha_f = \delta - \frac{v_y + l_f r}{v}
\]

\[
\alpha_r = -\frac{v_y - l_r r}{v}
\]

线性轮胎模型：

\[
F_{yf}=C_f\alpha_f,\qquad F_{yr}=C_r\alpha_r
\]

车辆横向与横摆运动方程：

\[
m(\dot v_y + v r)=F_{yf}+F_{yr}
\]

\[
I_z\dot r=l_fF_{yf}-l_rF_{yr}
\]

定义横向误差 \(e_y\)、航向误差 \(e_\psi\)，并利用两个运动学关系：

\[
v_y=\dot e_y-v e_\psi
\]

\[
r=\dot e_\psi+\kappa v
\]

其中 \(\kappa\) 是参考曲率，\(\dot\psi_{ref}=\kappa v\) 是参考横摆角速度。
把 \(v_y\)、\(r\) 代入轮胎力和运动方程，整理后即可得到上面的
\(A\)、\(B\)、\(C\)。例如横向方程展开为：

\[
\ddot e_y=
-\frac{C_f+C_r}{mv}\dot e_y
+\frac{C_f+C_r}{m}e_\psi
+\frac{l_rC_r-l_fC_f}{mv}\dot e_\psi
+\frac{C_f}{m}\delta
+\left(\frac{l_rC_r-l_fC_f}{mv}-v\right)\kappa v
\]

最后一项就是 \(C\) 的第 1 行乘以 \(\dot\psi_{ref}\)。
横摆方程同理，最后一项对应 \(C\) 的第 3 行。

> 这也说明：如果 \(C\) 项没有进入 QP，参考曲率对误差动力学的仿射影响
> 就没有被显式建模；代码用曲率前馈和每周期重新线性化来近似补偿。

#### 逐行解释

| 行 | 方程 | 物理含义 |
|---:|---|---|
| 0 | `e_y_dot = e_y_dot` | 状态定义：横向误差的变化率就是第 2 个状态 |
| 1 | `e_y_ddot = ...` | 轮胎侧偏力产生的横向加速度：与横向速度、航向误差、横摆角速度有关 |
| 2 | `e_psi_dot = e_psi_dot` | 状态定义：航向误差变化率就是第 4 个状态 |
| 3 | `e_psi_ddot = ...` | 横摆力矩产生的角加速度：与横向速度、航向误差、横摆角速度有关 |
| 4 | `e_s_dot = e_v` | 纵向位置误差的变化率等于速度误差 |
| 5 | `e_v_dot = -a` | 速度误差的变化率等于负的加速度（假设参考加速度在预测域内为 0） |

`A` 中与 `v` 相关的项在 `UpdateMatrix` 中写入：

```cpp
// mpc_controller.cc:751-756
const double v = std::max(linear_velocity, minimum_speed_protection_);
matrix_a_(1, 1) = matrix_a_coeff_(1, 1) / v;
matrix_a_(1, 3) = matrix_a_coeff_(1, 3) / v;
matrix_a_(3, 1) = matrix_a_coeff_(3, 1) / v;
matrix_a_(3, 3) = matrix_a_coeff_(3, 3) / v;
```

`minimum_speed_protection_` 默认 `0.1 m/s`，用于避免低速时 `1/v` 数值爆炸。

### 5.4 离散化：Tustin（双线性变换）

代码没有用简单的前向欧拉，而是对 `A` 使用 Tustin 变换：

```cpp
// mpc_controller.cc:758-760
Matrix matrix_i = Matrix::Identity(...);
matrix_ad_ = (matrix_i - ts_ * 0.5 * matrix_a_).inverse() *
             (matrix_i + ts_ * 0.5 * matrix_a_);
```

\[
A_d = \left(I-\frac{T_s}{2}A\right)^{-1}\left(I+\frac{T_s}{2}A\right)
\]

而 `B_d` 用前向欧拉：

```cpp
// mpc_controller.cc:240
matrix_bd_ = matrix_b_ * ts_;
```

\[
B_d = B T_s
\]

Tustin 对连续系统的频率响应拟合更好，低速/高频段比前向欧拉稳定。
`T_s` 默认 `0.01 s`，来自配置 `ts: 0.01`。

### 5.5 预测方程

离散模型：

\[
x_{k+1}=A_d x_k+B_d u_k,\quad k=0,1,\dots,N-1
\]

预测时域 `N = horizon_ = 10`，在
[`mpc_controller.h:191`](../../modules/control/controllers/mpc_controller/mpc_controller.h#L191)
中硬编码：

```cpp
const int horizon_ = 10;
```

注意：`horizon_` 不是配置项。预测时长约为 `10 × 0.01 = 0.1 s`。
这个时域很短，MPC 更像一个「带约束的多步反馈律」，而不是传统意义上
长时域轨迹优化；跟踪误差主要靠每个周期重新线性化和曲率前馈来补偿。

### 5.6 倒车处理

当挡位为 `GEAR_REVERSE` 时：

```cpp
// mpc_controller.cc:368-371
cf_ = -control_conf_.cf();
cr_ = -control_conf_.cr();
matrix_a_(0, 1) = 0.0;
matrix_a_coeff_(0, 2) = 1.0;
```

代码注释给出的倒车 `A` 矩阵第 0 行是 `[0, 0, v, 0]`，
意图是用运动学关系 `e_y_dot = v * e_psi` 替代前进时的 `e_y_dot = e_y_dot`。
但 `UpdateMatrix` 只更新第 1、3 行，**没有把 `matrix_a_coeff_(0,2)` 写回
`matrix_a_(0,2)`**，所以当前代码中倒车第 0 行实际仍是 `[0, 0, 0, 0]`。

更需要注意的是，倒车分支只修改了 `cf_`/`cr_` 这两个成员变量和 `A(0,1)`，
**没有重建** `matrix_a_coeff_` 的第 1、3 行，也没有重建 `matrix_b_`/`matrix_bd_`。
`UpdateMatrix` 使用的仍是 `Init` 时按前进方向算出的系数。
因此倒车时真正进入 QP 的模型与注释描述有较大差距，
倒车场景下建议先做仿真/台架验证，不要直接假设代码已经完成模型切换。

此外，倒车时：

- `ComputeLateralErrors` 中 `heading_rate` 取 `-angular_v`；
- `FLAGS_reverse_heading_control` 为真时，`lateral_error_dot` 和
  `lateral_error_dot_dot` 再取反；
- `FeedforwardUpdate` 在 `use_kinematic_model && GEAR_REVERSE` 时使用
  纯运动学前馈 `δ_ff = L * kappa`，否则使用带不足转向梯度的公式。

### 5.7 重要：C 项没有进入 QP

`UpdateMatrix` 计算了：

```cpp
matrix_c_(1, 0) = (lr_ * cr_ - lf_ * cf_) / mass_ / v - v;
matrix_c_(3, 0) = -(lf_ * lf_ * cf_ + lr_ * lr_ * cr_) / iz_ / v;
matrix_cd_ = matrix_c_ * debug->ref_heading_rate() * ts_;
```

但 `MpcOsqp` 的构造函数只接收 `A_d`、`B_d`、`Q`、`R` 等，
**没有接收 `C_d`**。也就是说，参考曲率/参考横摆角速度项并没有作为
仿射项进入优化问题。

代码的做法是：

- 每个周期用当前误差重新线性化（误差本身已经包含了参考轨迹信息）；
- 用 `FeedforwardUpdate` 单独计算曲率前馈转角；
- QP 只负责把误差状态调节到 0。

这也解释了为什么 QP 的 `x_ref` 是零向量：它是一个**误差调节器**，
而不是带完整参考轨迹的预测跟踪器。

---

## 6. 代价函数

### 6.1 目标

在每个控制周期，求解未来 `N` 步的控制序列，使：

\[
J=\sum_{k=0}^{N} x_k^T Q x_k+\sum_{k=0}^{N-1} u_k^T R u_k
\]

其中：

- `Q`：6×6 半正定对角矩阵，惩罚状态误差；
- `R`：2×2 正定对角矩阵，惩罚控制量；
- `x_k` 是第 `k` 步的预测状态；
- `u_k` 是第 `k` 步的控制量。

### 6.2 转成 OSQP 标准形式

OSQP 求解的是：

\[
\min_z \frac12 z^T P z + q^T z
\]

\[
\text{s.t.}\quad l \le A z \le u
\]

Apollo 把决策变量排成：

\[
z=
\begin{bmatrix}
x_0\\
x_1\\
\vdots\\
x_N\\
u_0\\
u_1\\
\vdots\\
u_{N-1}
\end{bmatrix}
\]

维度：

\[
n_z = n(N+1)+mN = 6\times 11 + 2\times 10 = 86
\]

`P` 是分块对角矩阵：

\[
P=\mathrm{blkdiag}(\underbrace{Q,\dots,Q}_{N+1},\underbrace{R,\dots,R}_{N})
\]

`q` 由
[`CalculateGradient`](../../modules/common/math/mpc_osqp.cc#L95)
计算：

```cpp
gradient_ = VectorXd::Zero(...);
for (i = 0; i <= horizon_; ++i) {
  gradient_.block(i * state_dim_, 0, state_dim_, 1) =
      -1.0 * matrix_q_ * matrix_x_ref_;
}
```

由于 `matrix_x_ref_` 是零向量，**`q = 0`**。

于是目标函数退化为：

\[
J=\frac12 z^T P z
\]

即「让所有状态和控制量尽量接近 0」。这里的「0」不是世界坐标原点，
而是「当前参考点上的零误差」。

### 6.3 默认权重

[`controller_conf.pb.txt`](../../modules/control/controllers/mpc_controller/conf/controller_conf.pb.txt)
中的默认值：

| 状态/控制 | 符号 | 权重 |
|---|---|---:|
| 横向误差 | `e_y` | 40.0 |
| 横向误差变化率 | `e_y_dot` | 0.0 |
| 航向误差 | `e_psi` | 30.0 |
| 航向误差变化率 | `e_psi_dot` | 0.0 |
| 纵向位置误差 | `e_s` | 70.0 |
| 速度误差 | `e_v` | 10.0 |
| 前轮转角 | `delta` | 3.25 |
| 加速度 | `a` | 1.0 |

直观理解：

- `e_s = 70` 最大：优先保证纵向位置跟踪（跟车距离/停车位置）；
- `e_y = 40`：横向偏差要收敛；
- `e_psi = 30`：航向也要对齐，但略低于横向位置；
- `e_v = 10`：速度误差权重相对小，避免为了速度牺牲位置；
- 两个 rate 状态权重为 0：不直接惩罚变化率，靠动力学耦合和约束间接约束；
- `R(0,0) = 3.25 > R(1,1) = 1.0`：更不愿意打方向，宁愿用加速度。

### 6.4 增益调度

[`LoadMPCGainScheduler`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L297)
把四组「速度 → 比例」表加载成 `Interpolation1D`：

- `lat_err_gain_scheduler`
- `heading_err_gain_scheduler`
- `feedforwardterm_gain_scheduler`
- `steer_weight_gain_scheduler`

每个周期如果 `FLAGS_enable_gain_scheduler` 为真：

```cpp
// mpc_controller.cc:405-418
matrix_q_updated_(0, 0) = matrix_q_(0, 0) * lat_err_interpolation_->Interpolate(v);
matrix_q_updated_(2, 2) = matrix_q_(2, 2) * heading_err_interpolation_->Interpolate(v);
steer_angle_feedforwardterm_updated_ =
    steer_angle_feedforwardterm_ * feedforwardterm_interpolation_->Interpolate(v);
matrix_r_updated_(0, 0) = matrix_r_(0, 0) * steer_weight_interpolation_->Interpolate(v);
```

默认表的特点：

- 低速时 `lat_err` 和 `heading_err` 的比例大于 1（更激进地纠偏）；
- 高速时比例降到 0.1～0.2（更保守）；
- 前馈比例在 2.5 m/s 时 0.7，10 m/s 以上降到 0（高速不再依赖曲率前馈，交给反馈）；
- 转向权重随速度升高而增大（高速更不愿意打方向）。

### 6.5 为什么 `q=0` 也能跟踪？

因为「参考」是通过误差计算进入系统的，而不是通过 `x_ref`：

1. 每个周期用当前匹配点/参考点重新计算 `e_y`、`e_psi`、`e_s`、`e_v`；
2. QP 以这些误差为初值，最小化未来误差；
3. 曲率前馈直接给出稳态转角；
4. 只执行第一步，下一步重新计算。

这是典型的 **receding horizon error regulation**。
它的好处是实现简单、矩阵维度固定；代价是没有显式的未来参考轨迹预览，
对大幅机动/预判场景的能力有限。

---

## 7. 约束

### 7.1 等式约束

QP 的约束矩阵 `A`（不要和动力学 `A` 混淆）由
[`CalculateEqualityConstraint`](../../modules/common/math/mpc_osqp.cc#L108)
拼装，包含三部分：

#### 1）初始状态约束

\[
x_0 = x_{init}
\]

代码中：

```cpp
matrix_constraint.block(0, 0, n*(N+1), n*(N+1)) = -I;
lowerEquality.block(0, 0, n, 1) = -matrix_initial_x_;
upperEquality = lowerEquality;
```

即 `-x_0 = -x_init`。

#### 2）动力学约束

对 `k = 0..N-1`：

\[
x_{k+1} - A_d x_k - B_d u_k = 0
\]

代码中把 `A_d` 放在 `(k+1)` 行块、`k` 列块，把 `B_d` 放在控制变量列块。

#### 3）状态/控制边界

约束矩阵的下半部分是一个单位矩阵块：

```cpp
matrix_constraint.block(n*(N+1), 0, num_param, num_param) = I;
```

它把状态变量和控制变量直接暴露给 OSQP 的上下界
`l`、`u`，从而实现：

\[
x_{min} \le x_k \le x_{max}
\]

\[
u_{min} \le u_k \le u_{max}
\]

### 7.2 控制量约束

[`ComputeControlCommand`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L445)
中：

```cpp
Matrix lower_bound(controls_, 1);
lower_bound << -wheel_single_direction_max_degree_, max_deceleration_;

Matrix upper_bound(controls_, 1);
upper_bound << wheel_single_direction_max_degree_, max_acceleration_;
```

即：

\[
-\delta_{max} \le \delta \le \delta_{max}
\]

\[
a_{min} \le a \le a_{max}
\]

其中：

- `wheel_single_direction_max_degree_` 名字里带 degree，但实际单位是 **rad**：
  代码先由 `max_steer_angle * 180/pi` 得到方向盘最大角度（度），
  再除以 `steer_ratio`、乘 `pi/180`，得到前轮最大转角（rad）。
- `max_acceleration_` / `max_deceleration_` 来自车辆配置
  `vehicle_param`，`max_deceleration` 通常是负值。

### 7.3 状态约束

```cpp
lower_state_bound << -1.0 * max, -1.0 * max, -1.0 * M_PI, -1.0 * max,
                     -1.0 * max, -1.0 * max;
upper_state_bound << max, max, M_PI, max, max, max;
```

即：

- 横向误差、横向误差变化率：无界；
- 航向误差：`[-pi, pi]`；
- 航向误差变化率、纵向位置误差、速度误差：无界。

也就是说，Apollo MPC 主要依赖**控制量约束**来保证可行性，
状态约束只对航向误差做了物理上的归一化限制。
如果需要限制横向偏差、速度误差或加速度变化率，需要自己扩展
`lower_state_bound` / `upper_state_bound` 或增加新的状态。

### 7.4 维度与 OSQP 拼装

以默认参数计算：

| 量 | 公式 | 数值 |
|---|---|---:|
| 状态维数 `n` | `basic_state_size_` | 6 |
| 控制维数 `m` | `controls_` | 2 |
| 预测步数 `N` | `horizon_` | 10 |
| 决策变量数 | `n(N+1)+mN` | 86 |
| 约束行数 | `2n(N+1)+mN` | 152 |

`MpcOsqp` 构造函数（[`mpc_osqp.cc:22`](../../modules/common/math/mpc_osqp.cc#L22)）
保存矩阵并计算 `state_dim_`、`control_dim_`、`num_param_`：

```cpp
state_dim_ = matrix_b.rows();       // 6
control_dim_ = matrix_b.cols();     // 2
num_param_ = state_dim_ * (horizon_ + 1) + control_dim_ * horizon_; // 86
```

`Data()` 中：

```cpp
data->n = kernel_dim;               // 86
data->m = num_affine_constraint;    // 152
```

`P`、`A` 都用 CSC 稀疏格式（`csc_matrix`）传给 OSQP。
`CalculateKernel` 只在对角线放 `Q`、`R`，所以 `P` 是对角矩阵；
`CalculateEqualityConstraint` 按列扫描非零元素，构造稀疏 `A`。

### 7.5 求解设置与失败行为

[`Settings`](../../modules/common/math/mpc_osqp.cc#L219)：

```cpp
settings->polish = true;
settings->scaled_termination = true;
settings->verbose = false;
settings->max_iter = max_iteration_;   // 默认 3000
settings->eps_abs = eps_abs_;          // 默认 0.01
```

`Solve()` 中检查状态：

```cpp
if (status < 0 || (status != 1 && status != 2)) {
  AERROR << "failed optimization status:\t" << ...;
  // cleanup
  return false;
}
```

OSQP 状态 1/2 通常表示 solved / solved inaccurate。

调用方：

```cpp
// mpc_controller.cc:478-484
if (!mpc_osqp.Solve(&control_cmd)) {
  AERROR << "MPC OSQP solver failed";
} else {
  control[0](0, 0) = control_cmd.at(0);
  control[0](1, 0) = control_cmd.at(1);
}
```

注意：**求解失败时不会中止控制周期**。`control` 向量初始化为 0，
因此转向反馈和加速度反馈都会是 0，但后续仍会叠加参考加速度、坡度补偿、
前馈等并输出。实车/调试时应把求解失败当作需要监控的异常。

---

## 8. 从最优解到执行器

QP 解出的 `control_cmd` 是：

```text
control_cmd[0] = 前轮转角 δ，单位 rad
control_cmd[1] = 纵向加速度 a，单位 m/s²
```

### 8.1 转向

```cpp
// mpc_controller.cc:486
steer_angle_feedback = Wheel2SteerPct(control[0](0, 0));
```

`Wheel2SteerPct`：

```cpp
// mpc_controller.cc:289
return wheel_angle / wheel_single_direction_max_degree_ * 100;
```

把前轮转角转成「最大转角的百分比」，范围约 `[-100, 100]`。

随后叠加四项：

\[
\delta_{cmd} =
\delta_{feedback} +
\delta_{ff} +
\delta_{ff,comp} +
\delta_{leadlag}
\]

- `steer_angle_feedback`：QP 解；
- `steer_angle_feedforwardterm_updated_`：曲率前馈；
- `steer_angle_ff_compensation`：可选的 MPC 前馈补偿（默认关闭）；
- `steer_angle_feedback_augment`：可选的 LeadLag 补偿。

曲率前馈在
[`FeedforwardUpdate`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L767)：

```cpp
const double kv =
    lr_ * mass_ / 2 / cf_ / wheelbase_ -
    lf_ * mass_ / 2 / cr_ / wheelbase_;
steer_angle_feedforwardterm_ = Wheel2SteerPct(
    wheelbase_ * debug->curvature() + kv * v * v * debug->curvature());
```

数学形式：

\[
\delta_{ff} = \kappa\left(L + K_v v^2\right)
\]

\[
K_v = \frac{l_r m}{2 C_f L} - \frac{l_f m}{2 C_r L}
\]

这是线性自行车模型的稳态转角公式：`L * kappa` 是 Ackermann 项，
`K_v v^2 kappa` 补偿轮胎侧偏带来的不足转向。

### 8.2 横向加速度限幅

如果 `FLAGS_set_steer_limit` 为真（`control.conf` 中默认 `true`）：

```cpp
const double steer_limit =
    atan(max_lat_acc_ * wheelbase_ / (v * v)) *
    steer_ratio_ * 180 / M_PI /
    steer_single_direction_max_degree_ * 100;
steer_angle_limited = Clamp(steer_angle, -steer_limit, steer_limit);
```

数学形式：

\[
\delta_{limit}(v)=\arctan\left(\frac{a_{lat,max}L}{v^2}\right)
\]

再换算成方向盘百分比。它限制的是「当前速度下不产生超过 `max_lat_acc_`
横向加速度」的最大转角。

### 8.3 低通滤波与最终限幅

```cpp
steer_angle = digital_filter_.Filter(steer_angle);
steer_angle = Clamp(steer_angle, -100.0, 100.0);
cmd->set_steering_target(steer_angle);
cmd->set_steering_rate(FLAGS_steer_angle_rate);
```

`digital_filter_` 的系数由
[`InitializeFilters`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L180)
用 `cutoff_freq`（默认 10 Hz）和 `ts` 生成，是一个二阶低通滤波器，
用于抑制转向抖动。

注意：当 `set_steer_limit` 为真时，`digital_filter_.Filter` 会被调用两次
（限幅分支内一次，分支外再一次），相当于级联两个相同的低通滤波器。
读代码/调参时要知道这一点。

### 8.4 加速度与坡度补偿

```cpp
double vehicle_pitch = use_pitch_angle_filter_
    ? digital_filter_pitch_angle_.Filter(vehicle_state->pitch())
    : vehicle_state->pitch();

double slope_offset_compensation = GRA_ACC * sin(vehicle_pitch);

double acceleration_cmd =
    acc_feedback + debug->acceleration_reference() +
    control_conf_.enable_slope_offset() * debug->slope_offset_compensation();
```

即：

\[
a_{cmd} = a_{feedback} + a_{ref} + \mathbf{1}_{slope} \cdot g\sin(\theta_{pitch})
\]

其中 `g = 9.8`。`enable_slope_offset` 默认 `false`，所以默认不加坡度补偿。

### 8.5 停车逻辑

[`GetPathRemain`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L1059)
从轨迹中找停车点，计算：

```text
path_remain = s_stop - station_feedback
```

如果轨迹类型是 `NORMAL`、`SPEED_FALLBACK` 或 `UNKNOWN`，并且：

```cpp
std::abs(debug->path_remain()) < FLAGS_max_acceleration_when_stopped
```

则标记 `is_full_stop = true`。注意这里用 `FLAGS_max_acceleration_when_stopped`
（默认 `0.01`）作为**距离阈值**，变量名和用途不一致。

如果 `use_preview_reference_check` 打开，还会检查预览点的速度和加速度：

```cpp
if (fabs(preview_acceleration_reference) <= FLAGS_max_acceleration_when_stopped &&
    fabs(preview_speed_reference) <= max_abs_speed_when_stopped) {
  is_full_stop = true;
}
```

进入 full stop 后：

```cpp
acceleration_cmd = (gear == GEAR_REVERSE)
    ? std::max(acceleration_cmd, standstill_acceleration_)
    : std::min(acceleration_cmd, standstill_acceleration_);
Reset();
```

`standstill_acceleration_` 默认 `-1.0 m/s²`，用于让车辆在终点柔和停住。

### 8.6 加速度标定表与油门/刹车

先做可选的加速度闭环 PID：

```cpp
double acceleration_lookup_error = acceleration_cmd - debug->acceleration_vrf();
double acceleration_lookup_offset = use_lookup_acc_pid_
    ? acceleration_lookup_pid_controller_.Control(acceleration_lookup_error, ts_)
    : 0.0;
double acceleration_lookup = acceleration_lookup_offset + acceleration_cmd;
```

然后用二维插值表
[`control_interpolation_`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L710)
把 `(speed, acceleration_lookup)` 映射成执行器指令：

```cpp
calibration_value = control_interpolation_->Interpolate(
    std::make_pair(speed, acceleration_lookup));
```

标定表的两个输入是速度和加速度：默认用当前车速
`vehicle_state->linear_velocity()`；如果 `FLAGS_use_preview_speed_for_table`
为真，则改用预览速度 `preview_speed_reference()`。

标定表来自
[`calibration_table.pb.txt`](../../modules/control/control_component/conf/calibration_table.pb.txt)，
每个条目是：

```text
speed:        车速 (m/s)
acceleration: 目标加速度 (m/s²)
command:      执行器指令（正数给油门，负数给刹车）
```

最后：

```cpp
if (acceleration_cmd >= 0) {
  throttle_cmd = std::max(calibration_value, throttle_lowerbound_);
  brake_cmd = 0.0;
} else {
  throttle_cmd = 0.0;
  brake_cmd = std::max(-calibration_value, brake_lowerbound_);
}
```

即：加速度命令非负走油门分支，为负走刹车分支；
`throttle_lowerbound_` / `brake_lowerbound_` 取车辆死区与控制配置的较大值。

### 8.7 输出字段

```cpp
cmd->set_steering_target(steer_angle);      // 百分比 [-100, 100]
cmd->set_steering_rate(FLAGS_steer_angle_rate); // 默认 100 %/s
cmd->set_throttle(throttle_cmd);            // 百分比 [0, 100]
cmd->set_brake(brake_cmd);                  // 百分比 [0, 100]
cmd->set_acceleration(acceleration_cmd);    // m/s²
cmd->set_gear_location(...);                // 低速/空挡时跟随规划挡位
```

---

## 9. 代码调用流程（逐函数）

### 9.1 `Init`

位置：[`mpc_controller.cc:196`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L196)

```text
Init(injector)
├── ControlTask::LoadConfig<MPCControllerConf>(&control_conf_)
├── ControlTask::LoadCalibrationTable(&calibration_table_)
├── LoadControlConf()
│    ├── 读取车辆参数、ts、cf/cr、质量、轴距、lf/lr、iz
│    ├── 读取 Q/R/eps/max_iteration
│    ├── 读取前馈/预览/挡位/限幅等开关
│    └── InitControlCalibrationTable()
├── 初始化 A、A_coeff、B、Bd、C、state、k、Q、R
├── 初始化加速度 PID
├── InitializeFilters()
└── LoadMPCGainScheduler()
```

`LoadControlConf` 中的关键计算：

```cpp
mass_front = mass_fl + mass_fr;
mass_rear  = mass_rl + mass_rr;
mass_      = mass_front + mass_rear;
lf_ = wheelbase_ * (1.0 - mass_front / mass_);
lr_ = wheelbase_ * (1.0 - mass_rear / mass_);
iz_ = lf_ * lf_ * mass_front + lr_ * lr_ * mass_rear;
```

这是用四个车轮质量近似整车质量分布，并据此估算质心位置和转动惯量。

### 9.2 `ComputeControlCommand`

位置：[`mpc_controller.cc:337`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L337)

逐段说明：

| 行号 | 内容 |
|---:|---|
| 342-343 | 构造 `TrajectoryAnalyzer` |
| 348-353 | 按需把轨迹平移到 COM |
| 358-386 | 倒车时重建 `A` |
| 388-389 | 清空 `SimpleMPCDebug` |
| 391-395 | 计算纵向误差（两个重载） |
| 398 | `UpdateState` |
| 400 | `UpdateMatrix` |
| 402 | `FeedforwardUpdate` |
| 405-423 | 增益调度，得到 `*_updated_` |
| 433-459 | 构造控制/状态上下界 |
| 469-477 | 构造 `MpcOsqp` |
| 478-484 | 求解 |
| 486-516 | 转向反馈、无约束控制差、前馈补偿 |
| 523-538 | LeadLag 补偿 |
| 541-562 | 叠加、限幅、滤波、写 `steering_target` |
| 564-588 | 加速度参考、坡度补偿 |
| 591-623 | 路径剩余与 full stop |
| 625-654 | 加速度 lookup/PID/标定表 |
| 658-680 | 油门/刹车分支、写输出 |
| 682-698 | 调试信息与挡位 |
| 700 | `ProcessLogs` |

### 9.3 `UpdateState`

位置：[`mpc_controller.cc:724`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L724)

```text
UpdateState(debug)
├── com = vehicle_state.ComputeCOMPosition(lr_)
├── ComputeLateralErrors(com.x, com.y, heading, v, omega, a, ...)
└── 写 matrix_state_:
     [0] lateral_error（或 look-ahead feedback）
     [1] lateral_error_rate
     [2] heading_error（或 look-ahead feedback）
     [3] heading_error_rate
     [4] station_error
     [5] speed_error
```

注意：`matrix_state_` 的第 0、2 项会根据
`enable_look_ahead_back_control_` 选择普通误差还是 look-ahead/look-back 误差。

### 9.4 `ComputeLateralErrors`

位置：[`mpc_controller.cc:782`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L782)

```text
ComputeLateralErrors
├── QueryNearestPointByPosition(x, y)
├── e_y = cos(theta_r)*dy - sin(theta_r)*dx
├── e_psi = NormalizeAngle(theta - theta_r)
├── e_y_dot = v*sin(e_psi)
├── ref_heading_rate = kappa_r * v_r
├── heading_rate = +/- angular_v
├── e_psi_dot = heading_rate - ref_heading_rate
├── look-ahead/look-back 修正（可选）
└── 填充 lateral_acceleration/jerk/curvature 等调试量
```

### 9.5 `ComputeLongitudinalErrors`

两个重载：

- [`mpc_controller.cc:910`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L910)：不带 preview，只填当前参考点；
- [`mpc_controller.cc:971`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L971)：带 `preview_time`，额外填 preview 字段。

核心步骤：

```text
QueryMatchedPathPoint(x, y)          // 按位置
ToTrajectoryFrame(...)               // 得到 s_matched, s_dot_matched, d_matched
QueryNearestPointByAbsoluteTime(now) // 按时间取参考点
station_error = s_ref - s_matched
speed_error   = v_ref - s_dot_matched
```

### 9.6 `UpdateMatrix`

位置：[`mpc_controller.cc:750`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L750)

```text
v = max(linear_velocity, minimum_speed_protection_)
A(1,1) = coeff(1,1)/v
A(1,3) = coeff(1,3)/v
A(3,1) = coeff(3,1)/v
A(3,3) = coeff(3,3)/v
A_d = (I - ts/2*A)^-1 * (I + ts/2*A)
C(1,0) = (lr*cr - lf*cf)/(m*v) - v
C(3,0) = -(lf^2*cf + lr^2*cr)/(iz*v)
C_d = C * ref_heading_rate * ts
```

### 9.7 `FeedforwardUpdate`

位置：[`mpc_controller.cc:767`](../../modules/control/controllers/mpc_controller/mpc_controller.cc#L767)

```text
kv = lr*m/(2*cf*L) - lf*m/(2*cr*L)
if (use_kinematic_model && GEAR_REVERSE)
    delta_ff = L * kappa
else
    delta_ff = L*kappa + kv*v^2*kappa
delta_ff_pct = Wheel2SteerPct(delta_ff)
```

### 9.8 `MpcOsqp::Solve`

位置：[`mpc_osqp.cc:281`](../../modules/common/math/mpc_osqp.cc#L281)

```text
Solve
├── CalculateGradient()
├── CalculateConstraintVectors()
├── Data()
│    ├── CalculateKernel()             // P
│    └── CalculateEqualityConstraint() // A
├── Settings()
├── osqp_setup()
├── osqp_solve()
├── 检查 status
├── 取 solution->x[first_control ... first_control+control_dim-1]
└── cleanup
```

`first_control = state_dim_ * (horizon_ + 1)`，即跳过所有预测状态，
取第一个控制量。

### 9.9 Submodule 路径

[`MPCControllerSubmodule::Init`](../../modules/control/control_component/submodules/mpc_controller_submodule.cc#L48)：

```cpp
mpc_controller_ = PluginManager::Instance()->CreateInstance<ControlTask>(
    "apollo::control::MPCController");
mpc_controller_->Init(injector_);
```

[`ProduceControlCoreCommand`](../../modules/control/control_component/submodules/mpc_controller_submodule.cc#L117)：

```cpp
if (chassis.driving_mode() == COMPLETE_MANUAL) {
  mpc_controller_->Reset();
}
mpc_controller_->ComputeControlCommand(
    &local_view.localization(), &local_view.chassis(),
    &local_view.trajectory(), control_core_command);
```

`Proc` 会把结果写到 `/apollo/control/controlcore`，再由
`PostprocessorSubmodule` 转发到 `/apollo/control`。

---

## 10. 参数与调参

### 10.1 核心配置字段

| 字段 | 默认值 | 作用 | 调参影响 |
|---|---:|---|---|
| `ts` | 0.01 | 控制/预测步长 (s) | 必须与控制周期一致；影响离散化 |
| `cf` / `cr` | 155494.663 | 前后轮侧偏刚度 (N/rad) | 模型精度；偏差大时反馈增益不匹配 |
| `mass_fl/fr/rl/rr` | 45/45/57/57 | 四轮质量 (kg) | 计算总质量、质心、转动惯量 |
| `matrix_q` | 40,0,30,0,70,10 | 状态权重 | 横向/航向/纵向跟踪优先级 |
| `matrix_r` | 3.25,1.0 | 控制权重 | 转向/加速度的「费力程度」 |
| `eps` | 0.01 | OSQP 绝对收敛阈值 | 越小越精确，越慢 |
| `max_iteration` | 3000 | OSQP 最大迭代 | 复杂场景可适当增大 |
| `max_lateral_acceleration` | 4.0 | 转向限幅用最大横向加速度 | 越小越保守 |
| `standstill_acceleration` | -1.0 | 停车时的保持加速度 | 影响终点停车的柔和程度 |
| `brake_minimum_action` / `throttle_minimum_action` | 1.0 / 1.0 | 执行器最小动作 | 克服死区 |
| `cutoff_freq` | 10 | 转向低通截止频率 (Hz) | 越小越平滑，但相位滞后 |
| `mean_filter_window_size` | 10 | 导航模式误差均值滤波窗口 | 仅 `enable_navigation_mode_error_filter` 时用 |
| `lat_err_gain_scheduler` | 表 | 横向误差权重随速度缩放 | 低速激进/高速保守 |
| `heading_err_gain_scheduler` | 表 | 航向误差权重随速度缩放 | 同上 |
| `steer_weight_gain_scheduler` | 表 | 转向权重随速度缩放 | 高速更不愿意打方向 |
| `feedforwardterm_gain_scheduler` | 表 | 前馈随速度缩放 | 高速削弱前馈 |
| `enable_mpc_feedforward_compensation` | false | 是否启用 MPC 前馈补偿 | 当前代码中相关增益未填充，实际效果有限 |
| `use_preview` | false | 预览重载选择 | 命名与分支关系反直觉，见第 11 节 |
| `preview_window` | 0 | 预览窗口（步数） | `preview_time = preview_window * ts` |
| `enable_look_ahead_back_control` | false | 是否使用 look-ahead/look-back 误差 | 改善特殊场景下的反馈 |
| `switch_speed` / `switch_speed_window` | 0 / 0 | 低速/高速切换点与过渡窗 | LeadLag 和 look-ahead 的低高速切换 |
| `use_kinematic_model` | false | 倒车是否用运动学前馈 | 倒车低速场景可开 |
| `use_lookup_acc_pid` | true | 加速度 lookup 前是否加 PID | 改善加速度跟踪 |
| `use_pitch_angle_filter` | true | 是否滤波俯仰角 | 影响坡度补偿 |
| `enable_slope_offset` | false | 是否加坡度补偿 | 坡道场景可开 |

### 10.2 调参建议

1. **先确认模型参数**：`cf/cr`、四轮质量、`wheelbase`、`steer_ratio`、
   最大转角。模型参数不对，调 Q/R 只是掩盖问题。
2. **先调 `Q` 的对角线**：
   - 横向跟踪差 → 增大 `Q(0,0)`；
   - 航向摆动 → 增大 `Q(2,2)`，或适当增大 `R(0,0)`；
   - 纵向跟车/停车差 → 增大 `Q(4,4)`；
   - 速度跟踪差 → 增大 `Q(5,5)`。
3. **再调 `R`**：
   - 转向抖动/频繁修正 → 增大 `R(0,0)`；
   - 加速度变化太猛 → 增大 `R(1,1)`。
4. **最后调增益调度**：低速/高速分别看跟踪误差和控制平滑度，按速度点调整 ratio。
5. **用 `SimpleMPCDebug` 定位问题**：
   - `lateral_error`、`heading_error` 是否收敛；
   - `steer_angle_feedback` 与 `steer_angle_feedforward` 的比例；
   - `matrix_q_updated` / `matrix_r_updated` 是否符合预期；
   - `is_full_stop`、`path_remain` 是否误触发。

### 10.3 单位与符号检查清单

| 量 | 单位 | 常见错误 |
|---|---|---|
| `ts` | s | 与 `control_period` 不一致 |
| `cf/cr` | N/rad | 用了 N/deg |
| `steer_ratio` | 无量纲 | 方向盘转角/前轮转角的方向搞反 |
| `wheel_single_direction_max_degree_` | rad（名字误导） | 当成度使用 |
| `steering_target` | % | 当成 rad 或度 |
| `throttle/brake` | % | 当成 0～1 |
| `acceleration` | m/s² | 与 `acceleration_lookup` 混淆 |
| `matrix_q` | 无量纲权重 | 与物理量纲混用 |

---

## 11. 源码阅读注意点（坑）

以下条目是读当前版本源码时容易卡住或误解的地方。带「可能」的表示需要结合
具体配置/场景判断，不一定是 bug。

### 11.1 `C_d` 计算了但没有进入 QP

`matrix_c_` 和 `matrix_cd_` 在 `UpdateMatrix` 中计算，但 `MpcOsqp`
构造函数没有接收它们。参考曲率通过前馈和每周期重新线性化处理，
QP 本身是零参考的误差调节器。

### 11.2 `control_gain` / `addition_gain` 没有赋值

`ComputeControlCommand` 中：

```cpp
Matrix control_gain_matrix = Matrix::Zero(controls_, basic_state_size_);
std::vector<Matrix> control_gain(horizon_, control_gain_matrix);
Matrix addition_gain_matrix = Matrix::Zero(controls_, 1);
std::vector<Matrix> addition_gain(horizon_, addition_gain_matrix);
```

这两个向量之后没有被填充，`matrix_k_` 也没有被使用。
因此 `unconstrained_control` 恒为 0，`enable_mpc_feedforward_compensation`
分支中的补偿项实际为 0；如果 `unconstrained_control_diff` 超过阈值，
还会出现 `control[0] / 0` 的除法，得到 `inf/nan`，随后被
`std::isnan` 检查置 0。也就是说，这个补偿功能在当前版本基本是失效/遗留代码。

### 11.3 `trajectory_transform_to_com_*` 的条件写错了吗？

```cpp
if (((control_conf_.trajectory_transform_to_com_reverse() &&
      gear == GEAR_REVERSE) ||
     (control_conf_.trajectory_transform_to_com_reverse() &&
      gear == GEAR_DRIVE))) {
  trajectory_analyzer_.TrajectoryTransformToCOM(lr_);
}
```

第二个条件用的是 `_reverse()`，不是 `_drive()`。
对比 LQR 控制器
[`lat_controller.cc:383-388`](../../modules/control/controllers/lat_based_lqr_controller/lat_controller.cc#L383)，
那里用的是 `_reverse()` 和 `_drive()` 两个不同的字段。
当前 MPC 的写法意味着：只要打开 `trajectory_transform_to_com_reverse`，
前进和倒车都会平移轨迹；`trajectory_transform_to_com_drive` 实际没有作用。
如果只设置 `_drive: true`，前进时不会触发。

### 11.4 `use_preview_` 的分支与命名相反

```cpp
if (!use_preview_) {
  ComputeLongitudinalErrors(&trajectory_analyzer_, preview_time_, ts_, debug);
} else {
  ComputeLongitudinalErrors(&trajectory_analyzer_, debug);
}
```

`use_preview_ == false` 时反而调用了带 `preview_time` 的重载；
`use_preview_ == true` 时调用不带 preview 的重载。
默认 `use_preview = false`、`preview_window = 0`，所以 preview 点等于当前点，
通常不会造成可见问题，但读代码时容易被绕进去。

### 11.5 `horizon_` 是硬编码的

```cpp
const int horizon_ = 10;
```

不在 `MPCControllerConf` 中。想改预测步长必须改代码并重新编译。
`basic_state_size_ = 6`、`controls_ = 2` 同样是硬编码。

### 11.6 `matrix_q` 必须正好 6 个

`Init` 中：

```cpp
if (basic_state_size_ != q_param_size) {
  return Status(CONTROL_COMPUTE_ERROR, ...);
}
```

少一个或多一个都会初始化失败。
`matrix_r` 没有这个检查：先 `Identity(2,2)`，再按配置个数覆盖对角线，
所以只配 1 个值时，第二个控制权重保持 1.0。

### 11.7 转向低通滤波可能执行两次

`FLAGS_set_steer_limit` 为真时，限幅分支内调用一次
`digital_filter_.Filter`，分支外又调用一次。等价于两级相同低通，
会带来额外相位滞后。调参时若觉得转向响应偏慢，可以检查这里。

### 11.8 `GetPathRemain` 用了 `max_acceleration_when_stopped` 作为距离阈值

变量名是「停车时的最大加速度」，但在 `GetPathRemain` 中：

```cpp
if (std::abs(debug->path_remain()) < FLAGS_max_acceleration_when_stopped) {
  debug->set_is_full_stop(true);
}
```

这里它是「距离终点多少米内认为到达」的阈值（默认 0.01 m）。
命名和用途不一致，阅读时不要被名字误导。

### 11.9 `Reset()` 只重置两个误差

```cpp
Status MPCController::Reset() {
  previous_heading_error_ = 0.0;
  previous_lateral_error_ = 0.0;
  return Status::OK();
}
```

没有重置滤波器状态、`previous_*` 加速度/角速度、solver 等。
在 full stop 或手动模式切换时，可能会有短暂的过渡。

### 11.10 OSQP 失败不会中止控制

`solve` 失败只打印 `AERROR`，控制周期继续。此时 `control_cmd` 为 0，
转向反馈为 0，但前馈、参考加速度、坡度补偿仍会叠加。
调试时应监控日志中的 `MPC OSQP solver failed`。

### 11.11 倒车第 0 行没有真正更新

前面 5.6 节已说明：`matrix_a_coeff_(0,2) = 1.0` 被设置，但
`UpdateMatrix` 没有把它写回 `matrix_a_(0,2)`；同时倒车分支没有重建
`matrix_a_coeff_` 的第 1、3 行和 `B`/`B_d`，QP 里实际使用的仍是前进模型系数。
倒车横向运动学在代码注释和实现之间存在明显差距。

### 11.12 `use_lqr_curvature_feedforward_` 读取后未使用

`LoadControlConf` 中赋值，但 `FeedforwardUpdate` 没有根据它切换算法；
前馈始终走 `L*kappa + kv*v^2*kappa`（倒车运动学模式除外）。

### 11.13 默认配置缺少 `pitch_angle_filter_conf`

`use_pitch_angle_filter: true`，但 `controller_conf.pb.txt` 没有设置
`pitch_angle_filter_conf`，其 `cutoff_freq` 默认 0。
`LpfCoefficients` 在 `cutoff_freq = 0` 时分子系数全为 0，
滤波输出恒为 0。因此默认配置下 `vehicle_pitch` 会被滤波成 0。
虽然 `enable_slope_offset` 默认 `false`，不影响加速度输出，
但调试信息里的 `vehicle_pitch` 会一直是 0。需要坡道补偿时应显式配置
`pitch_angle_filter_conf { cutoff_freq: ... }` 或关闭该滤波。

### 11.14 CSV 调试日志目前不会写数据

构造函数在 `FLAGS_enable_csv_debug` 为真时创建
`/tmp/mpc_controller_*.csv`，但 `ProcessLogs` 是空函数，
`WriteHeaders` 也是空函数。想记录数据请用 `cyber_recorder`
录制 `/apollo/control`，或自己补全 `ProcessLogs`。

### 11.15 旧路径的 DAG / launch

`mpc_module.dag`、`lateral_longitudinal_module.dag` 中的
`module_library` 和 `flag_file_path` 仍是 `modules/control/...` 旧路径；
`control_mpc_control.launch` 中的 `dag_conf` 也是旧路径。
使用这些文件前先按第 1.2 节修正。

---

## 12. 动手实验

### 实验 1：跑通单元测试

```bash
# 容器内
bazel test //modules/control/controllers/mpc_controller:mpc_controller_test
```

测试文件
[`mpc_controller_test.cc`](../../modules/control/controllers/mpc_controller/mpc_controller_test.cc)
只验证 `ComputeLateralErrors` 的输出，用固定数据检查
`heading_error`、`lateral_error`、`curvature` 等是否接近期望值。
可以先改一个期望值，观察测试如何失败，理解误差计算的输入输出。

### 实验 2：切换 pipeline 到 MPC

1. 备份 `pipeline.pb.txt`；
2. 改成只有 `MPCController`；
3. `./apollo.sh build control`；
4. 启动 control，播包；
5. `cyber_monitor -c /apollo/control` 查看 `simple_mpc_debug`。

### 实验 3：改 Q 权重

把 `matrix_q` 的第一个值从 40 改成 80，重新播同一段包，观察：

- `lateral_error` 的收敛速度；
- `steer_angle_feedback` 的幅度；
- 是否出现转向抖动。

### 实验 4：改增益调度

把 `lat_err_gain_scheduler` 在 2 m/s 的 ratio 从 0.6 改成 1.0，
观察低速横向跟踪和转向平滑度的变化。

### 实验 5：验证前馈

在 `FeedforwardUpdate` 中临时打印 `curvature`、`v`、
`steer_angle_feedforwardterm_`，或者通过 `cyber_monitor` 看
`simple_mpc_debug.steer_angle_feedforward`，对照公式
`L*kappa + kv*v^2*kappa` 手算验证。

### 实验 6：观察 full stop

播一段终点停车的包，观察：

- `path_remain` 如何减小；
- `is_full_stop` 何时变 true；
- `acceleration_cmd` 是否被 `standstill_acceleration_` 限制；
- `Reset()` 后误差是否短暂跳变。

---

## 13. 术语表

| 术语 | 含义 |
|---|---|
| MPC | Model Predictive Control，模型预测控制 |
| QP | Quadratic Programming，二次规划 |
| OSQP | Operator Splitting Quadratic Program，Apollo 使用的 QP 求解器 |
| Frenet / 轨迹坐标 | 沿参考线 `s` + 横向偏移 `d` 的坐标 |
| 后轴中心 | Apollo 车辆状态的默认参考点 |
| COM | Center of Mass，质心 |
| 横向误差 `e_y` | 车辆相对参考线的横向有符号距离 |
| 航向误差 `e_psi` | 车辆航向与参考航向之差 |
| 纵向位置误差 `e_s` | 参考 `s` 与当前匹配 `s` 之差 |
| 速度误差 `e_v` | 参考速度与当前纵向速度之差 |
| 不足转向梯度 `K_v` | 描述车辆转向特性的参数，用于曲率前馈 |
| 增益调度 | 按速度插值调整 Q/R/前馈的比例 |
| Tustin 变换 | 双线性离散化方法 |
| CSC | Compressed Sparse Column，OSQP 的稀疏矩阵格式 |
| estop | 紧急停止 |
| full stop | 到达终点后的完全停车状态 |
| LeadLag | 超前-滞后补偿器 |
| pid | 比例-积分-微分控制器 |

---

## 附：源码文件索引

完整的逐文件索引、行号和阅读优先级见
[05_source_index.md](05_source_index.md)。
