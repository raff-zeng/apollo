# CLAUDE.md

本文件是本仓库(个人 fork 的 Apollo 源码)的工作约定,供 Claude Code(agent)与开发者共同遵守。核心内容:git 提交规范、clangd 配置、MPC 学习目标。

## 项目概况

- 上游:Apollo(百度自动驾驶开源平台),本仓库为个人 fork
- remote:`origin` → `git@github.com:raff-zeng/apollo.git`
- 分支:主线 `master`,当前学习/开发分支 `zrf`(基于 `origin/master`)
- 学习目标:以源码为基础学习 MPC(Model Predictive Control)自动驾驶控制

## 构建 / 格式化 / lint

Apollo 的 bazel 构建**必须在 Docker 开发容器内**执行(host 上没有 bazel,`bazel-*` 软链指向容器内 `/apollo/.cache`)。常用命令:

```bash
./apollo.sh build [module]          # 构建(cyber 或 modules/<module>)
./apollo.sh build_opt [module]      # 优化构建
./apollo.sh lint                    # cpplint 代码风格检查
./apollo.sh format <path>           # 全量格式化(按扩展名分派)
./apollo.sh format -c <path>        # 仅 clang-format 格式化 C/C++/CUDA/proto
./apollo.sh check                   # build + test + lint(提交/PR 前)
```

> ⚠️ 不要在 host 直接跑 bazel。进入容器后再执行上述命令。

## Git 提交规范(与 Apollo 一致)

remote 指向个人 fork;提交信息采用 **conventional commit** 前缀(与 Apollo 提交历史一致),并遵循 Apollo `CONTRIBUTING.md` 的"一行摘要 + 可选正文"约定:

```
<type>: <一句话摘要>

<可选正文:说明做了什么、为什么>

Fixes #<issue>   # 如修复 issue
```

- `type` 取值:`feat` / `fix` / `docs` / `chore` / `refactor` / `test` / `build` / `perf` / `style`
- 摘要:英文、小写、祈使句、≤72 字符,结尾不加句号
- 示例:
  - `feat: add Apollo 11.0 bev+occ`
  - `docs: add cn docs`
  - `chore: comment seyond module and update docker image for 40XX GPU`
  - `fix: correct lateral error sign in mpc controller`
- 正文:(与 subject 之间空一行):说明做了什么、为什么,先用英文写一遍,再使用中文再翻译一遍

已配置 `git config commit.template = /home/zrf/apollo/.gitmessage`,交互式提交时会自动带出模板。

## clangd 配置

### 格式化(已就绪)

- 根目录 `.clang-format`(Google 风格)由 clangd 直接读取,无需额外配置
- `.vscode/settings.json` 已把 clangd 设为 C/C++/CUDA 的默认格式化器并开启 formatOnSave
- 等价命令行:`./apollo.sh format -c <path>`

## MPC 源码地图(学习重点)

- 控制器实现:`modules/control/controllers/mpc_controller/mpc_controller.{h,cc}`
- QP 求解器(OSQP 封装):`modules/common/math/mpc_osqp.{h,cc}`
- 控制组件子模块:`modules/control/control_component/submodules/mpc_controller_submodule.{h,cc}`
- 配置/协议:`modules/control/controllers/mpc_controller/conf/controller_conf.pb.txt`、`proto/mpc_controller.proto`
- 官方文档:`modules/control/controllers/mpc_controller/README_cn.md`、`docs/10_Control/`

## 工作约定(agent)

- 用中文与用户交流
- 不在 host 运行 bazel 构建;构建/生成 compile_commands 需进容器
- 提交信息遵循上文"Git 提交规范"
- 改动某模块前先看对应 `BUILD` / `cyberfile.xml`,了解依赖与目标结构

## Agent 会话日志

- 按月归档,保存路径:`./data/agent/<YYYYMM>/`,如 2026 年 10 月为 `./data/agent/202610/`
- 同一个会话记录为一个 `.md` 文件,文件名以日期为前缀:`<YYYYMMDD>_<会话标识>.md`,如 `20261019_<session-id>.md`
- 同一会话内持续追加到同一文件,不新建文件;会话结束前完成写入或更新
- 必须记录完整输入输出:用户消息与 agent 回复均保留原文,不摘要、不省略
- 至少包含:会话时间、会话 ID、完整用户输入、完整 agent 输出;超长结果可折叠摘要,但不得删减对话原文
