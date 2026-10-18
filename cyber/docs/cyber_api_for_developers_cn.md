# Apollo Cyber RT 开发者 API

本文档深入介绍了如何创建、操作和使用 Cyber RT API 的技术细节。

## 目录

- [Talker-Listener](#Talker-Listener)
- [Service 创建和使用](#Service-创建和使用)
- [Param 参数服务](#Param-参数服务)
- [Log API](#日志-API)
- [基于 Component 构建模块](#基于-Component-构建模块)
- [Launch](#Launch)
- [Timer](#Timer)
- [Time API](#Time-API)
- [Record 文件：读写](#Record-文件-读写)
- [C++ API 目录](##API-目录)
  - [Node](#node-api)
  - [Writer](#writer-api)
  - [Client](#client-api)
  - [Parameter](#parameter-api)
  - [Timer](#timer-api)
  - [Time](#time-api)
  - [Duration](#duration-api)
  - [Rate](#rate-api)
  - [RecordReader](#recordreader-api)
  - [RecordWriter](#recordwriter-api)

## Talker-Listener

演示 CyberRT API 的第一部分是理解 Talker/Listener 示例。以下是三个基本概念：node（基本单元）、reader（读取消息的工具）和 writer（写入消息的工具）。

### 创建一个 node

在 CyberRT 框架中，node 是最基本的单元，类似于 `handle` 的作用。当创建特定的功能对象（writer、reader 等）时，需要基于现有的 node 实例来创建。
node 创建接口如下：

```cpp
std::unique_ptr<Node> apollo::cyber::CreateNode(const std::string& node_name, const std::string& name_space = "");
```

- 参数：

  - node_name：node 的名称，全局唯一标识符
  - name_space：node 所在的空间名称

  > name_space 默认为空。它是与 node_name 拼接的空间名称。格式为 `/namespace/node_name`

- 返回值 - Node 的独占智能指针
- 错误条件 - 当未调用 `cyber::Init()` 时，系统处于未初始化状态，无法创建 node，返回 nullptr

### 创建一个 writer

writer 是 CyberRT 中用于发送消息的基本工具。每个 writer 对应一个具有特定数据类型的 channel。
writer 由 node 类的 `CreateWriter` 接口创建。接口列表如下：

```cpp
template <typename MessageT>
   auto CreateWriter(const std::string& channel_name)
       -> std::shared_ptr<Writer<MessageT>>;
template <typename MessageT>
   auto CreateWriter(const proto::RoleAttributes& role_attr)
       -> std::shared_ptr<Writer<MessageT>>;

```

- 参数：
  - channel_name：要写入的 channel 名称
  - MessageT：要写出的消息类型
- 返回值 - Writer 对象的共享指针

### 创建一个 reader

reader 是 cyber 中用于接收消息的基本工具。reader 在创建时必须绑定一个回调函数。当 channel 中有新消息到达时，将调用回调。
reader 由 node 类的 `CreateReader` 接口创建。接口列表如下：

```cpp
template <typename MessageT>
auto CreateReader(const std::string& channel_name, const std::function<void(const std::shared_ptr<MessageT>&)>& reader_func)
    -> std::shared_ptr<Reader<MessageT>>;

template <typename MessageT>
auto CreateReader(const ReaderConfig& config,
                  const CallbackFunc<MessageT>& reader_func = nullptr)
    -> std::shared_ptr<cyber::Reader<MessageT>>;

template <typename MessageT>
auto CreateReader(const proto::RoleAttributes& role_attr,
                  const CallbackFunc<MessageT>& reader_func = nullptr)
-> std::shared_ptr<cyber::Reader<MessageT>>;
```

- 参数：

  - MessageT：要读取的消息类型
  - channel_name：要接收的 channel 名称
  - reader_func：处理消息的回调函数

- 返回值 - Reader 对象的共享指针

### 代码示例

#### Talker (cyber/examples/talker.cc)

```cpp
#include "cyber/cyber.h"
#include "cyber/proto/chatter.pb.h"
#include "cyber/time/rate.h"
#include "cyber/time/time.h"
using apollo::cyber::Rate;
using apollo::cyber::Time;
using apollo::cyber::proto::Chatter;
int main(int argc, char *argv[]) {
  // 初始化 cyber 框架
  apollo::cyber::Init(argv[0]);
  // 创建 talker node
  std::shared_ptr<apollo::cyber::Node> talker_node(
      apollo::cyber::CreateNode("talker"));
  // 创建 talker
  auto talker = talker_node->CreateWriter<Chatter>("channel/chatter");
  Rate rate(1.0);
  while (apollo::cyber::OK()) {
    static uint64_t seq = 0;
    auto msg = std::make_shared<apollo::cyber::proto::Chatter>();
    msg->set_timestamp(Time::Now().ToNanosecond());
    msg->set_lidar_timestamp(Time::Now().ToNanosecond());
    msg->set_seq(seq++);
    msg->set_content("Hello, apollo!");
    talker->Write(msg);
    AINFO << "talker sent a message!";
    rate.Sleep();
  }
  return 0;
}
```

#### Listener (cyber/examples/listener.cc)

```cpp
#include "cyber/cyber.h"
#include "cyber/proto/chatter.pb.h"
void MessageCallback(
    const std::shared_ptr<apollo::cyber::proto::Chatter>& msg) {
  AINFO << "Received message seq-> " << msg->seq();
  AINFO << "msgcontent->" << msg->content();
}
int main(int argc, char *argv[]) {
  // 初始化 cyber 框架
  apollo::cyber::Init(argv[0]);
  // 创建 listener node
  auto listener_node = apollo::cyber::CreateNode("listener");
  // 创建 listener
  auto listener =
      listener_node->CreateReader<apollo::cyber::proto::Chatter>(
          "channel/chatter", MessageCallback);
  apollo::cyber::WaitForShutdown();
  return 0;
}
```

#### Bazel BUILD 文件(cyber/samples/BUILD)

```python
cc_binary(
    name = "talker",
    srcs = [ "talker.cc", ],
    deps = [
        "//cyber",
        "//cyber/examples/proto:examples_cc_proto",
    ],
)

cc_binary(
    name = "listener",
    srcs = [ "listener.cc", ],
    deps = [
        "//cyber",
        "//cyber/examples/proto:examples_cc_proto",
    ],
)
```

#### 编译和运行

- 编译：bazel build cyber/examples/…
- 在不同的终端中运行 talker/listener：
  - ./bazel-bin/cyber/examples/talker
  - ./bazel-bin/cyber/examples/listener
- 检查结果：你应该能在 listener 上看到消息打印。

## Service 创建和使用

### 简介

在自动驾驶系统中，有许多场景要求模块通信不仅仅是发送或接收消息。Service 是节点之间另一种通信方式。与 channel 不同，service 实现`双向`通信，例如节点通过发送请求获得响应。本节通过示例介绍 CyberRT API 中的 `service` 模块。

### Demo - 示例

问题：创建一个客户端-服务器模型，来回传递 Driver.proto。
当客户端发送请求时，服务器解析/处理请求并返回响应。

该 demo 的实现主要包括以下步骤。

#### 定义请求和响应消息

cyber 中的所有消息都是 `protobuf` 格式。任何具有序列化/反序列化接口的 protobuf 消息都可以用作服务请求和响应消息。本示例中使用 examples.proto 中的 `Driver` 作为服务请求和响应：

```protobuf
// 文件名: examples.proto
syntax = "proto2";
package apollo.cyber.examples.proto;
message Driver {
    optional string content = 1;
    optional uint64 msg_id = 2;
    optional uint64 timestamp = 3;
};
```

#### 创建 service 和 client

```cpp
// 文件名: cyber/examples/service.cc
#include "cyber/cyber.h"
#include "cyber/examples/proto/examples.pb.h"

using apollo::cyber::examples::proto::Driver;

int main(int argc, char* argv[]) {
  apollo::cyber::Init(argv[0]);
  std::shared_ptr<apollo::cyber::Node> node(
      apollo::cyber::CreateNode("start_node"));
  auto server = node->CreateService<Driver, Driver>(
      "test_server", [](const std::shared_ptr<Driver>& request,
                        std::shared_ptr<Driver>& response) {
        AINFO << "server: I am driver server";
        static uint64_t id = 0;
        ++id;
        response->set_msg_id(id);
        response->set_timestamp(0);
      });
  auto client = node->CreateClient<Driver, Driver>("test_server");
  auto driver_msg = std::make_shared<Driver>();
  driver_msg->set_msg_id(0);
  driver_msg->set_timestamp(0);
  while (apollo::cyber::OK()) {
    auto res = client->SendRequest(driver_msg);
    if (res != nullptr) {
      AINFO << "client: response: " << res->ShortDebugString();
    } else {
      AINFO << "client: service may not ready.";
    }
    sleep(1);
  }

  apollo::cyber::WaitForShutdown();
  return 0;
}
```

#### Bazel 构建文件

```python
cc_binary(
    name = "service",
    srcs = [ "service.cc", ],
    deps = [
        "//cyber",
        "//cyber/examples/proto:examples_cc_proto",
    ],
)
```

#### 编译和运行

- 编译 service/client：bazel build cyber/examples/…
- 运行：./bazel-bin/cyber/examples/service
- 检查结果：你应该在 apollo/data/log/service.INFO 中看到以下内容

```txt
I1124 16:36:44.568845 14965 service.cc:30] [service] server: i am driver server
I1124 16:36:44.569031 14949 service.cc:43] [service] client: response: msg_id: 1 timestamp: 0
I1124 16:36:45.569514 14966 service.cc:30] [service] server: i am driver server
I1124 16:36:45.569932 14949 service.cc:43] [service] client: response: msg_id: 2 timestamp: 0
I1124 16:36:46.570627 14967 service.cc:30] [service] server: i am driver server
I1124 16:36:46.571024 14949 service.cc:43] [service] client: response: msg_id: 3 timestamp: 0
I1124 16:36:47.571566 14968 service.cc:30] [service] server: i am driver server
I1124 16:36:47.571962 14949 service.cc:43] [service] client: response: msg_id: 4 timestamp: 0
I1124 16:36:48.572634 14969 service.cc:30] [service] server: i am driver server
I1124 16:36:48.573030 14949 service.cc:43] [service] client: response: msg_id: 5 timestamp: 0
```

### 注意事项

- 注册服务时，注意不允许重复的服务名称
- 注册服务器和客户端时应用的 node 名称也不应重复

## 参数服务

参数服务用于节点之间的共享数据，并提供 `set`、`get` 和 `list` 等基本操作。参数服务基于 `Service` 实现，包含 service 和 client。

### Parameter 对象

#### 支持的数据类型

所有通过 cyber 传递的参数都是 `apollo::cyber::Parameter` 对象，下表列出了 5 种支持的参数类型。

| 参数类型                                 | C++ 数据类型 | protobuf 数据类型 |
| :--------------------------------------- | :----------- | :---------------- |
| apollo::cyber::proto::ParamType::INT     | int64_t      | int64             |
| apollo::cyber::proto::ParamType::DOUBLE  | double       | double            |
| apollo::cyber::proto::ParamType::BOOL    | bool         | bool              |
| apollo::cyber::proto::ParamType::STRING  | std::string  | string            |
| apollo::cyber::proto::ParamType::PROTOBUF| std::string  | string            |
| apollo::cyber::proto::ParamType::NOT_SET | -            | -                 |

除了上述 5 种类型外，Parameter 还支持以 protobuf 对象为传入参数的接口。经过序列化处理后，将对象转换为 STRING 类型进行传输。

#### 创建 Parameter 对象

支持的构造函数：

```cpp
Parameter();  // 名称为空，类型为 NOT_SET
explicit Parameter(const Parameter& parameter);
explicit Parameter(const std::string& name);  // 类型为 NOT_SET
Parameter(const std::string& name, const bool bool_value);
Parameter(const std::string& name, const int int_value);
Parameter(const std::string& name, const int64_t int_value);
Parameter(const std::string& name, const float double_value);
Parameter(const std::string& name, const double double_value);
Parameter(const std::string& name, const std::string& string_value);
Parameter(const std::string& name, const char* string_value);
Parameter(const std::string& name, const std::string& msg_str,
          const std::string& full_name, const std::string& proto_desc);
Parameter(const std::string& name, const google::protobuf::Message& msg);
```

使用 Parameter 对象的示例代码：

```cpp
Parameter a("int", 10);
Parameter b("bool", true);
Parameter c("double", 0.1);
Parameter d("string", "cyber");
Parameter e("string", std::string("cyber"));
// proto message Chatter
Chatter chatter;
Parameter f("chatter", chatter);
std::string msg_str("");
chatter.SerializeToString(&msg_str);
std::string msg_desc("");
ProtobufFactory::GetDescriptorString(chatter, &msg_desc);
Parameter g("chatter", msg_str, Chatter::descriptor()->full_name(), msg_desc);
```

#### 接口和数据读取

接口列表：

```cpp
inline ParamType type() const;
inline std::string TypeName() const;
inline std::string Descriptor() const;
inline const std::string Name() const;
inline bool AsBool() const;
inline int64_t AsInt64() const;
inline double AsDouble() const;
inline const std::string AsString() const;
std::string DebugString() const;
template <typename Type>
typename std::enable_if<std::is_base_of<google::protobuf::Message, Type>::value, Type>::type
value() const;
template <typename Type>
typename std::enable_if<std::is_integral<Type>::value && !std::is_same<Type, bool>::value, Type>::type
value() const;
template <typename Type>
typename std::enable_if<std::is_floating_point<Type>::value, Type>::type
value() const;
template <typename Type>
typename std::enable_if<std::is_convertible<Type, std::string>::value, const std::string&>::type
value() const;
template <typename Type>
typename std::enable_if<std::is_same<Type, bool>::value, bool>::type
value() const;
```

使用这些接口的示例：

```cpp
Parameter a("int", 10);
a.Name();  // 返回 int
a.Type();  // 返回 apollo::cyber::proto::ParamType::INT
a.TypeName();  // 返回字符串: INT
a.DebugString();  // 返回字符串: {name: "int", type: "INT", value: 10}
int x = a.AsInt64();  // x = 10
x = a.value<int64_t>();  // x = 10
x = a.AsString();  // 未定义行为，错误日志提示
f.TypeName();  // 返回字符串: chatter
auto chatter = f.value<Chatter>();
```

### 参数服务

如果一个节点想为其他节点提供参数服务，则需要创建一个 `ParameterService`。

```cpp
/**
 * @brief 构造一个新的 ParameterService 对象
 *
 * @param node 节点处理器的 shared_ptr
 */
explicit ParameterService(const std::shared_ptr<Node>& node);
```

由于所有参数都存储在参数服务对象中，因此可以直接在 ParameterService 中操作参数，而无需发送服务请求。

**设置参数：**

```cpp
/**
 * @brief 设置 Parameter 对象
 *
 * @param parameter 要设置的参数
 */
void SetParameter(const Parameter& parameter);
```

**获取参数：**

```cpp
/**
 * @brief 获取 Parameter 对象
 *
 * @param param_name
 * @param parameter 存储的指针
 * @return true
 * @return false 调用服务失败或超时
 */
bool GetParameter(const std::string& param_name, Parameter* parameter);
```

**获取参数列表：**

```cpp
/**
 * @brief 获取所有 Parameter 对象
 *
 * @param parameters 存储所有参数的 vector 指针
 * @return true
 * @return false 调用服务失败或超时
 */
bool ListParameters(std::vector<Parameter>* parameters);
```

### 参数客户端

如果一个节点想使用其他节点的参数服务，需要创建一个 `ParameterClient`。

```cpp
/**
 * @brief 构造一个新的 ParameterClient 对象
 *
 * @param node 节点处理器的 shared_ptr
 * @param service_node_name 提供参数服务的节点名称
 */
ParameterClient(const std::shared_ptr<Node>& node, const std::string& service_node_name);
```

您还可以执行 [参数服务](#参数服务) 中提到的 `SetParameter`、`GetParameter` 和 `ListParameters`。

### Demo - 示例

```cpp
#include "cyber/cyber.h"
#include "cyber/parameter/parameter_client.h"
#include "cyber/parameter/parameter_server.h"

using apollo::cyber::Parameter;
using apollo::cyber::ParameterServer;
using apollo::cyber::ParameterClient;

int main(int argc, char** argv) {
  apollo::cyber::Init(*argv);
  std::shared_ptr<apollo::cyber::Node> node =
      apollo::cyber::CreateNode("parameter");
  auto param_server = std::make_shared<ParameterServer>(node);
  auto param_client = std::make_shared<ParameterClient>(node, "parameter");
  param_server->SetParameter(Parameter("int", 1));
  Parameter parameter;
  param_server->GetParameter("int", &parameter);
  AINFO << "int: " << parameter.AsInt64();
  param_client->SetParameter(Parameter("string", "test"));
  param_client->GetParameter("string", &parameter);
  AINFO << "string: " << parameter.AsString();
  param_client->GetParameter("int", &parameter);
  AINFO << "int: " << parameter.AsInt64();
  return 0;
}
```

#### 编译和运行

- 编译：bazel build cyber/examples/…
- 运行：./bazel-bin/cyber/examples/paramserver

## 日志 API

### 日志库

Cyber 日志库构建在 glog 之上。需要包含以下头文件：

```cpp
#include "cyber/common/log.h"
#include "cyber/init.h"
```

### 日志配置

默认全局配置路径：cyber/setup.bash

开发者可以修改以下配置：

```
export GLOG_log_dir=/apollo/data/log
export GLOG_alsologtostderr=0
export GLOG_colorlogtostderr=1
export GLOG_minloglevel=0
```

### 日志初始化

在代码入口调用 Init 方法来初始化日志：

```cpp++
apollo::cyber::cyber::Init(argv[0]) 已初始化。
如果在前面的组件中没有进行宏定义，则相应的日志将打印到二进制日志中。
```

### 日志输出宏

日志库封装在日志打印宏中。相关的日志宏使用如下：

```cpp
ADEBUG << "hello cyber.";
AINFO  << "hello cyber.";
AWARN  << "hello cyber.";
AERROR << "hello cyber.";
AFATAL << "hello cyber.";

```

### 日志格式

格式为 `<MODULE_NAME>.log.<LOG_LEVEL>.<datetime>.<process_id>`

### 关于日志文件

目前，与默认 glog 不同的唯一输出行为是，模块的不同日志级别将写入同一个日志文件。

## 基于 Component 构建模块

### 核心概念

#### 1. Component

Component 是 Cyber RT 提供的用于构建应用模块的基类。每个特定的应用模块可以继承 Component 类并定义自己的 `Init` 和 `Proc` 函数，以便加载到 Cyber 框架中。

#### 2. Binary vs Component

使用 Cyber RT 框架的应用程序有两种选择：

- 基于 Binary：应用程序单独编译成二进制文件，通过创建自己的 `Reader` 和 `Writer` 与其他 cyber 模块通信。
- 基于 Component：应用程序编译成共享库。通过继承 Component 类并编写相应的 dag 描述文件，Cyber RT 框架将动态加载和运行应用程序。

##### Component 的基本接口

- Component 的 `Init()` 函数类似于 main 函数，对算法进行一些初始化。
- Component 的 `Proc()` 函数类似于 Reader 的回调函数，当消息到达时由框架调用。

##### 使用 Component 的优势

- Component 可以通过 launch 文件加载到不同的进程中，部署灵活。
- Component 可以通过修改 dag 文件来更改接收的 channel 名称，而无需重新编译。
- Component 支持接收多种类型的数据。
- Component 支持提供多种融合策略。

#### 3. Dag 文件格式

一个示例 dag 文件：

```protobuf
# 定义 DAG 流中的所有组件。
module_config {
    module_library : "lib/libperception_component.so"
    components {
        class_name : "PerceptionComponent"
        config {
            name : "perception"
            readers {
                channel: "perception/channel_name"
            }
        }
    }
    timer_components {
        class_name : "DriverComponent"
        config {
            name : "driver"
            interval : 100
        }
    }
}
```

- **module_library**：如果要加载 .so 库，根目录是 cyber 的工作目录（`setup.bash` 的同一目录）
- **components & timer_component**：选择需要加载的基组件类类型
- **class_name**：要加载的组件类的名称
- **name**：加载的 class_name 作为加载示例的标识符
- **readers**：当前组件接收的数据，支持 1-3 个 channel 的数据。

### Demo - 示例

#### Common_component_example(cyber/examples/common_component_example/*)

头文件定义(common_component_example.h)

```cpp
#include <memory>

#include "cyber/class_loader/class_loader.h"
#include "cyber/component/component.h"
#include "cyber/examples/proto/examples.pb.h"

using apollo::cyber::examples::proto::Driver;
using apollo::cyber::Component;
using apollo::cyber::ComponentBase;

class Commontestcomponent : public Component<Driver, Driver> {
 public:
  bool Init() override;
  bool Proc(const std::shared_ptr<Driver>& msg0,
            const std::shared_ptr<Driver>& msg1) override;
};
CYBER_REGISTER_COMPONENT(Commontestcomponent)
```

Cpp 文件实现(common_component_example.cc)

```cpp
#include "cyber/examples/common_component_smaple/common_component_example.h"

#include "cyber/class_loader/class_loader.h"
#include "cyber/component/component.h"

bool Commontestcomponent::Init() {
  AINFO << "Commontest component init";
  return true;
}

bool Commontestcomponent::Proc(const std::shared_ptr<Driver>& msg0,
                               const std::shared_ptr<Driver>& msg1) {
  AINFO << "Start commontest component Proc [" << msg0->msg_id() << "] ["
        << msg1->msg_id() << "]";
  return true;
}
```

#### Timer_component_example(cyber/examples/timer_component_example/*)

头文件定义(timer_component_example.h)

```cpp
#include <memory>

#include "cyber/class_loader/class_loader.h"
#include "cyber/component/component.h"
#include "cyber/component/timer_component.h"
#include "cyber/examples/proto/examples.pb.h"

using apollo::cyber::examples::proto::Driver;
using apollo::cyber::Component;
using apollo::cyber::ComponentBase;
using apollo::cyber::TimerComponent;
using apollo::cyber::Writer;

class TimertestComponent : public TimerComponent {
 public:
  bool Init() override;
  bool Proc() override;

 private:
  std::shared_ptr<Writer<Driver>> driver_writer_ = nullptr;
};
CYBER_REGISTER_COMPONENT(TimertestComponent)
```

Cpp 文件实现(timer_component_example.cc)

```cpp
#include "cyber/examples/timer_component_example/timer_component_example.h"

#include "cyber/class_loader/class_loader.h"
#include "cyber/component/component.h"
#include "cyber/examples/proto/examples.pb.h"

bool TimertestComponent::Init() {
  driver_writer_ = node_->CreateWriter<Driver>("/carstatus/channel");
  return true;
}

bool TimertestComponent::Proc() {
  static int i = 0;
  auto out_msg = std::make_shared<Driver>();
  out_msg->set_msg_id(i++);
  driver_writer_->Write(out_msg);
  AINFO << "timertestcomponent: Write drivermsg->"
        << out_msg->ShortDebugString();
  return true;
}
```

#### 编译和运行

以 timertestcomponent 为例：

- 编译：bazel build cyber/examples/timer_component_smaple/…
- 运行：mainboard -d cyber/examples/timer_component_smaple/timer.dag

### 注意事项

- Component 需要注册才能通过 SharedLibrary 加载类。注册接口如下：

```cpp
CYBER_REGISTER_COMPONENT(DriverComponent)
```

如果注册时使用了命名空间，则在 dag 文件中定义时也需要添加命名空间。

- Component 和 TimerComponent 的配置文件不同，请注意不要将两者混淆。

## Launch

**cyber_launch** 是 Cyber RT 框架的启动器。它根据 launch 文件启动多个 mainboard，并根据 dag 文件将不同的组件加载到不同的 mainboard 中。
cyber_launch 支持两种场景：在子进程中动态加载组件或启动 Binary 程序。

### Launch 文件格式

```xml
<cyber>
    <module>
        <name>driver</name>
        <dag_conf>driver.dag</dag_conf>
        <process_name></process_name>
        <exception_handler>exit</exception_handler>
    </module>
    <module>
        <name>perception</name>
        <dag_conf>perception.dag</dag_conf>
        <process_name></process_name>
        <exception_handler>respawn</exception_handler>
    </module>
    <module>
        <name>planning</name>
        <dag_conf>planning.dag</dag_conf>
        <process_name></process_name>
    </module>
</cyber>
```

**Module**:
每个加载的组件或 binary 都是一个 module

- **name** 是加载的模块名称
- **dag_conf** 是组件对应的 dag 文件名称
- **process_name** 是 mainboard 进程启动后的名称，process_name 相同的组件将在同一进程中加载和运行。
- **exception_handler** 是进程中发生异常时的处理方法。值可以是以下列出的 exit 或 respawn。
  - exit，表示当前进程异常退出时需要停止整个进程运行。
  - respawn，当前进程异常退出后需要重新启动。如果不存在，则表示不处理。用户可以根据进程的具体情况进行控制

## Timer

Timer 可以用于创建定时任务以定期运行，或仅运行一次

### Timer 接口

```cpp
/**
 * @brief 构造一个新的 Timer 对象
 *
 * @param period 定时器的周期，单位是 ms
 * @param callback 定时器需要执行的任务
 * @param oneshot True: 仅在第一个定时周期后执行回调
 *                False: 每个定时周期执行回调
 */
Timer(uint32_t period, std::function<void()> callback, bool oneshot);
```

或者您可以将参数封装成定时器选项，如下所示：

```cpp
struct TimerOption {
  uint32_t period;                 // 定时器的周期，单位是 ms
  std::function<void()> callback;  // 定时器需要执行的任务
  bool oneshot;  // True: 仅在第一个定时周期后执行回调
                 // False: 每个定时周期执行回调
};
/**
 * @brief 构造一个新的 Timer 对象
 *
 * @param opt 定时器选项
 */
explicit Timer(TimerOption opt);
```

### 启动 Timer

创建 Timer 实例后，必须调用 `Timer::Start()` 来启动定时器。

### 停止 Timer

当需要手动停止已启动的定时器时，可以调用 `Timer::Stop()` 接口。

### Demo - 示例

```cpp
#include <iostream>
#include "cyber/cyber.h"
int main(int argc, char** argv) {
    cyber::Init(argv[0]);
    // 每 100ms 打印当前时间
    cyber::Timer timer(100, [](){
        std::cout << cyber::Time::Now() << std::endl;
    }, false);
    timer.Start();
    sleep(1);
    timer.Stop();
}
```

## Time API

Time 是用于管理时间的类；可以用于当前时间获取、耗时计算、时间转换等。

时间接口如下：

```cpp
// 构造函数，传入不同的值来构造 Time
Time(uint64_t nanoseconds); // uint64_t，以纳秒为单位
Time(int nanoseconds); // int 类型，单位：纳秒
Time(double seconds); // double，以秒为单位
Time(uint32_t seconds, uint32_t nanoseconds);
// 秒 秒 + 纳秒 纳秒
static Time Now(); // 获取当前时间
double ToSecond() const; // 转换为秒
uint64_t ToNanosecond() const; // 转换为纳秒
std::string ToString() const; // 转换为格式为 "2018-07-10 20:21:51.123456789" 的字符串
bool IsZero() const; // 判断时间是否为 0

```

代码示例如下：

```cpp
#include <iostream>
#include "cyber/cyber.h"
#include "cyber/duration.h"
int main(int argc, char** argv) {
    cyber::Init(argv[0]);
    Time t1(1531225311123456789UL);
    std::cout << t1.ToString() << std::endl; // 2018-07-10 20:21:51.123456789
    // Duration 时间间隔
    Time t1(100);
    Duration d(200);
    Time t2(300);
    assert(d == (t1-t2)); // true
}

```

## Record 文件：读写

### 读取 Reader 文件

**RecordReader** 是 cyber 框架中用于读取消息的组件。每个 RecordReader 可以通过 `Open` 方法打开一个现有的 record 文件，线程将异步读取 record 文件中的信息。用户只需要执行 ReadMessage 来提取 RecordReader 中的最新消息，然后通过 GetCurrentMessageChannelName、GetCurrentRawMessage、GetCurrentMessageTime 获取消息信息。

**RecordWriter** 是 cyber 框架中用于记录消息的组件。每个 RecordWriter 可以通过 Open 方法创建一个新的 record 文件。用户只需要执行 WriteMessage 和 WriteChannel 来写入消息和 channel 信息，写入过程是异步的。

### Demo - 示例(cyber/examples/record.cc)

通过 `test_write` 方法将 100 个 RawMessage 写入`TEST_FILE`，然后通过 `test_read` 方法读取它们。

```cpp
#include <string>

#include "cyber/cyber.h"
#include "cyber/message/raw_message.h"
#include "cyber/proto/record.pb.h"
#include "cyber/record/record_message.h"
#include "cyber/record/record_reader.h"
#include "cyber/record/record_writer.h"

using ::apollo::cyber::record::RecordReader;
using ::apollo::cyber::record::RecordWriter;
using ::apollo::cyber::record::RecordMessage;
using apollo::cyber::message::RawMessage;

const char CHANNEL_NAME_1[] = "/test/channel1";
const char CHANNEL_NAME_2[] = "/test/channel2";
const char MESSAGE_TYPE_1[] = "apollo.cyber.proto.Test";
const char MESSAGE_TYPE_2[] = "apollo.cyber.proto.Channel";
const char PROTO_DESC[] = "1234567890";
const char STR_10B[] = "1234567890";
const char TEST_FILE[] = "test.record";

void test_write(const std::string &writefile) {
  RecordWriter writer;
  writer.SetSizeOfFileSegmentation(0);
  writer.SetIntervalOfFileSegmentation(0);
  writer.Open(writefile);
  writer.WriteChannel(CHANNEL_NAME_1, MESSAGE_TYPE_1, PROTO_DESC);
  for (uint32_t i = 0; i < 100; ++i) {
    auto msg = std::make_shared<RawMessage>("abc" + std::to_string(i));
    writer.WriteMessage(CHANNEL_NAME_1, msg, 888 + i);
  }
  writer.Close();
}

void test_read(const std::string &readfile) {
  RecordReader reader(readfile);
  RecordMessage message;
  uint64_t msg_count = reader.GetMessageNumber(CHANNEL_NAME_1);
  AINFO << "MSGTYPE: " << reader.GetMessageType(CHANNEL_NAME_1);
  AINFO << "MSGDESC: " << reader.GetProtoDesc(CHANNEL_NAME_1);

  // 读取所有消息
  uint64_t i = 0;
  uint64_t valid = 0;
  for (i = 0; i < msg_count; ++i) {
    if (reader.ReadMessage(&message)) {
      AINFO << "msg[" << i << "]-> "
            << "channel name: " << message.channel_name
            << "; content: " << message.content
            << "; msg time: " << message.time;
      valid++;
    } else {
      AERROR << "read msg[" << i << "] failed";
    }
  }
  AINFO << "static msg=================";
  AINFO << "MSG validmsg:totalcount: " << valid << ":" << msg_count;
}

int main(int argc, char *argv[]) {
  apollo::cyber::Init(argv[0]);
  test_write(TEST_FILE);
  sleep(1);
  test_read(TEST_FILE);
  return 0;
}
```

#### 编译和运行

- 编译：bazel build cyber/examples/…
- 运行：./bazel-bin/cyber/examples/record
- 检查结果：

```
I1124 16:56:27.248200 15118 record.cc:64] [record] msg[0]-> channel name: /test/channel1; content: abc0; msg time: 888
I1124 16:56:27.248227 15118 record.cc:64] [record] msg[1]-> channel name: /test/channel1; content: abc1; msg time: 889
I1124 16:56:27.248239 15118 record.cc:64] [record] msg[2]-> channel name: /test/channel1; content: abc2; msg time: 890
I1124 16:56:27.248252 15118 record.cc:64] [record] msg[3]-> channel name: /test/channel1; content: abc3; msg time: 891
I1124 16:56:27.248297 15118 record.cc:64] [record] msg[4]-> channel name: /test/channel1; content: abc4; msg time: 892
I1124 16:56:27.248378 15118 record.cc:64] [record] msg[5]-> channel name: /test/channel1; content: abc5; msg time: 893
...
I1124 16:56:27.250422 15118 record.cc:73] [record] static msg=================
I1124 16:56:27.250434 15118 record.cc:74] [record] MSG validmsg:totalcount: 100:100
```

## API 目录

### Node API

有关其他信息和示例，请参阅 [Node](#node)

### API 列表

```cpp
// 使用用户定义的属性和消息类型创建 writer
auto CreateWriter(const proto::RoleAttributes& role_attr)
    -> std::shared_ptr<transport::Writer<MessageT>>;
// 使用用户定义的属性、回调和消息类型创建 reader
auto CreateReader(const proto::RoleAttributes& role_attr,
    const croutine::CRoutineFunc<MessageT>& reader_func)
    -> std::shared_ptr<transport::Reader<MessageT>>;
// 使用特定的 channel 名称和消息类型创建 writer
auto CreateWriter(const std::string& channel_name)
    -> std::shared_ptr<transport::Writer<MessageT>>;
// 使用特定的 channel 名称、回调和消息类型创建 reader
auto CreateReader(const std::string& channel_name,
    const croutine::CRoutineFunc<MessageT>& reader_func)
    -> std::shared_ptr<transport::Reader<MessageT>>;
// 使用用户定义的配置、回调和消息类型创建 reader
auto CreateReader(const ReaderConfig& config,
                  const CallbackFunc<MessageT>& reader_func)
    -> std::shared_ptr<cybertron::Reader<MessageT>>;
// 使用名称和特定回调创建 service
auto CreateService(const std::string& service_name,
    const typename service::Service<Request, Response>::ServiceCallback& service_calllback)
    -> std::shared_ptr<service::Service<Request, Response>>;
// 使用名称创建 client 以向服务器发送请求
auto CreateClient(const std::string& service_name)
    -> std::shared_ptr<service::Client<Request, Response>>;

```

## Writer API

有关其他信息和示例，请参阅 [Writer](#writer)

### API 列表

```cpp
bool Write(const std::shared_ptr<MessageT>& message);
```

## Client API

有关其他信息和示例，请参阅 [Client](#service-创建和使用)

### API 列表

```cpp
SharedResponse SendRequest(SharedRequest request,
                           const std::chrono::seconds& timeout_s = std::chrono::seconds(5));
SharedResponse SendRequest(const Request& request,
                           const std::chrono::seconds& timeout_s = std::chrono::seconds(5));
```

## Parameter API

用户用于执行参数相关操作的接口：

- 设置参数相关的 API。
- 读取参数相关的 API。
- 创建 ParameterService 以为其他节点提供参数服务相关的 API。
- 创建 ParameterClient 以使用其他节点提供的参数来服务相关的 API。

有关其他信息和示例，请参阅 [Parameter](##参数服务)

### API 列表 - 设置参数

```cpp
Parameter();  // 名称为空，类型为 NOT_SET
explicit Parameter(const Parameter& parameter);
explicit Parameter(const std::string& name);  // 类型为 NOT_SET
Parameter(const std::string& name, const bool bool_value);
Parameter(const std::string& name, const int int_value);
Parameter(const std::string& name, const int64_t int_value);
Parameter(const std::string& name, const float double_value);
Parameter(const std::string& name, const double double_value);
Parameter(const std::string& name, const std::string& string_value);
Parameter(const std::string& name, const char* string_value);
Parameter(const std::string& name, const std::string& msg_str,
          const std::string& full_name, const std::string& proto_desc);
Parameter(const std::string& name, const google::protobuf::Message& msg);
```

### API 列表 - 读取参数

```cpp
inline ParamType type() const;
inline std::string TypeName() const;
inline std::string Descriptor() const;
inline const std::string Name() const;
inline bool AsBool() const;
inline int64_t AsInt64() const;
inline double AsDouble() const;
inline const std::string AsString() const;
std::string DebugString() const;
template <typename Type>
typename std::enable_if<std::is_base_of<google::protobuf::Message, Type>::value, Type>::type
value() const;
template <typename Type>
typename std::enable_if<std::is_integral<Type>::value && !std::is_same<Type, bool>::value, Type>::type
value() const;
template <typename Type>
typename std::enable_if<std::is_floating_point<Type>::value, Type>::type
value() const;
template <typename Type>
typename std::enable_if<std::is_convertible<Type, std::string>::value, const std::string&>::type
value() const;
template <typename Type>
typename std::enable_if<std::is_same<Type, bool>::value, bool>::type
value() const;
```

### API 列表 - 创建参数服务

```cpp
explicit ParameterService(const std::shared_ptr<Node>& node);
void SetParameter(const Parameter& parameter);
bool GetParameter(const std::string& param_name, Parameter* parameter);
bool ListParameters(std::vector<Parameter>* parameters);
```

### API 列表 - 创建参数客户端

```cpp
ParameterClient(const std::shared_ptr<Node>& node, const std::string& service_node_name);
bool SetParameter(const Parameter& parameter);
bool GetParameter(const std::string& param_name, Parameter* parameter);
bool ListParameters(std::vector<Parameter>* parameters);
```

## Timer API

您可以设置 Timer 的参数并调用 start 和 stop 接口来启动和停止定时器。
有关其他信息和示例，请参阅 [Timer](#Timer)

### API 列表

```cpp
Timer(uint32_t period, std::function<void()> callback, bool oneshot);
Timer(TimerOption opt);
void SetTimerOption(TimerOption opt);
void Start();
void Stop();
```

## Time API

有关其他信息和示例，请参阅 [Time](#Time-API)

### API 列表

```cpp
static const Time MAX;
static const Time MIN;
Time() {}
explicit Time(uint64_t nanoseconds);
explicit Time(int nanoseconds);
explicit Time(double seconds);
Time(uint32_t seconds, uint32_t nanoseconds);
Time(const Time& other);
static Time Now();
static Time MonoTime();
static void SleepUntil(const Time& time);
double ToSecond() const;
uint64_t ToNanosecond() const;
std::string ToString() const;
bool IsZero() const;
```

## Duration API

间隔相关的接口，用于表示时间间隔，可以根据指定的纳秒或秒进行初始化。

### API 列表

```cpp
Duration() {}
Duration(int64_t nanoseconds);
Duration(int nanoseconds);
Duration(double seconds);
Duration(uint32_t seconds, uint32_t nanoseconds);
Duration(const Rate& rate);
Duration(const Duration& other);
double ToSecond() const;
int64_t ToNanosecond() const;
bool IsZero() const;
void Sleep() const;
```

## Rate API

频率接口通常用于在根据指定频率初始化对象后初始化睡眠频率的时间。

### API 列表

```cpp
Rate(double frequency);
Rate(uint64_t nanoseconds);
Rate(const Duration&);
void Sleep();
void Reset();
Duration CycleTime() const;
Duration ExpectedCycleTime() const { return expected_cycle_time_; }
```

## RecordReader API

用于读取 record 文件的接口，用于读取 record 文件中的消息和 channel 信息。

### API 列表

```cpp
RecordReader();
bool Open(const std::string& filename, uint64_t begin_time = 0,
          uint64_t end_time = UINT64_MAX);
void Close();
bool ReadMessage();
bool EndOfFile();
const std::string& CurrentMessageChannelName();
std::shared_ptr<RawMessage> CurrentRawMessage();
uint64_t CurrentMessageTime();
```

## RecordWriter API

用于写入 record 文件的接口，用于将消息和 channel 信息记录到 record 文件中。

### API 列表

```cpp
RecordWriter();
bool Open(const std::string& file);
void Close();
bool WriteChannel(const std::string& name, const std::string& type,
                  const std::string& proto_desc);
template <typename MessageT>
bool WriteMessage(const std::string& channel_name, const MessageT& message,
                  const uint64_t time_nanosec,
                  const std::string& proto_desc = "");
bool SetSizeOfFileSegmentation(uint64_t size_kilobytes);
bool SetIntervalOfFileSegmentation(uint64_t time_sec);
```
