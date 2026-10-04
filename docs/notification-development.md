# 通知配置与插件开发

框架支持多个本地通知渠道，每个实例独立配置开关和发送策略。
已有 console 控制台和 email 邮件插件。新增渠道不需要修改注册表或安装插件包。

## 控制台始终打印，邮件仅在失败时发送

用以下内容替换 application.yaml 的整个 notification 段：

```yaml
notification:
  enabled: true
  channels:
    screen:
      type: console
      policy: always
      config: {}
    failure_mail:
      type: email
      enabled: true
      policy: error_only
      config:
        host: ${SMTP_HOST}
        port: 465
        security: ssl
        username: ${SMTP_USERNAME}
        password: ${SMTP_PASSWORD}
        sender: ${MAIL_FROM}
        sender_name: 日常签到助手
        recipients:
          - ${MAIL_TO}
        subject: 日常签到失败通知
        timeout: 20
```

channels 的键是实例名；可以配置多个同类渠道，例如两个邮箱。
enabled 默认 true，policy 默认 always。
error_only 在任意任务结果为 FAILED 或 TIMEOUT 时发送本批全部结果；
只有 SUCCESS / SKIPPED 时不发送。空任务列表仅触发 always。
notification.enabled 是总开关；channels: {} 表示不配置任何渠道。

旧版 notification.policy + notification.channel 配置继续有效，但不能与 channels 混用。
渠道仅在实际需要发送时才导入、验证和构造；禁用或未触发的邮件渠道无需提供凭据。

各渠道按配置顺序发送。某个渠道导入、配置、构造或发送失败时，记录渠道名和异常类型，
继续其他渠道，最终抛出汇总异常，使命令以非零退出码结束。
不输出底层异常原文，避免 SMTP 服务响应或验证输入泄露凭据。
有限超时控制每个网络操作；目前不并发发送、不自动重试，避免重复投递。

当前 error_only 针对执行器产生的任务结果。配置加载、任务构造等启动阶段错误、
进程被终止、工作流未启动，都还不能由结果通知覆盖；后续心跳监测可覆盖未收到运行回报的情况。
邮件正文包含任务结果 message；任务插件仍应负责返回脱敏内容。

## SMTP 配置

- host：邮件服务商的 SMTP 服务器地址，不包含协议前缀。
- ssl：连接时启用 TLS；常用端口 465，也是默认值。
- starttls：连接后升级 TLS；常用端口 587，需同时修改 security 和 port。
- TLS 始终验证证书和主机名，不支持明文发送或关闭证书验证。
- username/password 同时提供；按邮箱服务商要求使用 SMTP 授权码或应用密码。
  两者同时省略可连接无需认证的 TLS 邮件中继。
- sender、recipients：纯邮箱地址；recipients 是非空列表，支持多个收件人。
- sender_name：可选的发件人显示名称，支持中文；省略时仅设置邮箱地址。邮箱客户端可能优先显示联系人备注。
- subject：邮件主题；timeout：单次阻塞网络操作超时秒数，默认 20，最大 120。
- SMTP 接受邮件不代表邮件最终到达收件箱；部分收件人被拒绝也视为发送失败。
- 使用 Python 标准库 smtplib / email，不需要新增依赖。

实现依据：[Python smtplib 文档](https://docs.python.org/3/library/smtplib.html)。

本地运行通过 IDE 环境变量提供配置；框架不自动读取 .env。
GitHub Actions 中不仅要创建 Secrets，还要在执行步骤映射环境变量，例如：

```yaml
env:
  SMTP_HOST: ${{ secrets.SMTP_HOST }}
  SMTP_USERNAME: ${{ secrets.SMTP_USERNAME }}
  SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
  MAIL_FROM: ${{ secrets.MAIL_FROM }}
  MAIL_TO: ${{ secrets.MAIL_TO }}
```

不要把真实密码写入公开的示例配置。框架升级不会自动修改私有仓库的 application.yaml 或工作流。

## 多个收件人

recipients 是 YAML 列表，每项填写一个邮箱地址：

```yaml
recipients:
  - first@example.com
  - second@example.com
```

也可以分别引用环境变量：

```yaml
recipients:
  - ${MAIL_TO}
  - ${MAIL_TO_SECOND}
```

不要把多个地址用逗号或分号拼进同一项或同一个环境变量；框架不会自动拆分。
在 GitHub Actions 使用新增变量时，也要将相应 Secret 映射到执行步骤的 env。
当前使用 To（收件人）群发，收件人可以看到彼此的地址；尚不提供抄送或密送。
如果只希望各自看到自己的地址，可配置多个 email 渠道实例，每个实例一个收件人。

## 实现新通知插件

目录约定：

```text
notification_plugins/
  example/
    __init__.py
    plugin.py
```

type 必须匹配 [a-z][a-z0-9_]*。
plugin.py 导出 PLUGIN，使用 NotificationDefinition 指定渠道类和 Pydantic 配置类：

```python
from configuration.model import StrictModel
from notification.base import NotificationChannel
from notification.definition import NotificationDefinition


class ExampleConfig(StrictModel):
    prefix: str = "通知"


class ExampleChannel(NotificationChannel):
    def __init__(self, config: ExampleConfig):
        self.config = config

    def send(self, results):
        # 仅作接口演示，真实发送逻辑写在这里。
        print(self.config.prefix, len(results))


PLUGIN = NotificationDefinition(ExampleChannel, ExampleConfig)
```

配置 type: example 即可加载。构造函数只接收验证后的配置对象，不能执行网络操作。
send(results) 接收 list[TaskResult]，成功返回 None，失败抛异常。
不要修改传入结果，不要输出凭据，不要在插件内部决定 always/error_only 策略。
发送时自行设置网络超时并释放连接。测试放 tests/test_<渠道名>_notification.py，
使用离线模拟；真实邮件联调应单独授权。
