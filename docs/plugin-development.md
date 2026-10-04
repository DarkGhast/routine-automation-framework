# 任务插件实现说明

本文面向插件开发者，介绍如何在当前框架中实现、配置、测试和运行本地任务插件。

## 1. 开发范围

新任务插件放在 `plugins/<type>/`，测试放在 `tests/test_<type>*.py`，
模块自己的接入说明和脱敏配置示例放在该插件目录的 `README.md` 中。

通常只需添加上述文件，再在运行配置中启用插件。无需修改中央注册表，
不需要将插件打包、发布或执行 `pip install -e`。

插件负责具体站点的配置和业务实现，框架负责以下公共能力：

- 任务加载、接口、结果状态和执行策略。
- 全局配置解析、日志格式、配色、通知策略和通知渠道。

符合现有接口的插件无需修改 `app/`、`core/`、`configuration/`、`notification/`
或 `tasks/`。当前尚未提供的公共能力见文末“当前框架边界”。

插件无需单独安装，不等于第三方依赖不需要准备。当前公共依赖见根目录
`requirements.txt`；不要假定 HTTP 客户端或浏览器库已安装。确需新增依赖时，
在模块说明中列出用途和版本要求，并同步准备依赖清单及 CI 环境。
不要在插件运行期间自动安装依赖或下载浏览器。

## 2. 目录和入口

建议真实站点采用以下结构，小模块也可以合并到 `plugin.py`：

```text
plugins/
  example/
    __init__.py
    config.py
    task.py
    plugin.py
    README.md
tests/
  test_example.py
```

- `<type>` 必须匹配 `[a-z][a-z0-9_]*`，例如 `example_site`。
- `__init__.py` 可以为空；不要在公共 `plugins/__init__.py` 中集中导入插件。
- `plugin.py` 必须导出名为 `PLUGIN` 的 `TaskDefinition` 对象。
- 框架只导入配置中启用的 `plugins.<type>.plugin`，不扫描全部模块。
- 导入和任务构造阶段只定义对象、保存配置，不执行登录、签到或其他网络操作。

当前接口定义：

| 接口 | 源码 | 约定 |
|---|---|---|
| `AutomationTask` | [tasks/base.py](../tasks/base.py) | 实现同步 `execute()` |
| `TaskDefinition` | [tasks/definition.py](../tasks/definition.py) | 提供任务类与 Pydantic 配置类 |
| 插件加载器 | [tasks/registry.py](../tasks/registry.py) | 校验配置后调用任务类 `(实例名, 配置对象)` |
| `StrictModel` | [configuration/model.py](../configuration/model.py) | 拒绝未声明字段，保留 Pydantic 类型转换 |
| `TaskResult` / `TaskStatus` | [core/result.py](../core/result.py) | 统一结果格式及状态 |
| `TaskTimeoutError` | [core/exception.py](../core/exception.py) | 由执行器识别的超时异常 |

## 3. 最小接入示例

下面的 `example` 是离线接入示例，只验证插件能被加载，不代表真实站点签到。
真实插件须依据服务端业务响应判断结果，不应直接沿用固定成功返回。

`plugins/example/config.py`：

```python
from pydantic import Field

from configuration.model import StrictModel


class ExampleConfig(StrictModel):
    message: str = Field(default="示例任务执行完成", min_length=1)
```

`plugins/example/task.py`：

```python
from core.logging import get_logger
from core.result import TaskResult, TaskStatus
from tasks.base import AutomationTask
from .config import ExampleConfig


logger = get_logger(__name__)


class ExampleTask(AutomationTask):
    def __init__(self, task_name: str, config: ExampleConfig):
        super().__init__(task_name)
        self.config = config

    def execute(self) -> TaskResult:
        logger.debug("开始执行实例：%s", self.task_name)
        # 仅模拟接入；真实模块在此执行并判断业务结果。
        return TaskResult(
            task_name=self.task_name,
            status=TaskStatus.SUCCESS,
            message=self.config.message,
        )
```

`plugins/example/plugin.py`：

```python
from tasks.definition import TaskDefinition
from .config import ExampleConfig
from .task import ExampleTask


PLUGIN = TaskDefinition(task_class=ExampleTask, config_class=ExampleConfig)
```

框架默认只传入两个位置参数。为了便于测试，可以增加带默认值的客户端或工厂参数，
但不能新增框架必须传入的参数。每个实例的配置、会话和账号状态应互相独立。

## 4. 配置与多实例

```yaml
tasks:
  account_a:
    type: example
    enabled: true
    config:
      message: 实例 A 执行完成
  account_b:
    type: example
    enabled: true
    config:
      message: 实例 B 执行完成

notification:
  enabled: true
  policy: always
  channel:
    type: console
    config: {}
```

- `account_a`、`account_b` 是实例名，也是日志和结果中的标识。
- `type` 对应插件目录；同一插件可以创建多个实例。省略 `type` 时使用实例名。
- `enabled` 默认 `true`，`config` 默认空字典，私有字段由插件配置模型定义。
- YAML 支持 `${ENV_NAME}` / `${ENV_NAME:default}`，框架先解析，再校验插件配置。
- 禁用任务不会导入插件或校验私有配置中的凭据；全局配置结构仍会校验。
- 账号凭据通过环境变量提供，配置示例只使用占位符。密码和 Token 可使用
  Pydantic `SecretStr`；这不能替代日志脱敏，不要打印其解密值。
- 默认不自动读取 `.env`。可通过 shell、PyCharm 或 CI 注入环境变量。

