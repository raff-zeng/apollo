# Apollo Cyber RT 术语

本页描述了 Cyber RT 中最常用术语的定义。

## Component（组件）

在自动驾驶系统中，模块（如感知、定位、控制系统等）以组件的形式存在于 Cyber RT 中。每个组件通过 Cyber channel 与其他组件通信。组件概念不仅解耦了模块，还提供了根据各个模块设计将模块划分为组件的灵活性。

## Channel（通道）

Channel 用于管理 Cyber RT 中的数据通信。用户可以发布/订阅同一个 channel 来实现点对点通信。

## Task（任务）

Task 是 Cyber RT 中异步计算任务的抽象描述。

## Node（节点）

Node 是 Cyber RT 的基本构建块；每个模块都包含 node 并通过 node 进行通信。模块可以通过在 node 中定义读/写和/或服务/客户端来实现不同类型的通信。

## Reader/Writer（读取器/写入器）

从/到 channel 读取/写入消息的类。Reader/Writer 通常在 node 内创建，是 Cyber RT 中的主要消息传输接口。

## Service/Client（服务/客户端）

除了 Reader/writer 之外，Cyber RT 还为模块通信提供服务/客户端模式。它支持节点之间的双向通信。当客户端节点向服务发出请求时，将收到响应。

## Parameter（参数）

参数服务在 Cyber RT 中提供全局参数访问接口。它基于服务/客户端模式构建。

## Service Discovery（服务发现）

作为一个去中心化的设计框架，Cyber RT 没有用于服务注册的主节点/中心节点。所有节点被平等对待，可以通过 `service discovery` 找到其他服务节点。服务发现中使用 `UDP`。

## CRoutine（协程）

称为协程概念，Cyber RT 实现了 CRoutine 以优化线程使用和系统资源分配。

## Scheduler（调度器）

为了更好地支持自动驾驶场景，Cyber RT 提供了多种资源调度算法供开发者选择。

## Message（消息）

Message 是 Cyber RT 中用于模块之间数据传输的数据单元。

## Dag 文件（Dag file）

Dag 文件是模块拓扑的配置文件。您可以在 dag 文件中定义使用的组件以及上游/下游通道。

## Launch 文件（Launch files）

Launch 文件提供了一种启动模块的简单方法。通过在 launch 文件中定义一个或多个 dag 文件，您可以同时启动多个模块。

## Record 文件（Record file）

Record 文件用于记录 Cyber RT 中从/到 channel 发送/接收的消息。回复 record 文件可以帮助重现 Cyber RT 之前的操作行为。
