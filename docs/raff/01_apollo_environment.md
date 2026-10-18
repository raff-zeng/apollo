# Apollo 工作环境与开发流程入门

> 面向第一次使用 Apollo 的开发者。目标不是背命令，而是建立一张「代码在哪里、怎么编译、怎么跑、怎么看」的地图。
> 所有命令默认在仓库根目录 `/home/zrf/apollo` 下执行；标注「容器内」的命令必须先进入 Docker 开发容器。

## 1. 先建立全局认识

Apollo 不是一个单独的程序，而是「一个通信框架 + 一组功能模块 + 一套开发工具」：

| 层次 | 目录 | 作用 |
|---|---|---|
| 通信框架 | `cyber/` | CyberRT：节点、组件、Channel、DAG、Launch、录制/回放 |
| 消息定义 | `modules/common_msgs/` | 所有 protobuf 消息，例如 `ADCTrajectory`、`Chassis`、`ControlCommand` |
| 基础库 | `modules/common/` | 数学、滤波、车辆状态、配置、日志等公共能力 |
| 功能模块 | `modules/perception/`、`localization/`、`planning/`、`control/`、`canbus/` 等 | 感知、定位、规划、控制、底盘 |
| 可视化/工具 | `modules/dreamview/`、`modules/tools/`、`cyber/tools/` | DreamView、数据回放、调试工具 |
| 构建与脚本 | `apollo.sh`、`scripts/`、`tools/` | Bazel 封装、格式化、lint、发布 |
| 文档 | `docs/` | 官方文档；本目录 `docs/raff/` 是个人学习笔记 |

一个自动驾驶周期大致是：

```text
传感器 → perception → prediction → planning（输出 ADCTrajectory）
                                      ↓
localization + chassis + planning → control（本笔记重点）→ ControlCommand
                                      ↓
                                    canbus → 车辆执行
```

Control 模块订阅 `/apollo/planning`、`/apollo/localization/pose`、`/apollo/canbus/chassis`，
计算后发布 `/apollo/control`。MPC 是 Control 模块内部的一个控制器插件。

## 2. 仓库目录地图

```text
apollo/
├── apollo.sh                     # 构建/测试/lint/format 的统一入口
├── WORKSPACE                     # Bazel 工作区
├── cyber/                        # CyberRT 框架与工具
│   ├── tools/cyber_launch/       # cyber_launch
│   ├── tools/cyber_monitor/      # cyber_monitor
│   ├── tools/cyber_recorder/     # cyber_recorder
│   └── setup.bash                # 容器内 source 后可使用 cyber_* 工具
├── modules/
│   ├── common/                   # 公共库（math、filters、vehicle_state、configs）
│   ├── common_msgs/              # protobuf 消息
│   ├── control/
│   │   ├── control_component/    # Control 组件、任务基类、子模块、DAG/launch/conf
│   │   └── controllers/          # 控制器插件：lat/lon/mpc/...
│   ├── planning/
│   ├── localization/
│   ├── canbus/
│   └── dreamview/
├── docs/                         # 官方文档 + docs/raff 个人笔记
├── scripts/                      # apollo.sh 背后的脚本、模块启动脚本
├── tools/                        # clangd、cpplint、包管理等工具
├── data/                         # 运行日志、core、录包、agent 会话日志
└── docker/scripts/               # 开发容器启动/进入脚本
```

几个第一次容易混淆的点：

- `modules/control/control_component/` 才是 Control 组件的实际源码目录；
  部分 README 和 DAG 里写的 `modules/control/dag/`、`modules/control/conf/`
  是旧路径，当前仓库中不存在。
- `modules/control/controllers/` 下每个子目录是一个**插件包**，有自己的
  `BUILD`、`cyberfile.xml`、`plugins.xml`、`proto/`、`conf/`。
- `bazel-bin/`、`bazel-out/` 等是构建产物软链接，指向容器内 `.cache/bazel/...`；
  在宿主机上看到它们断链属于正常现象。

