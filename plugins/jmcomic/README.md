# JMComic 每日签到

通过移动端 API 登录、查询今日签到状态，并在未签到时提交一次签到。
一个框架任务实例对应一个账号，会话只在本次执行中使用并及时关闭。

## 依赖

在项目虚拟环境中安装插件专用依赖：

```powershell
.venv/Scripts/python.exe -m pip install -r plugins/jmcomic/requirements.txt
```

使用 `jmcomic==2.7.7` 的请求签名、响应解密、API 域名与请求头定义，
使用 `curl_cffi>=0.16.3,<0.17` 管理独立 HTTP 会话。
不创建上游 `JmOption` 或完整下载客户端，避免初始化联网、全局日志开关及默认重试。
没有自动安装依赖、下载图片或执行第三方插件的行为。

公共 `requirements.txt` 和框架代码未改变；启用本插件的运行环境或 CI
需要额外安装上述清单。仓库当前没有 CI 工作流。
普通离线业务测试无需网络依赖，协议加解密测试在未安装依赖时会跳过。

## 配置

```yaml
tasks:
  jm:
    type: jmcomic
    enabled: false
    config:
      username: ${JM_USERNAME}
      password: ${JM_PASSWORD}
      timeout: 20
      max_retries: 1
      random_delay_seconds: -1
      jmcomic_config: {}
      # 可选：仅填写可信的 API 主机名，不含协议、路径或账号信息。
      # api_domain: api.example.com
```

| 字段 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `username` | 是 | 无 | 用户名，示例环境变量 `JM_USERNAME` |
| `password` | 是 | 无 | 密码，示例环境变量 `JM_PASSWORD`，保留首尾空格 |
| `timeout` | 否 | `20` | 单次请求超时秒数，必须大于 0 且不超过 120 |
| `max_retries` | 否 | `1` | 登录、查询及签到的额外重试次数，整数 0～3；业务拒绝不盲目重试 |
| `random_delay_seconds` | 否 | `-1` | `-1`、`false` 或 `0` 不等待；正整数表示每次执行前随机等待 0～N 秒，上限 86400 |
| `jmcomic_config` | 否 | `{}` | 内嵌网络选项，格式见下文 |
| `api_domain` | 否 | 动态获取，内置备用 | 可选的 API 主机名，指定后不自动更新域名，始终使用 HTTPS |

填写环境变量后将 `enabled` 改为 `true`。框架不会自动读取 `.env`。
需要多账号时新增同类型任务实例，分别引用不同的凭据环境变量。
账号与密码使用 `SecretStr`，校验错误隐藏原始输入。

原三个离线演示任务保留在 `config/application-test.yaml`，新示例配置中的 JM 任务默认禁用。

### 内嵌网络选项

无需独立 `option_file`。`jmcomic_config` 是本插件支持的网络配置映射，
不是上游完整 YAML 的直接透传；未知字段会报配置错误，不会悄悄忽略。

```yaml
jmcomic_config:
  domains: [api.example.com]
  proxies:
    http: ${JM_PROXY_URL}
    https: ${JM_PROXY_URL}
  headers:
    User-Agent: your-user-agent
```

- `domains`：API 主机名列表，显式填写则不自动更新；兼容字段 `api_domain` 优先于该列表。
- `proxies`：支持 `http`、`https`、`all`，值为包含协议的代理 URL；省略或 `null` 使用系统代理，`{}` 强制直连。
- `headers`：仅用于站点 API 请求，不发给域名发现服务。覆盖同名默认头，值按秘密字段处理；
  不允许覆盖 `token`、`tokenparam`、`Cookie`、`Host`、`Referer`、`Content-Length`。

随机等待在创建网络会话前执行一次，重试不再次等待。框架串行执行，因此等待也会推迟后续任务。
它不提供定时启动或隔日调度；`timeout` 不包含该等待时间。

## 执行与结果

1. 未指定域名时从 SDK 定义的域名服务获取最新列表，失败则使用内置域名；只在无凭据的初始化阶段切换域名。
2. 向 `/setting` 请求初始化会话，若 `jm3_version` 是更高的有效版本，更新本次会话请求签名中的 App 版本，不修改 SDK 全局状态。
3. `/login` 成功且包含有效 `uid` 与 `s` 后，保存当前会话的 AVS Cookie。
4. `/daily` 的 `signed` 或当月日历明确表明今日已签到时返回 `SKIPPED`。
5. 否则将 `user_id` 与 `daily_id` 提交到 `/daily_chk`，识别奖励、成功或重复签到标记。

HTTP 200 本身不代表成功。每步检查 API 业务码，校验并解密响应；
未知业务码、未知签到消息、缺失或畸形日历均交给框架作为协议异常处理。
非成功业务码附带服务端错误说明时返回 `FAILED`，通知只包含脱敏的阶段结论。
已识别的网络超时交给框架转为 `TIMEOUT`，其他网络错误仍为异常。