本地运行配置 `config/application.yaml` 已被 Git 忽略，不应提交真实凭据。
模块自己的 README 应包含字段、默认值、
环境变量名称以及一份可复制的脱敏配置。

## 5. 业务结果与程序异常

`execute()` 必须返回 `TaskResult(self.task_name, status, message)`，不能返回
`None`、字典或状态字符串。当前执行器不会额外验证返回对象的类型。

| 情况 | 处理方式 | 错误通知 |
|---|---|---|
| 本次签到成功 | 返回 `SUCCESS` | 单独出现时不触发 `error_only` |
| 服务端明确返回今日已签到 | 返回 `SKIPPED`，说明无需重复签到 | 不触发 |
| 服务端明确拒绝，例如登录失败、签到条件不满足 | 返回 `FAILED`，保留可读原因 | 触发 |
| 网络或任务超时 | 将已识别的超时转换为 `TaskTimeoutError`；执行器记录堆栈并生成 `TIMEOUT` | 触发 |
| 程序错误、无法按预期解析的协议响应等异常 | 让异常交给执行器；执行器记录堆栈并生成 `FAILED` | 触发 |

业务失败直接返回结果，不要 `raise RuntimeError("签到失败")`，也不要为了输出
业务失败去调用 `logger.exception()`。程序异常不要捕获后伪装成业务失败或成功。
框架当前用相同的 `FAILED` 状态汇总业务失败与普通异常，但异常另有堆栈日志。

只将确实识别的客户端超时异常转换为 `TaskTimeoutError`，不要把所有网络异常都归为超时。
框架只捕获这个专用超时类；其他未经转换的异常会按普通失败处理。

真实站点至少需要分别核验登录结果与签到结果。HTTP 200 或响应中存在 `msg`
不能单独作为成功依据；未知业务码或无法识别的页面也不能默认成功。

三个离线参考实现：

- [成功](../plugins/demo_success/plugin.py)
- [重复签到](../plugins/demo_already_signed/plugin.py)
- [业务失败](../plugins/demo_failure/plugin.py)

## 6. 日志、通知和资源

使用 `get_logger(__name__)` 或标准库 `logging.getLogger(__name__)`，两者接入同一套日志。
不要在插件中调用 `basicConfig()`、添加全局 handler、修改根 logger 等级或手写 ANSI 颜色。

- `DEBUG`：分支判断和排错所需的中间状态。
- `INFO`：必要的执行进度；不要重复打印完整通知汇总。
- `WARNING`：需要留意但仍可继续的情况。
- `ERROR` / `CRITICAL`：按严重程度使用；交给执行器的异常通常无需重复记录堆栈。

不要打印密码、Token、Cookie 或完整敏感响应。结果的 `message` 同样会进入通知，
应提供简洁的业务结论。插件不直接 `print()` 通知或调用通知渠道，由框架统一发送。
`error_only` 判断的是整批任务：任意 `FAILED` / `TIMEOUT` 会触发本批全部结果通知。

网络请求必须有明确超时；当前框架不主动中断任务，也不提供自动重试。
如模块确需重试，限制次数，并区分可重试的连接故障和可能已完成的业务操作。
会话、文件、浏览器等资源由插件通过上下文管理器或 `finally` 释放，
框架没有统一的 `close()` 回调。不要在模块全局共享带账号 Cookie 的 Session。

## 7. 测试与本地运行

优先使用 Fake Client / Fake Session 或 mock 测试真实模块的业务判断，单元测试不依赖网络
和真实账号。模拟响应应来自已理解的协议，不要为了让测试通过而猜测业务成功字段。

至少覆盖：

1. 成功、重复签到、业务失败三种响应映射。
2. 登录失败时不继续发送签到请求。
3. 超时、异常响应、程序异常及资源释放。
4. 必填配置、非法值、未声明字段；多实例之间配置和会话隔离。
5. 通过 `create_tasks(ApplicationConfig.model_validate(...))` 加载插件，
   验证接入不依赖修改注册表。

可参考 [加载测试](../tests/test_task_registry.py)、
[场景集成测试](../tests/test_demo_plugins.py) 和 [异常隔离测试](../tests/test_executor.py)。

在项目根目录、使用项目 Python 环境执行：

```bash
python -m pytest tests/test_example.py -q
python -m pytest -q
python -m app.main --config config/application.yaml
```

最后一条会执行配置中所有启用的任务；模块联调前检查配置范围，真实登录或签到
应与离线单元测试分开。离线测试通过不代表真实站点协议或连通性已经验证。

PyCharm 选择 Python 运行配置：模块名称 `app.main`，工作目录为项目根目录，
解释器为项目 `.venv`，参数 `--config config/application.yaml`。
使用另一个配置文件时相应替换参数；不需要直接运行插件文件。

## 8. 当前框架边界

- 单次启动，按 YAML 顺序串行执行，没有内置定时调度、异步执行或热加载。
- 所有任务先创建，再执行；启用插件的配置、导入或构造错误会阻止整批任务启动。
- 执行阶段的普通异常被隔离，后续任务继续执行。
- 被禁用的任务直接过滤，不产生 `SKIPPED` 结果；`SKIPPED` 是已执行任务返回的业务状态。
- 执行失败目前不会自动设置非零进程退出码；GitHub Actions 的绿色不代表所有业务任务成功。
- 通知渠道也支持本地插件，使用独立的 notification_plugins 目录，见 [通知插件说明](notification-development.md)。
- 插件协议尚无独立版本机制，开发时以当前仓库接口为准。