## 3. Docker 开发容器

### 3.1 为什么用容器

Apollo 的依赖（特定版本的 Bazel、CUDA、系统库、第三方库）都封装在开发镜像里。
宿主机只负责运行 Docker；**编译、运行、调试都在容器内完成**。

### 3.2 启动容器

宿主机执行：

```bash
cd /home/zrf/apollo
bash docker/scripts/dev_start.sh -y
```

首次执行会拉取镜像，耗时较长；之后会复用已存在的 `apollo_dev_<用户名>` 容器。

常用参数：

| 参数 | 作用 |
|---|---|
| `-y` | 非交互式同意 License，适合脚本化 |
| `-l` / `--local` | 使用本地已有镜像，不联网拉取 |
| `-t <tag>` | 指定镜像 tag |
| `-f` / `--fast` | 快速模式，不挂载全部地图 volume |
| `-g <us\|cn\|none>` | 选择镜像仓库区域 |
| `stop` | 停止所有 Apollo 容器 |

当前机器上的容器为 `apollo_dev_zrf`，镜像为
`registry.baidubce.com/apolloauto/apollo:dev-x86_64-18.04-20231128_2222`。
检查容器状态：

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
```

### 3.3 进入 / 退出容器

```bash
# 宿主机：进入容器（容器未启动时会尝试启动已停止的同名容器）
bash docker/scripts/dev_into.sh

# 容器内：退出
exit
```

进入容器后，仓库在 `/apollo`，当前用户与宿主机一致。建议先确认工具链：

```bash
# 容器内
source /apollo/cyber/setup.bash
bazel --version
which cyber_launch mainboard cyber_monitor cyber_recorder
nvidia-smi        # 有 GPU 时检查驱动是否可见
```

### 3.4 容器与宿主机的文件关系

- 仓库目录以 volume 方式挂载：宿主机 `/home/zrf/apollo` = 容器内 `/apollo`。
- 在容器内改代码，宿主机立即可见，反之亦然。
- 构建缓存 `.cache/` 也在仓库下，因此容器重建后缓存通常还在。
- `data/log/`、`data/core/` 用于运行日志和 core dump。

## 4. 构建

### 4.1 统一入口：`apollo.sh`

Apollo 用 Bazel 构建，但不要直接敲 `bazel build`，而是用封装脚本 `apollo.sh`。
它会处理环境变量、编译选项、模块名简写等。

```bash
# 容器内，仓库根目录
./apollo.sh build                # 全量构建（很慢，第一次可能几十分钟）
./apollo.sh build control        # 只构建 modules/control
./apollo.sh build cyber          # 只构建 cyber 框架
./apollo.sh build_opt control    # 优化构建（-c opt）
./apollo.sh build_dbg control    # 调试构建（-c dbg，便于 gdb）
./apollo.sh build_cpu control    # CPU 模式
./apollo.sh build_gpu control    # GPU 模式
```

模块名规则：`cyber` 表示 `//cyber`，其他名字表示 `//modules/<name>`。
也可以直接传 Bazel 目标，例如：

```bash
./apollo.sh build //modules/control/controllers/mpc_controller:libmpc_controller.so
```

### 4.2 控制并发与内存

仓库根目录的笔记文件里记录了一个常用设置：

```bash
export APOLLO_BUILD_JOBS=16
./apollo.sh build
```

机器内存较小时建议降低并发，否则容易 OOM 或被系统 kill。

### 4.3 测试、lint、格式化

```bash
./apollo.sh test control         # 运行 modules/control 的单元测试
./apollo.sh lint                 # cpplint 风格检查
./apollo.sh format -c <path>     # 仅 clang-format 格式化 C/C++/proto
./apollo.sh format <path>        # 按扩展名分派格式化
./apollo.sh check                # build + test + lint（提交前）
```

MPC 单元测试可以直接跑：

```bash
# 容器内
bazel test //modules/control/controllers/mpc_controller:mpc_controller_test
```

### 4.4 构建产物在哪里

