# Routine Automation Framework

用于统一执行网站 / App 日常任务的轻量 Python 自动化框架。

开发新模块请先阅读 [任务插件实现说明](docs/plugin-development.md)：包含完整接口约定、
配置示例、业务结果与异常处理、测试方法和运行方式。

## 运行

使用 Python 3.10 或更高版本，在项目根目录执行命令。
环境需具备 requirements.txt 中的公共依赖；插件不需要单独执行 pip install，
也不需要打包或发布。GitHub Actions 同样可以 checkout 项目、准备公共依赖后直接运行。

无需账号即可运行三个离线示例：

```bash
python -m app.main --config config/application-test.yaml
```

预期控制台通知内容（显示在带留白的通知区域内）：

```text
success: SUCCESS - 签到成功（模拟）
already_signed: SKIPPED - 今日已签到，无需重复签到（模拟）
failure: FAILED - 签到失败（模拟）
```

日志继续使用 Python 标准库 logging，由 core/logging.py 统一配置，
格式为“时间 | 等级 | 模块 | 消息”。日志和控制台通知均输出到 stdout，
避免 PyCharm 将普通 INFO 日志按标准错误流显示为红色。
支持颜色的终端、PyCharm 和 GitHub Actions 中，DEBUG 为灰色，INFO 使用主题默认文字色，
WARNING 为亮黄色，ERROR 为亮红色，CRITICAL 为加粗亮白字配红底，逐级增强提示。
控制台通知使用青色上下横线与左侧竖线，包含汇总和逐项结果。
长消息按估算的终端宽度换行。由于 IDE 中英文回退字体宽度可能不同，
不绘制依赖空格补齐的右边框，避免右侧参差不齐。

重定向到文件时默认不输出颜色控制符。可以设置 NO_COLOR=1 禁用颜色，
或 FORCE_COLOR=1 强制启用（NO_COLOR 优先）。

需要比较各等级日志颜色时，在运行参数后添加 --preview-logging：

```bash
python -m app.main --config config/application-test.yaml --preview-logging
```

该参数在执行任务前展示 DEBUG / INFO / WARNING / ERROR / CRITICAL，
每条都标注为样式预览，不抛异常；移除参数后恢复正常输出。

失败模块直接返回 FAILED 业务结果，不抛异常、不产生异常堆栈。
三个模块固定模拟各自场景，不访问真实站点，也不保存签到状态。
重复签到表示服务端已报告当天完成，映射为 SKIPPED，不视为错误。

实际使用时可复制 config/application-example.yaml 为 config/application.yaml，
安装所需插件的依赖并配置账号、启用任务后，再运行：

```bash
python -m app.main
```

已有本地 application.yaml 不会自动迁移。新示例包含默认禁用的 JMComic 和 PicACG 任务，
接入方式见 [JMComic 插件说明](plugins/jmcomic/README.md) 和
[PicACG 插件说明](plugins/picacg/README.md)。

## 本地插件约定

```text
plugins/
├── __init__.py
├── demo_success/
│   ├── __init__.py
│   └── plugin.py
├── demo_already_signed/
│   ├── __init__.py
│   └── plugin.py
├── demo_failure/
│   ├── __init__.py
│   └── plugin.py
├── picacg/
│   ├── __init__.py
│   ├── config.py
│   ├── client.py
│   ├── audit.py
│   ├── task.py
│   └── plugin.py
└── jmcomic/
    ├── __init__.py
    ├── config.py
    ├── client.py
    ├── task.py
    └── plugin.py
```

每个插件目录必须提供 plugin.py，并导出 PLUGIN：
它是 tasks.definition.TaskDefinition，包含任务类和 Pydantic 配置模型。

框架按 type 导入 plugins.<type>.plugin，不扫描、导入未启用的模块。
插件目录名称须以小写英文字母开头，其余字符允许小写字母、数字和下划线。
plugins/__init__.py 中不要集中导入插件；插件导入和构造阶段也不要执行签到。

新增模块只需添加自己的目录及文件，然后在 YAML 中配置。
无需修改 tasks/registry.py、入口或现有模块。复杂模块可以自行拆分 config.py、task.py，
plugin.py 只负责导出入口。

## 新模块示例

创建 plugins/example/__init__.py（空文件）和 plugins/example/plugin.py：

```python
from pydantic import Field

from configuration.model import StrictModel
from core.result import TaskResult, TaskStatus
from tasks.base import AutomationTask
from tasks.definition import TaskDefinition


class ExampleConfig(StrictModel):
    message: str = Field(default="执行完成", min_length=1)


class ExampleTask(AutomationTask):
    def __init__(self, task_name: str, config: ExampleConfig):
        super().__init__(task_name)
        self.config = config

    def execute(self) -> TaskResult:
        # 在这里执行实际业务，并根据业务响应判断结果。
        return TaskResult(
            self.task_name, TaskStatus.SUCCESS, self.config.message
        )


PLUGIN = TaskDefinition(ExampleTask, ExampleConfig)
```

应用配置：

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
```

account_a/account_b 是独立实例名，example 是模块类型。
每个实例各自创建配置对象和任务对象；未指定 type 时默认使用实例名。
enabled 默认 true，config 默认空字典。StrictModel 会拒绝未声明字段。

配置支持 `${ENV}` 和 `${ENV:default}`。只有启用任务才会检查其私有配置
中的缺失环境变量；通知仅在实际发送时创建和检查渠道。

## 执行与错误边界

- 按 YAML 中任务顺序串行执行，不包含内置定时调度。
- 配置错误、插件缺失、导入失败或构造失败会终止启动，错误包含相关模块或实例信息。
- 签到失败等业务结果直接返回 FAILED，不通过抛异常表达，仍会触发 error_only 通知。
- 程序异常由执行器捕获并记录堆栈：普通异常转为 FAILED，TaskTimeoutError 转为 TIMEOUT，后续任务继续执行。
- 插件也可以直接返回 SUCCESS / FAILED / TIMEOUT / SKIPPED。
- 执行器不会主动中断超时任务；具体模块需要设置请求超时等限制，并自行释放会话等资源。
- 通知支持多渠道独立配置 always / error_only；已提供 console 和 email。错误通知包含本批全部结果。
  配置示例、SMTP 接入及扩展方法见 [通知配置与插件开发](docs/notification-development.md)。
- 当前任务执行失败会记录到结果，但不据此设置非零进程退出码。
  GitHub Actions 若要将任务失败标记为工作流失败，后续还需增加退出码策略。

## 测试

```bash
python -m pytest -q
```

测试覆盖本地插件加载、禁用模块不导入、多实例配置、三种模拟结果、
失败后继续执行，以及通知策略。新增插件接入测试通过临时目录验证，
不修改中央注册代码。
