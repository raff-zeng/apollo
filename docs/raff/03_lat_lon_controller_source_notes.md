# LAT / LON 控制器源码学习笔记

> 阅读基线：当前仓库 `zrf` 分支 HEAD。行号以当前仓库为准。
> 配套文档：
> - MPC 原理与源码：[04_mpc_controller_source_notes.md](04_mpc_controller_source_notes.md)
> - 控制学习任务与环境：[02_control_learning_task.md](02_control_learning_task.md)

## 目录

- [0. 一句话总结](#0-一句话总结)
- [1. 在 Control 模块中的位置](#1-在-control-模块中的位置)
- [2. 文件结构](#2-文件结构)
- [3. LAT 横向控制器：LQR](#3-lat-横向控制器lqr)
- [4. LON 纵向控制器：双环 PID](#4-lon-纵向控制器双环-pid)
- [5. LAT/LON 与 MPC 的对比](#5-latlon-与-mpc-的对比)
- [6. 源码阅读注意点](#6-源码阅读注意点)
- [7. 源码索引](#7-源码索引)

---

## 0. 一句话总结

Apollo 默认的控制方案是**横向 LQR + 纵向双环 PID**：

- **LAT（横向）**：用 4 状态线性自行车模型
  `[e_y, e_y_dot, e_psi, e_psi_dot]` 做离散 LQR，得到反馈转角；
  再叠加曲率前馈、可选的 LeadLag/MRAC 补偿，最后限幅、滤波，输出方向盘百分比。
- **LON（纵向）**：位置环 PID 把 `station_error` 变成速度补偿，
  速度环 PID 把 `speed_error` 变成加速度；
  叠加参考加速度和坡度补偿后，查油门/刹车标定表，输出 `throttle` / `brake`。
- **MPC**：把横向和纵向合成 6 状态，一次性求解带约束的 QP。
  LAT/LON 是「分解 + 经典控制」，MPC 是「联合 + 优化控制」。

---

## 1. 在 Control 模块中的位置

默认
[`pipeline.pb.txt`](../../modules/control/control_component/conf/pipeline.pb.txt)：

```text
controller {
  name: "LAT_CONTROLLER"
  type: "LatController"
}
controller {
  name: "LON_CONTROLLER"
  type: "LonController"
}
```

`ControlTaskAgent` 按顺序执行：

```text
ControlComponent::Proc()
  └── ControlTaskAgent::ComputeControlCommand()
        ├── LatController::ComputeControlCommand()   // 只写 steering_target / steering_rate
        └── LonController::ComputeControlCommand()   // 只写 throttle / brake / acceleration / gear
```

两者通过同一个 `ControlCommand` 通信：

- `LatController` 读取 `cmd->steering_target()`（纵向控制器会检查转向是否到位）；
- `LonController` 写 `throttle`、`brake`、`acceleration`、`gear_location`；
- 两者都往 `cmd->debug()` 里写各自的调试消息：
  `simple_lat_debug`、`simple_lon_debug`。

submodule 模式下，`LatLonControllerSubmodule` 依次调用两者：

```text
PreprocessorSubmodule → LatLonControllerSubmodule → PostprocessorSubmodule
```

对应文件：
[`lat_lon_controller_submodule.cc`](../../modules/control/control_component/submodules/lat_lon_controller_submodule.cc)。

---

## 2. 文件结构

### 2.1 LAT 插件包

```text
modules/control/controllers/lat_based_lqr_controller/
├── BUILD
├── cyberfile.xml
├── plugins.xml
├── lat_controller.h              # 类声明（277 行）
├── lat_controller.cc             # 实现（937 行）
├── lat_controller_test.cc        # 单元测试
├── lateral_controller_test/      # 测试数据
├── proto/
│   └── lat_based_lqr_controller_conf.proto
├── conf/
│   └── controller_conf.pb.txt
├── docs/images/
└── README_cn.md
```

### 2.2 LON 插件包

```text
modules/control/controllers/lon_based_pid_controller/
├── BUILD
├── cyberfile.xml
├── plugins.xml
├── lon_controller.h              # 类声明（189 行）
├── lon_controller.cc             # 实现（913 行）
├── lon_controller_test.cc
├── longitudinal_controller_test/
├── util/check_pit.h/.cc          # PIT（维修区）场景判断
├── proto/
│   └── lon_based_pid_controller_conf.proto
├── conf/
│   └── controller_conf.pb.txt
├── docs/images/
└── README_cn.md
```

### 2.3 关键依赖

| 文件 | 作用 |
|---|---|
| [`linear_quadratic_regulator.cc`](../../modules/common/math/linear_quadratic_regulator.cc) | 迭代求解离散 Riccati 方程，得到 LQR 增益 K |
| [`pid_controller.cc`](../../modules/control/control_component/controller_task_base/common/pid_controller.cc) | PID 实现（含积分饱和） |
| [`trajectory_analyzer.cc`](../../modules/control/control_component/controller_task_base/common/trajectory_analyzer.cc) | 轨迹匹配、Frenet 转换、COM 平移 |
| [`leadlag_controller.cc`](../../modules/control/control_component/controller_task_base/common/leadlag_controller.cc) | 超前-滞后补偿 |
| [`mrac_controller.cc`](../../modules/control/control_component/controller_task_base/common/mrac_controller.cc) | 模型参考自适应控制（默认关闭） |
| [`interpolation_1d.cc`](../../modules/control/control_component/controller_task_base/common/interpolation_1d.cc) | 增益调度插值 |
| [`interpolation_2d.cc`](../../modules/control/control_component/controller_task_base/common/interpolation_2d.cc) | 纵向标定表插值 |

---

## 3. LAT 横向控制器：LQR

### 3.1 输入输出

**输入**：

- 规划轨迹 `ADCTrajectory`；
- 定位 `LocalizationEstimate`；
- 底盘 `Chassis`；
- 车辆状态 `VehicleState`。

**输出**（写入 `ControlCommand`）：

- `steering_target`：方向盘百分比 `[-100, 100]`；
- `steering_rate`：默认 `FLAGS_steer_angle_rate = 100`；
- `debug.simple_lat_debug`：误差、前馈、反馈、各分项贡献等。

### 3.2 状态量与模型

状态：

\[
x=
\begin{bmatrix}
e_y\\
\dot e_y\\
e_\psi\\
\dot e_\psi
\end{bmatrix}
\]

这正好是 MPC 6 状态模型的前 4 维。连续模型：

\[
\dot x = A x + B\delta
\]

\[
A=
\begin{bmatrix}
0 & 1 & 0 & 0\\
0 & -\dfrac{C_f+C_r}{mv} & \dfrac{C_f+C_r}{m} & \dfrac{l_rC_r-l_fC_f}{mv}\\
0 & 0 & 0 & 1\\
0 & \dfrac{l_rC_r-l_fC_f}{I_zv} & \dfrac{l_fC_f-l_rC_r}{I_z} & -\dfrac{l_f^2C_f+l_r^2C_r}{I_zv}
\end{bmatrix}
\]

\[
B=
\begin{bmatrix}
0\\
\dfrac{C_f}{m}\\
0\\
\dfrac{l_fC_f}{I_z}
\end{bmatrix}
\]

与 MPC 的区别：

- LAT 只有 1 个控制量 `delta`；
- 没有纵向状态；
- 没有显式的参考曲率仿射项，曲率通过前馈处理；
- 多了一个**预览状态链**（`preview_window`）。

代码位置：

- 初始化 `A`、`B`：[`lat_controller.cc:192`](../../modules/control/controllers/lat_based_lqr_controller/lat_controller.cc#L192)；
- 每周期更新与速度相关的项：
  [`UpdateMatrix`](../../modules/control/controllers/lat_based_lqr_controller/lat_controller.cc#L711)。

### 3.3 离散化

与 MPC 一样使用 Tustin：

\[
A_d=\left(I-\frac{T_s}{2}A\right)^{-1}\left(I+\frac{T_s}{2}A\right)
\]

\[
B_d=B T_s
\]

```cpp
// lat_controller.cc:729-731
Matrix matrix_i = Matrix::Identity(matrix_a_.cols(), matrix_a_.cols());
matrix_ad_ = (matrix_i - ts_ * 0.5 * matrix_a_).inverse() *
             (matrix_i + ts_ * 0.5 * matrix_a_);
```

### 3.4 预览（preview）模型

`preview_window_` 默认 `0`（配置），因此默认不启用预览。
启用后：

```text
matrix_size = 4 + preview_window
state = [e_y, e_y_dot, e_psi, e_psi_dot, p0, p1, ..., p_{N-1}]
```

- `p_i` 是轨迹上未来第 `i+1` 个控制周期的横向误差；
- `UpdateState` 用 `QueryNearestPointByRelativeTime` 从轨迹中取出这些预览误差；
- `UpdateMatrixCompound` 构造增广矩阵：
  - 左上角放 `A_d`、`B_d`；
  - 预览状态之间是移位链 `p_i(k+1)=p_{i+1}(k)`；
  - 最后一个预览状态由控制量驱动 `p_{N-1}(k+1)=u(k)`。

```cpp
// lat_controller.cc:734-745
matrix_adc_.block(0, 0, basic_state_size_, basic_state_size_) = matrix_ad_;
matrix_bdc_.block(0, 0, basic_state_size_, 1) = matrix_bd_;
if (preview_window_ > 0) {
  matrix_bdc_(matrix_bdc_.rows() - 1, 0) = 1;
  for (int i = 0; i < preview_window_ - 1; ++i) {
    matrix_adc_(basic_state_size_ + i, basic_state_size_ + 1 + i) = 1;
  }
}
```

LQR 在增广系统上求解，因此 `K` 的列数等于 `4 + preview_window`。
预览状态每个周期都会被轨迹实测值覆盖，模型中的移位链只是为了让 LQR
在优化时把未来误差纳入反馈增益。

注意：配置中的 `matrix_q` 和 `reverse_matrix_q` 长度必须等于
`4 + preview_window`，否则 `Init` 直接报错。

### 3.5 LQR 求解

求解器：
[`SolveLQRProblem`](../../modules/common/math/linear_quadratic_regulator.cc#L33)

迭代离散代数 Riccati 方程：

\[
P_{k+1}=A^TP_kA-(A^TP_kB)(R+B^TP_kB)^{-1}(B^TP_kA)+Q
\]

收敛后：

\[
K=(R+B^TPB)^{-1}B^TPA
\]

代码中：

```cpp
// lat_controller.cc:475-477
common::math::SolveLQRProblem(matrix_adc_, matrix_bdc_, matrix_q_updated_,
                              matrix_r_, lqr_eps_, lqr_max_iteration_,
                              &matrix_k_, &num_iteration, &result_diff);
```

参数：

- `eps`：收敛阈值，默认 `0.01`；
- `max_iteration`：最大迭代次数，默认 `150`；
- `Q`：4×4（或 `4+N`）状态权重；
- `R`：1×1 控制权重，默认 `1.0`。

默认 Q：

```text
e_y       0.05
e_y_dot   0.0
e_psi     1.0
e_psi_dot 0.0
```

也就是**更重视航向误差**，横向误差权重较小。这与 MPC 的 Q
（横向 40、航向 30）方向不同：LAT 的 LQR 通过前馈和增益调度补偿横向跟踪，
而 MPC 把横向误差直接放进优化目标。

### 3.6 反馈转角

```cpp
// lat_controller.cc:488-493
const double steer_angle_feedback = -(matrix_k_ * matrix_state_)(0, 0) * 180 /
                                    M_PI * steer_ratio_ /
                                    steer_single_direction_max_degree_ * 100;
```

数学形式：

\[
\delta_{fb}=-Kx
\]

再从前轮转角（rad）换算成方向盘百分比：

\[
\delta_{fb,\%}=\delta_{fb}\cdot\frac{180}{\pi}\cdot
\frac{i_s}{\delta_{max,deg}}\cdot 100
\]

其中 `i_s = steer_ratio`，`delta_max_deg` 是方向盘最大转角（度）。

`matrix_state_` 的前 4 项：

```text
[0] lateral_error（或 look-ahead feedback）
[1] lateral_error_rate
[2] heading_error（或 look-ahead feedback）
[3] heading_error_rate
```

### 3.7 前馈转角

[`ComputeFeedForward`](../../modules/control/controllers/lat_based_lqr_controller/lat_controller.cc#L747)：

```cpp
const double kv =
    lr_ * mass_ / 2 / cf_ / wheelbase_ -
    lf_ * mass_ / 2 / cr_ / wheelbase_;

// 前进 / 倒车动态模型
steer_angle_feedforwardterm =
    (wheelbase_ * ref_curvature + kv * v * v * ref_curvature -
     matrix_k_(0, 2) *
         (lr_ * ref_curvature -
          lf_ * mass_ * v * v * ref_curvature / 2 / cr_ / wheelbase_)) *
    180 / M_PI * steer_ratio_ / steer_single_direction_max_degree_ * 100;
```

前两项是熟悉的稳态转角：

\[
\delta_{ff,0}=\kappa\left(L+K_vv^2\right)
\]

\[
K_v=\frac{l_r m}{2C_fL}-\frac{l_f m}{2C_rL}
\]

第三项 `-K(0,2)*(...)` 是 LQR 稳态修正：它把「航向误差反馈在稳态下
会额外产生的转角」抵消掉，使前馈更接近真正的稳态解。
`K(0,2)` 就是航向误差对应的反馈增益。

倒车且 `reverse_use_dynamic_model == false` 时使用运动学前馈：

\[
\delta_{ff}=\text{reverse\_feedforward\_ratio}\cdot L\kappa
\]

默认 `reverse_feedforward_ratio = 1.4`。

### 3.8 误差计算与目标点选择

[`ComputeLateralErrors`](../../modules/control/controllers/lat_based_lqr_controller/lat_controller.cc#L773)
与 MPC 的误差公式基本一致，但**目标点的选择逻辑不同**：

```cpp
if (query_time_nearest_point_only) {
  target_point = QueryNearestPointByAbsoluteTime(now + query_relative_time_);
} else if (navigation_mode && !enable_navigation_mode_position_update) {
  target_point = QueryNearestPointByAbsoluteTime(now + query_relative_time_);
} else {
  target_point = QueryNearestPointByPosition(x, y);
}
```

默认（非导航模式）按**位置最近**取目标点，而不是按时间。

误差：

\[
e_y=\cos\theta_r(y-y_r)-\sin\theta_r(x-x_r)
\]

\[
e_\psi=\mathrm{NormalizeAngle}(\theta-\theta_r)
\]

\[
\dot e_y=v\sin(e_\psi)
\]

\[
\dot e_\psi=\omega-\kappa_r v_r
\]

另外，`enable_look_ahead_back_control_` 打开时，会计算
`lateral_error_feedback` / `heading_error_feedback`：

- 前进：`e_y + lookahead_station * sin(e_psi)`；
- 倒车：`e_y - lookback_station * sin(e_psi)`；
- 航向误差用未来/过去点的航向差修正。

这些 feedback 值会替代原始误差进入 LQR 状态（`UpdateState` 中）。
默认配置 `enable_look_ahead_back_control: true`，`lookahead_station: 1.4224`，
`lookback_station: 2.8448`。

### 3.9 增益调度、LeadLag、MRAC

#### 增益调度

按速度插值缩放 `Q(0,0)` 和 `Q(2,2)`：

```cpp
matrix_q_updated_(0, 0) =
    matrix_q_(0, 0) * lat_err_interpolation_->Interpolate(|v|);
matrix_q_updated_(2, 2) =
    matrix_q_(2, 2) * heading_err_interpolation_->Interpolate(|v|);
```

默认表：

- 低速 4 m/s：比例 1.0；
- 8 m/s：0.6；
- 12 m/s：0.2；
- 20 m/s：0.1；
- 25 m/s：0.05。

低速更激进，高速更保守。

#### LeadLag

`enable_reverse_leadlag_compensation: true` 时启用。
在低速（或配置要求高速）时，对 `-e_y` 做 LeadLag，输出叠加到转角：

```cpp
steer_angle_feedback_augment =
    leadlag_controller_.Control(-matrix_state_(0, 0), ts_) * 180 / M_PI *
    steer_ratio_ / steer_single_direction_max_degree_ * 100;
```

#### MRAC

`enable_steer_mrac_control` 默认 `false`。打开后，LQR 输出作为参考，
MRAC 根据实际转向位置做自适应补偿，并考虑转向限幅和速率限制。
初学阶段可以先跳过。

### 3.10 限幅、滤波、低速锁止

```cpp
// 横向加速度限幅
steer_limit = FLAGS_set_steer_limit
    ? atan(max_lat_acc_ * wheelbase_ / v^2) * steer_ratio * 180/pi /
      steer_single_direction_max_degree * 100
    : 100.0;

// 最大转向速率限制（可选）
steer_diff_with_max_rate = enable_maximum_steer_rate_limit
    ? max_steer_angle_rate * ts * 180/pi / steer_single_direction_max_degree * 100
    : 100.0;

steer_angle_limited = Clamp(steer_angle, -steer_limit, steer_limit);
steer_angle = digital_filter_.Filter(steer_angle);
steer_angle = Clamp(steer_angle, -100.0, 100.0);
```

- `set_steer_limit` 默认 `true`；
- `digital_filter_` 是二阶低通，截止频率默认 10 Hz；
- 低速锁止：前进、自动模式、速度低于 `lock_steer_speed`（默认 `-0.081`，
  注意配置是负值）或上一周期 `path_remain <= 0` 时，保持上一周期转角。

> 注意：`lock_steer_speed` 默认 `-0.081`，速度条件
> `abs(v) < lock_steer_speed` 永远不会成立；但同一个 `if` 里还有
> `path_remain <= 0`，所以终点附近仍可能触发锁止。若想让速度条件生效，
> 需要把它改成正值。

### 3.11 倒车处理

```cpp
// lat_controller.cc:394-435
if (gear == GEAR_REVERSE) {
  cf_ = -conf.cf();
  cr_ = -conf.cr();
  matrix_a_(0, 1) = 0.0;
  matrix_a_coeff_(0, 2) = 1.0;
} else {
  cf_ = conf.cf();
  cr_ = conf.cr();
  matrix_a_(0, 1) = 1.0;
  matrix_a_coeff_(0, 2) = 0.0;
}
matrix_a_(1, 2) = (cf_ + cr_) / mass_;
matrix_a_(3, 2) = (lf_ * cf_ - lr_ * cr_) / iz_;
...
matrix_b_(1, 0) = cf_ / mass_;
matrix_b_(3, 0) = lf_ * cf_ / iz_;
matrix_bd_ = matrix_b_ * ts_;
```

与 MPC 不同，LAT 在倒车分支中**确实重建了** `A` 的第 2/3 行和 `B`/`Bd`。
`UpdateMatrix` 中：

```cpp
if (gear == GEAR_REVERSE && !reverse_use_dynamic_model) {
  v = min(linear_velocity, -0.1);
  matrix_a_(0, 2) = matrix_a_coeff_(0, 2) * v;  // 运动学 e_y_dot = v * e_psi
} else {
  v = max(linear_velocity, 0.1);
  matrix_a_(0, 2) = 0.0;
}
```

所以 LAT 的倒车运动学行是真正生效的，而 MPC 的同位置行没有生效
（见 04 文档第 5.6 节）。

`UpdateDrivingOrientation` 还会在倒车时把 `driving_orientation_` 加 180°，
并在 `FLAGS_reverse_heading_control` 为真时把 `B_d` 取反。

### 3.12 调用流程

```text
LatController::Init
├── LoadConfig<LatBaseLqrControllerConf>
├── LoadControlConf
├── 初始化 A/B/Q/R、A_dc/B_dc
├── InitializeFilters
├── LoadLatGainScheduler
├── Init LeadLag（可选）
└── Init MRAC（可选）

LatController::ComputeControlCommand
├── 导航模式坐标更新（可选）
├── TrajectoryAnalyzer
├── 轨迹平移到 COM（可选）
├── 倒车模型切换
├── UpdateDrivingOrientation
├── UpdateState
│    ├── ComputeLateralErrors
│    └── 填充 4 + preview_window 状态
├── UpdateMatrix
├── UpdateMatrixCompound
├── 按挡位选择 matrix_q / reverse_matrix_q
├── 增益调度
├── SolveLQRProblem
├── 反馈 + 前馈 + LeadLag
├── 横向加速度限幅
├── MRAC（可选）
├── 低通滤波 / 限幅 / 低速锁止
└── 写 steering_target / steering_rate
```

### 3.13 参数与调参

| 参数 | 默认值 | 作用 |
|---|---:|---|
| `ts` | 0.01 | 控制周期 |
| `preview_window` | 0 | 预览步数；>0 时 Q 长度要变成 4+N |
| `cf` / `cr` | 155494.663 | 前后侧偏刚度 |
| `mass_fl/fr/rl/rr` | 520×4 | 四轮质量 |
| `matrix_q` | 0.05, 0, 1.0, 0 | 横向/横向速率/航向/航向速率 |
| `matrix_r` | 1.0 | 转向控制权重 |
| `eps` | 0.01 | LQR 收敛阈值 |
| `max_iteration` | 150 | LQR 最大迭代 |
| `max_lateral_acceleration` | 5.0 | 转向限幅 |
| `cutoff_freq` | 10 | 转向低通 |
| `lookahead_station` | 1.4224 | 低速前视距离 |
| `lookback_station` | 2.8448 | 低速后视距离 |
| `switch_speed` | 2.0 | 低/高速过渡点 |
| `query_relative_time` | 0.8 | 按时间取点时的前视时间 |
| `trajectory_transform_to_com_*` | true | 轨迹平移到质心 |
| `enable_reverse_leadlag_compensation` | true | 倒车 LeadLag |
| `reverse_feedforward_ratio` | 1.4 | 倒车前馈比例 |
| `lat_err_gain_scheduler` | 表 | 横向误差权重随速度缩放 |
| `heading_err_gain_scheduler` | 表 | 航向误差权重随速度缩放 |

调参顺序建议：

1. 先确认 `cf/cr`、质量、轴距、转向比正确；
2. 调 `matrix_q(0,0)`（横向）和 `matrix_q(2,2)`（航向）；
3. 调 `matrix_r`（转向平滑度）；
4. 再调 `lookahead_station` / 增益调度；
5. 最后考虑 LeadLag / MRAC。

---

## 4. LON 纵向控制器：双环 PID

### 4.1 输入输出

**输入**：

- 规划轨迹（参考 `s`、`v`、`a`）；
- 定位/车辆状态（当前 `s`、`v`、`a`、pitch）；
- 底盘（挡位、转向、EPB）；
- `ControlCommand`（LatController 已经写入的 `steering_target`）。

**输出**：

- `throttle`、`brake`（百分比）；
- `acceleration`（m/s²）；
- `gear_location`；
- `debug.simple_lon_debug`。

### 4.2 双环 PID 结构

```text
station_error
   │
   ├─ station PID ──→ speed_offset
   │
   └─ + speed_error ──→ speed_controller_input ──→ speed PID ──→ acceleration_closed_loop
                                                                    │
                                                                    ├─ + acceleration_reference
                                                                    └─ + slope compensation
                                                                          │
                                                                          ▼
                                                                    acceleration_cmd
                                                                          │
                                                                          ▼
                                                                  2D calibration table
                                                                          │
                                                                          ▼
                                                                   throttle / brake
```

代码：

```cpp
// lon_controller.cc:265-295
double speed_offset = station_pid_controller_.Control(station_error_limited, ts);
...
double speed_controller_input = speed_offset + debug->speed_error();
speed_controller_input_limited =
    Clamp(speed_controller_input, -speed_controller_input_limit,
          speed_controller_input_limit);
double acceleration_cmd_closeloop =
    speed_pid_controller_.Control(speed_controller_input_limited, ts);
```

### 4.3 纵向误差与预览

[`ComputeLongitudinalErrors`](../../modules/control/controllers/lon_based_pid_controller/lon_controller.cc#L621)
与 MPC 的纵向误差算法一致：

- 按位置找匹配点 `s_matched`；
- 按绝对时间找参考点 `reference_point`；
- `station_error = s_ref - s_matched`；
- `speed_error = v_ref - s_dot_matched`；
- `preview_time = preview_window * ts`，默认 `20 * 0.01 = 0.2 s`；
- 预览点误差用于可选的 preview 控制。

`station_error_limit` 默认 `2.0 m`，`speed_controller_input_limit` 默认 `1.5 m/s`。

### 4.4 低速/高速/倒车/PIT PID

LON 配置里有多组 PID：位置环、低速/高速速度环、倒车、PIT。

| 场景 | 使用的 PID | 默认参数 |
|---|---|---|
| 前进低速（`v <= 3 m/s`） | `low_speed_pid_conf` | kp 2.0, ki 0.3 |
| 前进高速（`v > 3 m/s`） | `high_speed_pid_conf` | kp 1.0, ki 0.3 |
| 位置环 | `station_pid_conf` | kp 0.2, ki 0 |
| 倒车 | `reverse_station/speed_pid_conf` | kp 0.4/0.8, ki 0.1/0.3 |
| PIT（维修区） | `pit_station/speed_pid_conf` | kp 0.5/1.0, ki 0.3/0.2 |

切换逻辑在 `ComputeControlCommand` 中：

```cpp
if (gear == GEAR_REVERSE) {
  if (CheckPit::CheckInPit(...)) { pit PID }
  else { reverse PID }
} else if (v <= switch_speed) {
  if (CheckPit::CheckInPit(...)) { pit PID }
  else { station + low_speed PID }
} else {
  station + high_speed PID
}
```

`switch_speed` 默认 `3.0 m/s`，`switch_speed_window` 默认 `0`。

### 4.5 加速度、坡度与转向等待

```cpp
double vehicle_pitch_rad =
    digital_filter_pitch_angle_.Filter(vehicle_state->pitch());
double slope_offset_compensation =
    use_opposite_slope_compensation * GRA_ACC *
    sin(vehicle_pitch_rad + pitch_offset_deg * pi/180);

double acceleration_cmd =
    acceleration_cmd_closeloop + preview_acceleration_reference +
    enable_slope_offset * slope_offset_compensation;
```

- `pitch_angle_filter_conf.cutoff_freq` 默认 `5 Hz`；
- `enable_slope_offset` 默认 `false`；
- `use_opposite_slope_compensation` 默认 `1`。

**转向等待**：如果轨迹类型是 `UNKNOWN`，且
`|steering_target - chassis.steering_percentage| > steer_cmd_interval`（默认 20%），
纵向控制器会把加速度置 0、重置积分，等待转向到位：

```cpp
if (use_steering_check &&
    trajectory_type == UNKNOWN &&
    abs(current_steer_interval) > steer_cmd_interval) {
  speed_pid_controller_.Reset_integral();
  station_pid_controller_.Reset_integral();
  acceleration_cmd = 0;
  debug->set_is_wait_steer(true);
}
```

### 4.6 停车逻辑

LON 的停车逻辑比 MPC 复杂，涉及多个标志：

| 函数 | 作用 |
|---|---|
| `GetPathRemain` | 找到轨迹上的停车点，计算 `path_remain = s_stop - current_station` |
| `IsStopByDestination` | 判断 stop reason 是否是信号灯、参考线终点、开放空间前停车、任务完成 |
| `IsPedestrianStopLongTerm` | 行人/障碍物停车超过 `pedestrian_stop_time`（15 s） |
| `IsFullStopLongTerm` | 完全停车超过 `full_stop_long_time`（3 s），用于 EPB |
| `SetParkingBrake` | EPB 分阶段切换 |

主要判断：

```cpp
// 距终点小于阈值
if (drive && path_remain < max_path_remain_when_stopped ||
    reverse && path_remain > -max_path_remain_when_stopped) {
  if (is_stop_reason_by_destination || is_stop_reason_by_pedestrian) {
    is_full_stop = true;
  } else {
    is_full_stop_soft = true;
  }
}
```

- `max_path_remain_when_stopped` 默认 `0.3 m`；
- 如果上一周期已经 full stop，阈值再加上 `full_stop_path_remain_gain`（0.3）；
- `is_full_stop`：把加速度钳制到 `standstill_acceleration`（-0.3）并重置积分；
- `is_full_stop_soft`：根据 `path_remain` 和轨迹类型叠加
  `standstill_narmal_acceleration`（-0.5）或 `stop_gain_acceleration`（-1.0）；
- `use_vehicle_epb` 默认 `false`；打开后 full stop 超过 3 s 会拉 EPB。

### 4.7 标定表与油门/刹车

```cpp
double acceleration_lookup =
    (gear == GEAR_REVERSE) ? -acceleration_cmd : acceleration_cmd;

calibration_value = control_interpolation_->Interpolate(
    std::make_pair(std::fabs(speed), acceleration_lookup));
```

- 速度默认用当前车速 `|v|`；`FLAGS_use_preview_speed_for_table` 为真时用预览速度；
- 标定表条目：`speed`、`acceleration`、`command`；
- `command >= 0` 走油门，`command < 0` 走刹车；
- 最终：

```cpp
if (acceleration_lookup >= 0) {
  throttle_cmd = max(calibration_value, throttle_lowerbound);
  brake_cmd = 0;
} else {
  throttle_cmd = 0;
  brake_cmd = max(-calibration_value, brake_lowerbound);
}
```

`throttle_lowerbound` / `brake_lowerbound` 取车辆死区和配置的较大值。

### 4.8 调用流程

```text
LonController::Init
├── LoadConfig<LonBasedPidControllerConf>
├── LoadCalibrationTable
├── Init station/speed PID
├── Init LeadLag（可选）
├── SetDigitalFilterPitchAngle
└── InitControlCalibrationTable

LonController::ComputeControlCommand
├── TrajectoryAnalyzer（按 sequence_num 复用）
├── ComputeLongitudinalErrors
├── station_error 限幅
├── 选择 PID（前进/倒车/PIT/高低速）
├── station PID → speed_offset
├── + speed_error → speed_controller_input（限幅）
├── speed PID → acceleration_closeloop
├── 坡度补偿
├── acceleration_cmd
├── 转向等待检查（可选）
├── GetPathRemain / 停车判断
├── full stop / soft stop 处理
├── 2D 标定表 → throttle / brake
├── EPB（可选）
├── 写 throttle / brake / acceleration / gear
└── speed interface（可选）
```

### 4.9 参数与调参

| 参数 | 默认值 | 作用 |
|---|---:|---|
| `ts` | 0.01 | 控制周期 |
| `preview_window` | 20.0 | 预览步数（× ts = 0.2 s） |
| `station_error_limit` | 2.0 | 位置误差限幅 (m) |
| `speed_controller_input_limit` | 1.5 | 速度环输入限幅 (m/s) |
| `station_pid_conf` | kp 0.2, ki 0 | 位置环 |
| `low_speed_pid_conf` | kp 2.0, ki 0.3 | 低速速度环 |
| `high_speed_pid_conf` | kp 1.0, ki 0.3 | 高速速度环 |
| `switch_speed` | 3.0 | 高低速切换 (m/s) |
| `standstill_acceleration` | -0.3 | 停车保持加速度 |
| `standstill_narmal_acceleration` | -0.5 | 软停车加速度 |
| `stop_gain_acceleration` | -1.0 | 停车增益 |
| `max_path_remain_when_stopped` | 0.3 | 停车距离阈值 |
| `pedestrian_stop_time` | 15 | 行人停车判断时间 (s) |
| `full_stop_long_time` | 3.0 | EPB 触发时间 (s) |
| `use_steering_check` | true | 转向未到位时暂停加速 |
| `steer_cmd_interval` | 20.0 | 转向差阈值 (%) |
| `use_lookup_acc_pid` | — | MPC 中才有；LON 用双环 PID |

调参顺序：

1. 先调速度环 `low_speed_pid_conf` / `high_speed_pid_conf`；
2. 再调位置环 `station_pid_conf`（kp 从小到大）；
3. 用 `preview_window` 改善跟车/停车的前瞻性；
4. 检查标定表是否匹配车型；
5. 最后调停车阈值和 EPB。

---

## 5. LAT/LON 与 MPC 的对比

| 维度 | LAT + LON | MPC |
|---|---|---|
| 控制结构 | 横向 LQR + 纵向双环 PID，分解控制 | 横纵向联合，QP 优化 |
| 状态 | LAT 4 状态（+预览）；LON 误差标量 | 6 状态 |
| 控制量 | 转角；油门/刹车 | 转角 + 加速度 |
| 约束 | 转角限幅/速率、横向加速度限幅；PID 积分饱和 | 显式控制/状态约束 |
| 前馈 | 曲率前馈 + LQR 稳态修正 | 曲率前馈 + 误差调节 |
| 预览 | LAT 预览窗口；LON 预览时间 | 固定 10 步，无显式预览 |
| 求解 | 每周期 DARE + PID | 每周期 OSQP |
| 调参 | Q/R + PID + 增益调度 | Q/R + 约束 + 增益调度 |
| 倒车 | 重建 A/B，运动学行生效 | 重建不完整（见 04 文档） |
| 优点 | 简单、可解释、鲁棒、计算量小 | 能处理约束、联合优化、理论统一 |
| 缺点 | 横纵向解耦，约束只能事后限幅 | 模型敏感、求解器调参、时域短 |

学习建议：

1. 先用 LAT/LON 理解「误差 → 反馈 + 前馈 → 执行器」的经典链路；
2. 再看 MPC 如何把同样的误差放进一个 QP；
3. 最后在同一路线对比两者，重点看：
   - 横向误差和航向误差；
   - 转向平滑度；
   - 停车精度；
   - 计算耗时。

---

## 6. 源码阅读注意点

1. **`lock_steer_speed` 默认是负数**：`abs(v) < -0.081` 永远不成立，
   低速锁止默认不生效。使用时改成正值。
2. **LAT 的 `preview_window` 改变 Q 长度**：`matrix_q` 和
   `reverse_matrix_q` 都必须等于 `4 + preview_window`，否则初始化失败。
3. **LAT 默认按位置取目标点**：不是按时间；这与 MPC 的纵向参考点
   （按绝对时间）不同。回放旧数据包时，LAT 的横向误差通常仍然可用，
   但 LON 的 `station_error` 会受到旧时间戳影响（见 02 文档）。
4. **LON 的 `preview_window` 是 double**：`20.0` 表示 20 个控制周期，
   不是 20 秒。
5. **LON 的停车逻辑有多个阈值**：`max_path_remain_when_stopped`、
   `standstill_acceleration`、`stop_gain_acceleration` 等，
   调参时要一起看。
6. **`use_steering_check`**：轨迹类型为 `UNKNOWN` 时，转向未到位会
   暂停加速；这会影响起步/停车附近的表现。
7. **LAT 的 LeadLag 默认开启**：`enable_reverse_leadlag_compensation: true`，
   但只在低速或配置要求高速时生效；不要误以为它一直工作。
8. **MRAC 默认关闭**：初学阶段可以先忽略 `mrac_controller`。
9. **标定表是纵向控制的核心**：`calibration_table.pb.txt` 不匹配车型时，
   PID 输出再正确，油门/刹车也会不准。
10. **LAT/LON 与 MPC 的 pipeline 互斥**：不要同时把三者放在 pipeline 里，
    后执行的控制器会覆盖前面的输出。

---

## 7. 源码索引

| 文件 | 关键内容 | 行号 |
|---|---|---|
| [`lat_controller.h`](../../modules/control/controllers/lat_based_lqr_controller/lat_controller.h) | 类声明、状态/矩阵成员 | 57 类定义 |
| [`lat_controller.cc`](../../modules/control/controllers/lat_based_lqr_controller/lat_controller.cc) | 加载配置 | 87 `LoadControlConf` |
| 同上 | 初始化 | 177 `Init` |
| 同上 | 主入口 | 304 `ComputeControlCommand` |
| 同上 | 重置 | 647 `Reset` |
| 同上 | 状态更新 | 655 `UpdateState` |
| 同上 | 矩阵更新 | 711 `UpdateMatrix` |
| 同上 | 预览增广 | 734 `UpdateMatrixCompound` |
| 同上 | 前馈 | 747 `ComputeFeedForward` |
| 同上 | 横向误差 | 773 `ComputeLateralErrors` |
| 同上 | 倒车方向 | 920 `UpdateDrivingOrientation` |
| [`lat_based_lqr_controller_conf.proto`](../../modules/control/controllers/lat_based_lqr_controller/proto/lat_based_lqr_controller_conf.proto) | 配置字段 | 9 |
| [`lat 配置`](../../modules/control/controllers/lat_based_lqr_controller/conf/controller_conf.pb.txt) | 默认参数 | 1–104 |
| [`lon_controller.h`](../../modules/control/controllers/lon_based_pid_controller/lon_controller.h) | 类声明 | 55 类定义 |
| [`lon_controller.cc`](../../modules/control/controllers/lon_based_pid_controller/lon_controller.cc) | 初始化 | 102 `Init` |
| 同上 | 主入口 | 169 `ComputeControlCommand` |
| 同上 | 重置 | 613 `Reset` |
| 同上 | 纵向误差 | 621 `ComputeLongitudinalErrors` |
| 同上 | 路径剩余 | 718 `GetPathRemain` |
| 同上 | 终点停车 | 763 `IsStopByDestination` |
| 同上 | 行人停车 | 785 `IsPedestrianStopLongTerm` |
| 同上 | 长时间停车 | 834 `IsFullStopLongTerm` |
| 同上 | EPB | 865 `SetParkingBrake` |
| [`lon_based_pid_controller_conf.proto`](../../modules/control/controllers/lon_based_pid_controller/proto/lon_based_pid_controller_conf.proto) | 配置字段 | 12 |
| [`lon 配置`](../../modules/control/controllers/lon_based_pid_controller/conf/controller_conf.pb.txt) | 默认参数 | 1–92 |
| [`linear_quadratic_regulator.cc`](../../modules/common/math/linear_quadratic_regulator.cc) | LQR/DARE | 33 / 82 |
| [`pid_controller.cc`](../../modules/control/control_component/controller_task_base/common/pid_controller.cc) | PID | 27 `Control` |
| [`trajectory_analyzer.cc`](../../modules/control/control_component/controller_task_base/common/trajectory_analyzer.cc) | 轨迹/误差 | 72、109、154 |
| [`lat_lon_controller_submodule.cc`](../../modules/control/control_component/submodules/lat_lon_controller_submodule.cc) | submodule 调用 | 45、73、123 |
| [`control_cmd.proto`](../../modules/common_msgs/control_msgs/control_cmd.proto) | 调试消息 | 76 `SimpleLongitudinalDebug`、121 `SimpleLateralDebug` |