- `bazel-bin/`：最终二进制和共享库，例如
  `bazel-bin/modules/control/controllers/mpc_controller/libmpc_controller.so`。
- `bazel-bin/cyber/tools/cyber_launch/cyber_launch`：CyberRT 工具。
- `bazel-out/`：中间产物。
- `compile_commands.json`：clangd 使用的编译数据库，由 `tools/clangd/refresh.sh` 生成。

### 4.5 清理

```bash
./apollo.sh clean                # 清理 bazel 输出、core、日志
./apollo.sh clean --expunge      # 彻底清理 bazel 缓存（很慢）
```

如果更换了 Docker 镜像或工具链，官方建议删除旧缓存：

```bash
rm -rf /apollo/.cache/{bazel,build,repos}
```

### 4.6 构建常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `bazel: command not found` | 在宿主机执行 | 进容器后再构建 |
| 拉取依赖超时 | 网络/镜像源 | 检查网络；必要时配置代理或 `-l` 使用本地镜像 |
| 编译到一半被 kill | 内存不足 | 降低 `APOLLO_BUILD_JOBS` |
| 修改代码后行为没变 | 没重新构建，或启动的是旧二进制 | 重新 `./apollo.sh build control`，确认 `cyber_launch` 加载的是新库 |
| `bazel-*` 断链 | 宿主机看不到容器内 `/apollo/.cache` | 正常现象，不影响容器内构建 |

## 5. 运行与观察

### 5.1 CyberRT 的核心概念

| 概念 | 含义 | 本仓库例子 |
|---|---|---|
| Component | 可被框架调度的计算单元 | `ControlComponent`、`MPCControllerSubmodule` |
| DAG | 一个进程内的组件装配文件 | `modules/control/control_component/dag/control.dag` |
| Launch | 启动一个或多个 DAG 的 XML | `modules/control/control_component/launch/control.launch` |
| Channel | 发布/订阅的话题 | `/apollo/planning`、`/apollo/control` |
| Record | 录制/回放的文件格式 | `*.record` |

两种启动方式等价：

```bash
cyber_launch start modules/control/control_component/launch/control.launch
# 或
mainboard -d modules/control/control_component/dag/control.dag
```

`cyber_launch` 适合日常启动；`mainboard -d` 适合单 DAG 调试。

### 5.2 启动 Control

```bash
# 容器内，仓库根目录
source /apollo/cyber/setup.bash
cyber_launch start modules/control/control_component/launch/control.launch
```

停止：

```bash
cyber_launch stop modules/control/control_component/launch/control.launch
```

查看进程和话题：

```bash
cyber_node list
cyber_monitor
```

**注意**：`scripts/control.sh start` 依赖 `modules/control/launch/control.launch`，
当前源码布局下该路径不存在，因此第一次使用时建议直接用上面的
`control_component/launch/control.launch`。

### 5.3 DreamView

DreamView 是 Apollo 的 Web 可视化界面，可以看车辆、轨迹、模块状态和播放数据包。

```bash
# 容器内
source /apollo/cyber/setup.bash
./scripts/bootstrap.sh start          # 经典 DreamView（本仓库默认也是 8888）
# 或
./scripts/bootstrap.sh start_plus     # DreamView+，默认 http://localhost:8888
```

浏览器访问对应端口。两种方式都默认使用 8888，只能二选一；
切换前先执行下面的停止命令，否则端口被占用会导致新后端启动失败。停止：

```bash
./scripts/bootstrap.sh stop
# 或
./scripts/bootstrap.sh stop_plus
```

DreamView 启动失败时，先看：

```bash
tail -n 100 /apollo/nohup.out
ls /apollo/data/log
```

### 5.4 录制与回放

```bash
# 查看录包信息
cyber_recorder info demo.record

# 回放（-l 循环，-r 倍速）
cyber_recorder play -f demo.record -l
cyber_recorder play -f demo.record -r 0.5

# 只录制控制相关话题
cyber_recorder record -c /apollo/planning -c /apollo/localization/pose \
  -c /apollo/canbus/chassis -c /apollo/control -o control.record

# 只回放某些话题
cyber_recorder play -f demo.record -c /apollo/planning -c /apollo/control
```