响应 JSON 前后允许有额外字符；无法解析或包含多个候选对象时拒绝猜测，不输出原文。
签到日期按 UTC+8 计算，不跟随重定向。
登录与状态查询在网络异常后有限重试。签到提交超时或连接失败后，先复查今日状态：
已签到返回 `SKIPPED`，确认未签到才在重试预算内再次提交；复查无法完成则保留原网络异常。
重试提交被明确拒绝时，再次核对服务端状态，避免将前次已完成的签到误报为失败。
重复签到提示在成功业务码响应和非成功业务码的错误消息中均可识别。
这种 `SKIPPED` 只表示已确认今日完成，不声称是本次获得奖励。
`timeout` 是每次请求的上限，不是整个任务的总时限。域名发现、备用域名和重试可能增加总耗时。
不输出账号、UID、密码、Cookie、Token、奖励原文或完整响应。

会话与上游 `JmOption` 一样，通过 `ProxyBuilder.system_proxy()` 读取系统代理。
Windows 代理可能保存在注册表中，即使没有 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量也可生效。
DEBUG 会分别报告系统代理检测结果和环境变量存在性，不输出代理地址或认证信息。

## 测试

### PyCharm 调试日志

使用 `app.main --config config/application.yaml` 时，将本地 YAML 的
`logging.level` 设置为 `DEBUG`。如果仍使用示例中的 `${LOG_LEVEL:INFO}`，
也可以在 PyCharm 的环境变量中添加 `LOG_LEVEL=DEBUG`。

日志包含阶段、域名、耗时、HTTP/业务码、curl 数值错误码与对应类别，以及代理环境变量是否非空。
同时报告 Python UTF-8 模式、路径编码及默认 CA 文件存在性和路径是否含非 ASCII 字符，
不输出证书路径。Windows 中文路径下遇到错误码 77 时，可据此检查 UTF-8 模式与底层路径编码是否一致。
不记录原始异常、代理地址、请求参数、请求头或响应正文；环境变量存在并不证明实际使用了该代理。
常见类别：`COULDNT_RESOLVE_HOST` 为域名解析失败，`COULDNT_RESOLVE_PROXY` 为代理解析失败，
`COULDNT_CONNECT` 为连接失败，`SSL_CONNECT_ERROR` 为 TLS 握手错误，
`PEER_FAILED_VERIFICATION` 为证书验证失败，`SSL_CACERT_BADFILE` 为本地 CA 文件问题。
不要通过关闭证书验证解决 TLS 错误。`live_test` 会主动隐藏日志，应使用主框架入口排查。

### 离线与真实联调

离线测试，不会读取真实凭据或访问站点：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_jmcomic.py tests/test_jmcomic_client.py tests/test_jmcomic_live_test.py -q
```

手动真实联调（会登录并在需要时签到）：

```powershell
.venv/Scripts/python.exe -m plugins.jmcomic.live_test --credentials config-test/jmcomic-test.local.json
```

本地 JSON 文件仅包含 `username`、`password` 两个字符串字段。
使用前确保凭据目录被 Git 忽略。联调程序直接读取凭据，关闭本进程日志输出，
丢弃执行期间的标准输出和标准错误，最终仅输出固定的 JSON 状态与脱敏结论。
它不会调用其他已配置任务、发送通知、修改运行配置或将响应保存到文件。
该入口不是 pytest 自动测试的一部分。成功或已签到退出码为 0，其他结果为 1。

2026-10-04 经授权对已签到账号额外提交一次 `/daily_chk`：实际返回业务码 `200`，
消息为“今天已經簽到過了”，插件映射为 `SKIPPED`。首次签到成功仍待未签到日期验证。

## 与原服务的范围差异

本插件不常驻调度。随机延迟由 `random_delay_seconds` 提供，在任务开始前等待；
批量重试是出现失败后按分钟间隔重新执行全部账号，此行为未迁入插件，
与这里的单账号、有限请求重试不同。

原项目的 `option_file` 是 `jmcomic` 的高级 YAML 配置入口，可覆盖代理、域名、
请求头、客户端和重试等选项。本插件使用上述 `jmcomic_config` 内嵌网络选项，
不加载上游的下载器或插件扩展配置。重试次数统一使用 `max_retries`。定时与通知仍由外部调度或框架管理。

## 来源

签到流程参考 [YsKiKi/jmComicCheckIn](https://github.com/YsKiKi/jmComicCheckIn)，
并核对 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)
2.7.7 中的 API 协议及 `daily_checkin` 实现。参考项目的 MIT 许可保存在
[LICENSE.reference](LICENSE.reference)。
