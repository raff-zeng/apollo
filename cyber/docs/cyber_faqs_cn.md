# Apollo Cyber RT 常见问题

## 什么是 Apollo Cyber RT？

Apollo 的 Cyber RT 是专为自动驾驶场景设计的开源运行时框架。基于集中式计算模型，它在性能、延迟和数据吞吐量方面进行了高度优化。

---

## 为什么我们要开发一个新的运行时框架？

- 在多年的自动驾驶技术开发过程中，我们从之前使用 Apollo 的经验中学到了很多。在自动驾驶场景中，我们需要一个有效的集中式计算模型，对高性能的需求包括高并发、低延迟和高吞吐量。

- 行业在发展，Apollo 也在发展。展望未来，Apollo 已经从开发阶段进入产品化阶段，在现实世界中进行大规模部署，我们看到了对最高稳健性和高性能的需求。这就是我们花费数年时间构建 Apollo Cyber RT 的原因，它满足了自动驾驶解决方案的要求。

---

## 新运行时框架有哪些优势？

- 加速开发
  - 定义明确的任务接口和数据融合
  - 丰富的开发工具集
  - 大量的传感器驱动
- 简化部署
  - 高效且自适应的消息通信
  - 可配置的具有资源感知能力的用户级调度器
  - 依赖更少，可移植性强
- 赋能您自己的自动驾驶车辆
  - 默认的开源运行时框架
  - 专为自动驾驶设计的构建模块
  - 即插即用您自己的 AD 系统

---

## 我们仍然可以使用已收集的数据吗？

- 如果您收集的数据与 Apollo 之前的版本兼容，您可以使用我们推荐的转换工具使数据符合新的运行时框架要求
- 如果您创建了自定义数据格式，那么之前生成的数据将不被新的运行时框架支持

---

## 你们会继续支持 ROS 吗？

我们将继续支持基于 ROS 的 Apollo 之前版本（3.0 及之前）。我们非常感谢您继续与我们共同成长，并强烈鼓励您迁移到 Apollo 3.5。虽然我们知道一些开发者更喜欢在 ROS 上工作，但我们希望您理解为什么 Apollo 团队在我们努力开发一个满足汽车标准的更全面平台时，无法在未来版本中继续支持 ROS。

---

## Apollo Cyber RT 会影响常规代码开发吗？

如果您没有在运行时框架层进行任何修改，仅使用了 Apollo 的模块代码库，那么您不会受到新运行时框架引入的影响，因为大多数情况下您只需要重新接口输入输出数据的访问。

---

## Apollo Cyber RT 的推荐设置

- 运行时框架也使用 apollo 的 docker 环境
- 建议在打开新终端时运行 source setup.bash
- Fork 和克隆带有新框架代码的 Apollo 仓库，代码可以在 [apollo/cyber](../../cyber/) 找到

## 如何启用 SHM 以减少延迟？

为了减少线程数量，CyberRT 中更改了共享内存的可读通知机制。默认机制是 UDP 多播，系统调用（sendto）会导致一些延迟。

因此，为了减少延迟，您可以更改机制，步骤如下：

1. 将 CyberRT 更新到最新版本；
2. 取消注释 [cyber.pb.conf](../../cyber/conf/cyber.pb.conf) 中的 transport_conf；
3. 将 **shm_conf** 的 **notifier_type** 从 "multicast" 更改为 "condition"；
4. 使用 opt 选项构建 CyberRT，如 `bazel build -c opt --copt=-fpic //cyber/...`；
5. 运行 talker 和 listener；

注意：您可以根据节点之间的关系选择相应的传输方式。例如，默认配置是进程内 **INTRA**，主机进程之间 **SHM**，跨主机 **RTPS**。当然您可以将三者都改为 RTPS。或者将 `same_proc` 和 `diff_proc` 改为 **SHM**；

## 如何使用无序列化消息？

Cyber RT 支持的消息类型既包括可序列化的结构化数据（如 protobuf），也包括原始字节序列。您可以参考示例代码：

- apollo::cyber::message::RawMessage
- talker: https://github.com/gruminions/apollo/blob/record/cyber/examples/talker.cc
- listener: https://github.com/gruminions/apollo/blob/record/cyber/examples/listener.cc

## 如何配置多主机通信？

确保两个主机（或更多）处于局域网的同一网段下，如 `192.168.10.6` 和 `192.168.10.7`。

您只需要修改 `/apollo/cyber/setup.bash` 中的 `CYBER_IP`

```bash
export CYBER_IP=127.0.0.1
```

假设您有两个主机 A 和 B，A 的 IP 是 `192.168.10.6`，B 的 IP 是 `192.168.10.7`。然后在主机 A 上将 `CYBER_IP` 设置为 `192.168.10.6`，在主机 B 上将 `CYBER_IP` 设置为 `192.168.10.7`。现在主机 A 可以与主机 B 通信。

---

更多常见问题敬请期待...