回放时如果 Control 没启动，`/apollo/control` 不会有新消息；
如果 Control 启动了但没有规划轨迹，会触发 estop。

### 5.5 观察控制输出

```bash
# 只看控制话题
cyber_monitor -c /apollo/control

# 看所有通道
cyber_monitor
```

`cyber_monitor` 常用键：

- `↑/↓` 或 `w/s`：移动光标
- `→` 或 `d`：进入通道查看详细 protobuf
- `←` 或 `a`：返回
- `q` / `Esc`：退出

MPC 的调试信息在 `ControlCommand.debug.simple_mpc_debug` 中，
包括 `lateral_error`、`heading_error`、`station_error`、`speed_error`、
`steer_angle_feedback`、`steer_angle_feedforward`、`matrix_q_updated` 等字段。
详见 [04_mpc_controller_source_notes.md](04_mpc_controller_source_notes.md)。

### 5.6 日志位置

| 路径 | 内容 |
|---|---|
| `data/log/` | 各模块/工具的 INFO/WARNING/ERROR 日志 |
| `data/core/` | core dump |
| `/apollo/nohup.out` | `scripts/bootstrap.sh` 等 nohup 启动的后台输出 |
| `/tmp/mpc_controller_*.csv` | MPC 构造函数在 `FLAGS_enable_csv_debug=true` 时创建的文件（当前 `ProcessLogs` 为空，实际不会写入数据） |

## 6. 一次完整的开发闭环

以「修改 MPC 的 `matrix_q` 并观察效果」为例：

```bash
# 0. 宿主机进容器
cd /home/zrf/apollo
bash docker/scripts/dev_into.sh

# 1. 改配置
#    编辑 modules/control/controllers/mpc_controller/conf/controller_conf.pb.txt
#    例如把 matrix_q 的第一个值 40.0 改成 60.0

# 2. 编译（配置是运行时读取的，通常不必重编；但改 C++ 必须重编）
./apollo.sh build control

# 3. 启动控制模块（确保 pipeline 中启用了 MPC，见 04 文档）
cyber_launch start modules/control/control_component/launch/control.launch

# 4. 播放数据包
cyber_recorder play -f /path/to/demo.record -l

# 5. 另开终端观察
bash docker/scripts/dev_into.sh
source /apollo/cyber/setup.bash
cyber_monitor -c /apollo/control
```

改 C++ 时的推荐验证顺序：

```text
clang-format -> 编译目标模块 -> 单元测试 -> 启动模块/播包 -> 看日志和话题 -> 录包复盘
```

格式化与 lint：

```bash
./apollo.sh format -c modules/control/controllers/mpc_controller
./apollo.sh lint
```

## 7. 常见问题（FAQ）

### Q1：为什么不能在宿主机直接跑 bazel？

宿主机没有 Apollo 的完整工具链和 sysroot；`bazel-*` 软链接也指向容器内路径。
统一在容器内执行 `./apollo.sh ...`。

### Q2：`cyber_launch` 提示找不到 DAG 或模块库？

优先检查路径。当前源码中：

- 正确 DAG：`modules/control/control_component/dag/control.dag`
- 正确 launch：`modules/control/control_component/launch/control.launch`
- 正确模块库：`modules/control/control_component/libcontrol_component.so`

而 `mpc_module.dag` / `lateral_longitudinal_module.dag` 里的
`module_library: "modules/control/libcontrol_component.so"` 和
`flag_file_path: "/apollo/modules/control/conf/control.conf"` 是旧路径，
使用 submodule 模式前需要改成 `control_component/` 下的实际路径。

### Q3：DreamView 打不开？

