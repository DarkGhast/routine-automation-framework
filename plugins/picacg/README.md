# 哔咔每日签到插件

通过现有任务加载器接入，任务类型为 `picacg`。执行账号密码登录，取得内存中的
Token 后查询当前用户及签到状态，未签到时提交一次并重新查询确认。
已签到返回 `SKIPPED`，正常运行不重复提交。客户端的 `login()`、`get_profile()`、
`login_and_verify()` 保留，任务使用 `check_in()` 完成签到。

`isPunched` 必须是服务端返回的布尔值，缺失或类型异常不提交。
签到返回 `res.status=ok` 且查询确认为已签到，才报告完成；`res.status=fail`
必须结合查询确认为已签到，才判定为重复签到，否则返回业务失败。
服务端日期可能与本地日期不同，不用本机日历推断刷新时间。
主参考的执行顺序为登录、直接签到、查询资料，备用 JS 也直接提交签到；
本插件增加签到前的状态判断，避免每次运行都让服务端拒绝重复提交。

## 运行

沿用项目 Python 环境和根目录依赖；无新增第三方依赖，无单独交互入口。
项目公共示例 `config/application-example.yaml` 已包含默认禁用的 `picacg` 任务。
日常使用在本地 `config/application.yaml` 中配置并启用，使用 `python -m app.main`
运行所有启用任务。模块 README 的独立配置适合只运行哔咔，避免同时执行其他站点。
在项目根目录运行现有框架入口（示例仅包含哔咔任务，通知关闭）：

```powershell
.venv/Scripts/python.exe -m app.main --config plugins/picacg/application.example.yaml
```

示例配置见 [application.example.yaml](application.example.yaml)。正式插件只接收
框架注入的 `username/password`，不读取凭据文件。

环境变量方式遵循框架的 `${ENV}` 语法，可复制以下配置；框架先解析占位符，
插件使用 `SecretStr` 保存解析后的账号密码，不自行读取环境变量，也不自动加载 `.env`。
可以通过 IDE 的运行环境配置注入变量。启用任务缺少变量或凭据时在加载阶段报错，
禁用任务不检查其私有配置。

```yaml
tasks:
  picacg:
    type: picacg
    enabled: true
    config:
      username: ${PICA_USERNAME}
      password: ${PICA_PASSWORD}
      timeout: 15
      max_retries: 2
      proxy_mode: system
```

| 配置 | 默认值 | 含义 |
|---|---|---|
| `username` | 必填 | 配合 `${PICA_USERNAME}` 由框架注入 |
| `password` | 必填 | 配合 `${PICA_PASSWORD}` 由框架注入 |
| `timeout` | `15` | 单次网络阻塞操作超时秒数，范围 `(0, 120]`，不是整任务硬截止时间 |
| `max_retries` | `2` | GET 查询额外重试次数，范围 0–2；登录及签到 POST 不自动重试 |
| `proxy_mode` | `system` | 使用本机系统/环境代理；`direct` 强制直连 |

## 网络与响应日志

唯一目标为 `https://picaapi.picacomic.com`；仅允许 `POST auth/sign-in`、
`GET users/profile` 和 `POST users/punch-in`。保留系统信任链与主机名验证，禁用自动重定向。
默认用标准库 `getproxies()` 读取本机代理，环境变量优先，Windows 无环境代理时
读取系统静态代理配置；`NO_PROXY` 仍可能让目标绕过代理。仅支持 HTTP CONNECT
隧道代理（代理 URL 为 `http://`），不支持 SOCKS/PAC，也不引入 JM 的依赖。
`proxy_mode: direct` 禁用代理。不输出代理凭据或地址；
配置代理不代表实际路由一定使用代理。不自动发现公网代理、切换代理或回退直连。
代理不改变 API 目标，HTTPS 认证和加密保持启用；不提供镜像、TLS 跳过、
通知、遥测或下载执行功能。

GET 在网络失败、超时或 HTTP 429/500/502/503/504 时有限重试，退避 1、2 秒；
证书错误、业务拒绝、重定向、协议异常不重试。每次请求重新生成时间戳和 nonce。
响应读取上限 1 MiB，响应流始终关闭；不会因为 HTTP 200、首页可达或任务进程退出
成功就认定登录有效。

