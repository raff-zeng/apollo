# Apollo 源码学习指南（控制方向）

本目录是个人 fork（`raff-zeng/apollo`，学习分支 `zrf`）的 Apollo 学习笔记，目标是帮助第一次接触 Apollo 的开发者从「能把环境跑起来」走到「能读懂并修改 LAT / LON / MPC 控制器」。

阅读基线：当前仓库 `zrf` 分支 HEAD。源码行号以当前仓库为准。

## 文档地图

| 文档 | 适合什么时候读 | 内容 |
|---|---|---|
| [01_apollo_environment.md](01_apollo_environment.md) | 第一次使用 Apollo | Docker 容器、目录结构、构建、启动、录包/播包、调试工具、常见坑 |
| [02_control_learning_task.md](02_control_learning_task.md) | 想动手跑任务 | 环境准备、推荐驾驶任务（SimControl）、LAT/LON 与 MPC 对比实验、数据采集 |
| [03_lat_lon_controller_source_notes.md](03_lat_lon_controller_source_notes.md) | 学习默认控制方案 | LAT 横向 LQR、LON 纵向双环 PID、停车逻辑、标定表、调参 |
| [04_mpc_controller_source_notes.md](04_mpc_controller_source_notes.md) | 学习 MPC | 文件结构、横纵向误差、预测模型、代价函数、约束、OSQP、完整调用流程、调参 |
| [05_source_index.md](05_source_index.md) | 读代码时随手查 | 源码、消息、配置、文档的逐文件索引与阅读优先级 |

建议顺序：

1. 先读 01，完成「进容器 → 编译 control → 启动 → 观察话题」的闭环；
2. 再读 02，按推荐任务把 Planning / Routing / Control 跑起来；
3. 然后读 03，理解默认的 LAT/LON 控制链路；
4. 再读 04 的第 1～3 节建立 MPC 框架，精读第 4～8 节对照源码看数学如何落到矩阵和 QP；
5. 最后用 05 作为索引，按「调用链」把相关文件串起来读一遍。

## 5 分钟跑通（当前机器）

当前机器上的开发容器名为 `apollo_dev_zrf`，镜像为
`registry.baidubce.com/apolloauto/apollo:dev-x86_64-18.04-20231128_2222`，
仓库通过 `/apollo` 挂载进容器。

```bash
# 1. 宿主机：启动并进入开发容器
cd /home/zrf/apollo
bash docker/scripts/dev_start.sh -y      # 首次会拉取镜像，已有容器则复用
bash docker/scripts/dev_into.sh          # 进入后提示符通常在 /apollo

# 2. 容器内：编译 control 模块
cd /apollo
export APOLLO_BUILD_JOBS=16
./apollo.sh build control

# 3. 启动默认控制管线（LAT + LON）
cyber_launch start modules/control/control_component/launch/control.launch

# 4. 另开一个终端进入容器，观察控制话题
bash docker/scripts/dev_into.sh
source /apollo/cyber/setup.bash
cyber_monitor -c /apollo/control
```

> 默认的 `pipeline.pb.txt` 里是 `LatController + LonController`，**MPC 不会自动启用**。
> 启用 MPC 的两种方式和具体步骤见
> [04_mpc_controller_source_notes.md](04_mpc_controller_source_notes.md#1-mpc-在-control-模块中的位置)。
>
> 想跑完整的「规划 + 控制」任务，见
> [02_control_learning_task.md](02_control_learning_task.md)。
> 当前 checkout 可直接使用的地图是 `demo` 和 `borregas_ave`；
> `modules/map/data/sunnyvale*` 目录为空，官方文档里的 Sunnyvale Big Loop 暂不可用。

## 约定

- 文中路径默认相对仓库根目录 `/home/zrf/apollo`。
- 所有 bazel 构建、`cyber_*` 工具、`mainboard` 都必须在 Docker 开发容器内执行；宿主机没有完整工具链。
- 代码链接使用相对本目录的路径，例如
  [`mpc_controller.cc`](../../modules/control/controllers/mpc_controller/mpc_controller.cc)。
- 提交信息遵循仓库 `CLAUDE.md` 的 conventional commit 规范。

## 当前仓库状态提示

- 根目录的 `bazel-*` 是指向容器内 `/apollo/.cache/bazel/...` 的软链接，宿主机上看到断链是正常的。
- `compile_commands.json` 已由 `tools/clangd/refresh.sh` 生成，clangd 跳转配置见 `.clangd` 与 `tools/clangd/`。
- 源码中部分 README/DAG 的路径仍是旧目录结构（例如 `modules/control/dag/...`、`modules/control/conf/...`），
  实际文件在 `modules/control/control_component/` 下。第一次运行失败时优先检查路径。