- 确认进程：`./scripts/dreamview.sh status` 或 `ps aux | grep dreamview`
- 确认端口：本仓库经典版和 Plus 版默认都是 `8888`，不能同时启动
- 看进程名：`ss -ltnp | grep 8888`，DreamView+ 应为 `dreamview_plus`
- 看日志：`/apollo/nohup.out`、`data/log/`
- 远程机器需要把端口映射到本地，或在有浏览器的机器上访问

### Q4：播包后 Control 没有输出？

按顺序检查：

1. `/apollo/planning` 是否有数据：`cyber_monitor -c /apollo/planning`
2. `/apollo/localization/pose` 和 `/apollo/canbus/chassis` 是否有数据
3. Control 进程是否启动：`cyber_node list`
4. **底盘驾驶模式是否为 `COMPLETE_AUTO_DRIVE`**：`ControlComponent::Proc`
   只有在完全自动驾驶模式下才会调用控制器；手动模式或未使能时输出零控制指令
5. 是否触发 estop：看 `data/log/` 中 control 的日志
6. 如果轨迹为空或时间戳超时，Control 会输出 estop 指令而不是正常控制

### Q5：编译很慢 / 磁盘占用大？

- 只构建需要的模块：`./apollo.sh build control`
- 定期清理：`./apollo.sh clean`
- 彻底清理缓存：`./apollo.sh clean --expunge`（之后第一次构建会很慢）

### Q6：clangd 跳转失效？

```bash
# 容器内重新生成 compile_commands.json
tools/clangd/refresh.sh
```

然后在 VS Code 执行 `clangd: Restart language server`。

## 8. 建议的学习路线（10 天）

| 天 | 目标 | 产出 |
|---|---|---|
| 1 | 进容器、编译 control、启动/停止模块 | 能独立完成构建和启动 |
| 2 | 熟悉 CyberRT：DAG、launch、channel、录制回放 | 能播包并用 `cyber_monitor` 看数据 |
| 3 | 读 Control 组件：`ControlComponent`、`ControlTaskAgent`、`ControlTask` | 画出 Control 的调用框图 |
| 4 | 读 LAT/LON 控制器，理解横纵向分解 | 能说清 Frenet 坐标下的 s/d |
| 5 | 读 MPC 的误差计算：`ComputeLateralErrors`、`ComputeLongitudinalErrors` | 能手推 d、θ_e、s_e、v_e |
| 6 | 读预测模型：A/B/C 矩阵、Tustin 离散化 | 能写出 6 状态方程 |
| 7 | 读代价函数与约束，对照 `mpc_osqp.cc` | 能说清 P、q、A、l、u 的维度 |
| 8 | 读执行器链路：前馈、限幅、滤波、标定表 | 能画出从转角到 throttle/brake 的流程 |
| 9 | 改 Q/R、增益调度，播包对比 | 有一组可解释的调参实验 |
| 10 | 复盘并写自己的笔记/提交 | 形成可复用的知识库 |

## 9. 速查表

```bash
# ===== 宿主机 =====
bash docker/scripts/dev_start.sh -y          # 启动容器
bash docker/scripts/dev_into.sh              # 进入容器
docker ps                                    # 查看容器

# ===== 容器内 =====
source /apollo/cyber/setup.bash               # CyberRT 环境
./apollo.sh build control                     # 构建 control
./apollo.sh test control                      # 测试
./apollo.sh lint                              # 风格检查
./apollo.sh format -c <path>                  # 格式化
tools/clangd/refresh.sh                       # 刷新 clangd 数据库

cyber_launch start modules/control/control_component/launch/control.launch
cyber_launch stop  modules/control/control_component/launch/control.launch
./scripts/bootstrap.sh start                  # 经典 DreamView（默认 8888）
./scripts/bootstrap.sh start_plus             # DreamView+（默认 8888）

cyber_monitor                                 # 看所有 channel
cyber_monitor -c /apollo/control              # 看控制指令
cyber_recorder info demo.record               # 录包信息
cyber_recorder play -f demo.record -l         # 循环回放
cyber_recorder record -a -o all.record        # 录制全部
```