签到提交出现超时、网络错误或无法识别的响应时，只重新查询签到状态，不重发提交。
查询确认已签到时报告当日状态已完成；不能确认时保留原异常交给执行器。
这不能证明是哪一次请求完成了签到，但避免了在响应丢失后盲目重复提交。
直接调用 `submit_checkin()` 会绕过已签到预检查，仅用于开发者明确授权的重复调用诊断；
常规框架任务始终走 `check_in()`。

正式任务和普通真实联调不再创建响应日志文件，也不提供 `log_dir` 配置。
保留框架控制台进度、结果及异常日志，不保存请求体、Token、Cookie 或密码。
沿用框架 `logging.level`：`INFO` 输出登录进度与最终结果；`DEBUG` 增加代理模式和
是否配置、请求方法/接口/次数、HTTP 与业务码、耗时、重试和签到状态判断。
不输出代理地址、账号、Token 或完整响应；无需配置插件专用日志开关。
已有历史日志不删除；分析所需的两次成功签到及一次重复调用响应已提取到
[samples](samples/README.md)，仅含业务响应和验证结果，不含账号资料。
每实例创建独立客户端，重新登录及查询失败时清除旧 Token。

## 失败分类

- 明确的签名拒绝、凭据拒绝、Token 无效：`SIGNATURE_ERROR`、`CREDENTIALS_ERROR`、
  `TOKEN_INVALID`，返回框架 `FAILED`。
- 认证或业务拒绝但原因不明确：`AUTH_REJECTED`、`BUSINESS_REJECTED`，不猜测密码错误。
- 签到返回 `fail`，查询仍未签到：`CHECKIN_REJECTED`，返回框架 `FAILED`。
- 非 JSON、未知业务码、缺少 Token/用户 `_id`、HTTP 与业务成功码冲突：
  `UNKNOWN_RESPONSE` 协议异常，交给框架执行器处理。
- 网络、TLS、HTTP 暂时不可用、重定向：对应传输异常；实际超时转换为 `TaskTimeoutError`。

参考仓库没有完整错误码表。目前仅将服务端明确的有限错误文本映射为具体类别，
例如 `invalid signature`、`invalid credentials`、`token expired`。
这些分支的离线覆盖不代表已经实际触发所有服务端错误形式。
程序异常继续交给执行器，不伪装成业务失败。框架当前不依据任务失败设置进程退出码，
请查看框架任务结果，不要以退出码 0 判断成功。

## 协议依据与验证边界

2026-10-04 阅读的主参考版本与相关提交见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES)。
主参考与备用参考均指向上述 API 域名。站点 `https://www.picacomic.com/` 的官方
下载页面与 API 使用同一注册域，页面展示的 Android 版本也与参考请求头一致。
这支持请求目标核对，不等于对服务端运营者的独立身份审计，也不证明当前登录可用。
连接时仍必须通过 TLS 验证；不向第三方参考仓库作者的网站发送账号密码。

离线测试使用人工协议样例与脱敏真实响应结构，不读取真实凭据、不联网、不签到：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_picacg.py tests/test_picacg_config.py -q
.venv/Scripts/python.exe -m pytest -q
```

测试覆盖签名固定向量、加载/禁用、凭据读取时机、配置校验、两步成功条件、
错误分支、重试、连接策略、资源释放、账号切换、日志持久化与脱敏、首次签到、
已签到跳过、重复提交响应及提交结果不确定时的查询恢复。
已用真实账号验证首次签到、显式重复提交和框架再次运行自动跳过，详见
[验证记录](VERIFICATION.md)。正常使用运行上面的框架命令即可。

## 使用本地文件进行真实联调

文件仅作为测试入口的参数，不属于任务配置，与 JM 的联调方式一致：

```powershell
.venv/Scripts/python.exe -m plugins.picacg.live_test --credentials config-test/picacg-test.local.json
```

测试入口读取仅含 `username`、`password` 的 JSON（支持 UTF-8 BOM），经框架加载哔咔任务；
正式插件收到的仍是相同的账号密码配置。此命令会真实登录、查询并在未签到时提交一次，
不保存响应日志，不主动重复提交，不发送通知，失败返回非零退出码。
文件内容不会输出，不要提交凭据文件；在本机限制文件访问权限。
