"""只使用 jmcomic 的协议工具，独立管理会话、超时和业务结果。"""

import json
import locale
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from core.exception import TaskTimeoutError
from core.logging import get_logger
from core.result import TaskStatus

from .config import JMComicConfig


logger = get_logger(__name__)


def network_error_info(exc):
    """只读取数值错误码；绝不格式化原始异常（可能包含请求或代理凭据）。"""
    from curl_cffi.const import CurlECode

    raw_code = getattr(exc, "code", None)
    code = int(raw_code) if isinstance(raw_code, int) and not isinstance(raw_code, bool) else None
    try:
        category = CurlECode(code).name
    except (ValueError, TypeError):
        category = "UNKNOWN"
    return code, category


class JMProtocolError(ValueError):
    """响应不符合已知协议；消息不包含原始响应。"""


class JMTransportError(ConnectionError):
    """已脱敏的连接或 HTTP 错误。"""


class BusinessRejected(Exception):
    """客户端内部的明确业务拒绝，由任务转换为 FAILED。"""

    def __init__(self, message, *, already_signed=False):
        super().__init__(message)
        self.already_signed = already_signed


def already_signed_message(msg) -> bool:
    return isinstance(msg, str) and (msg.strip() in ("已簽到", "已签到") or any(
        marker in msg for marker in (
            "今天已經簽到過了", "今日已簽到", "今天已签到", "今日已签到", "已經簽到過",
        )
    ))


def parse_json_object(text: str) -> dict:
    """容忍 JSON 前后的杂字符；多个候选对象拒绝猜测，不记录原文。"""
    decoder = json.JSONDecoder()
    objects = []
    position = 0
    while position < len(text):
        start = text.find("{", position)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(text, start)
        except ValueError:
            position = start + 1
            continue
        objects.append(value)
        position = end
    if len(objects) != 1 or not isinstance(objects[0], dict):
        raise JMProtocolError("响应无法确定唯一 JSON 对象")
    return objects[0]


def site_today():
    """签到日历使用 UTC+8，不依赖运行机器的本地时区。"""
    return datetime.now(timezone(timedelta(hours=8))).date()


def signed_today(data: dict, day: int) -> bool:
    flag = data.get("signed")
    if flag is True:
        return True
    if flag is not None and type(flag) is not bool:
        raise JMProtocolError("签到状态字段格式异常")
    record = data.get("record")
    if record is None:
        if flag is False:
            return False
        raise JMProtocolError("签到响应缺少可识别的今日状态")
    if not isinstance(record, list):
        raise JMProtocolError("签到日历格式异常")
    matched = []
    for week in record:
        if not isinstance(week, list):
            raise JMProtocolError("签到日历格式异常")
        for item in week:
            if not isinstance(item, dict):
                raise JMProtocolError("签到日历项目格式异常")
            date = item.get("date")
            # 日历边缘允许空白日期；其他非法日期不能当作未签到。
            if date in (None, ""):
                continue
            if type(date) not in (int, str) or not re.fullmatch(r"\d{1,2}", str(date)):
                raise JMProtocolError("签到日历日期格式异常")
            if not 1 <= int(date) <= 31:
                raise JMProtocolError("签到日历日期超出范围")
            if int(date) == day:
                value = item.get("signed")
                if value is not None and type(value) is not bool:
                    raise JMProtocolError("签到日历状态格式异常")
                matched.append(value is True)
    if len(matched) != 1:
        raise JMProtocolError("签到日历无法唯一确定今日状态")
    return matched[0]


def checkin_status(data: dict) -> TaskStatus:
    """依据上游 daily_checkin 的业务标记，未知消息不默认成功。"""
    msg = data.get("msg", "")
    if not isinstance(msg, str):
        raise JMProtocolError("签到结果消息格式异常")
    if already_signed_message(msg):
        return TaskStatus.SKIPPED
    if data.get("status") == "ok" or re.fullmatch(
        r"\s*(?:(?:Jcoin|EXP)\s*[:：]\s*\d+\s*)+", msg,
    ):
        return TaskStatus.SUCCESS
    if msg.strip() in ("签到成功", "簽到成功", "签到成功！", "簽到成功！"):
        return TaskStatus.SUCCESS
    raise JMProtocolError("签到接口返回了未知业务结果")


def positive_id(value, field: str) -> str:
    if type(value) not in (int, str) or not re.fullmatch(r"[0-9]+", str(value)) or int(value) <= 0:
        raise JMProtocolError(f"响应缺少有效的 {field}")
    return str(value)


class JMComicClient:
    def __init__(self, config: JMComicConfig, session_factory=None, today=site_today):
        self.config = config
        self.session_factory = session_factory
        self.today = today
        self.session = None
        self.domain = None
        self.uid = None
        self.app_version = None

    def _discover_domains(self):
        from curl_cffi.requests.exceptions import RequestException
        from jmcomic import JmModuleConfig, JmCryptoTool, JmMagicConstants

        for index, url in enumerate(JmModuleConfig.API_URL_DOMAIN_SERVER_LIST, 1):
            try:
                response = self.session.request("GET", url, timeout=self.config.timeout, allow_redirects=False)
                if response.status_code != 200:
                    continue
                text = response.text.lstrip("\ufeff\ufffe\u200b \r\n\t")
                payload = parse_json_object(JmCryptoTool.decode_resp_data(
                    text, "", JmMagicConstants.API_DOMAIN_SERVER_SECRET,
                ))
                domains = payload.get("Server")
                if not isinstance(domains, list) or not domains or len(domains) > 32:
                    raise JMProtocolError("域名列表格式异常")
                if not all(isinstance(d, str) for d in domains):
                    raise JMProtocolError("域名项目格式异常")
                # 复用主机名校验，禁止返回 URL、端口或含凭据的地址。
                validated = [JMComicConfig(username="unused", password="unused", api_domain=d).api_domain for d in domains]
                logger.debug("JMComic 域名更新成功：候选数=%d", len(validated))
                return list(dict.fromkeys(validated))
            except (RequestException, ValueError, TypeError, IndexError):
                logger.debug("JMComic 域名更新源 %d 不可用，继续尝试（原始信息隐藏）", index)
        logger.debug("JMComic 域名更新不可用，使用内置域名")
        return []

    def __enter__(self):
        # 延迟导入：禁用插件、构造任务和离线业务测试无需安装网络依赖。
        from curl_cffi.requests import Session
        from common import ProxyBuilder
        import certifi

        factory = self.session_factory or Session
        # 与 JmOption 的默认行为一致：Windows 系统代理可能仅保存在注册表中。
        configured = self.config.jmcomic_config.proxies
        proxies = ProxyBuilder.system_proxy() if configured is None else {
            key: secret.get_secret_value() for key, secret in configured.items()
        }
        options = {}
        if configured is not None and not configured:
            from curl_cffi import CurlOpt
            # 显式空字典表示直连，不能再让 libcurl 回退到环境代理。
            options["curl_options"] = {CurlOpt.PROXY: b""}
        self.session = factory(impersonate="chrome", timeout=self.config.timeout, proxies=proxies, **options)
        logger.debug("JMComic 代理来源=%s，已配置=%s（不输出地址）",
                     "系统" if configured is None else "插件配置", bool(proxies))
        # 仅报告变量是否非空，不输出代理地址、用户名或密码。
        proxy_flags = ", ".join(
            f"{name}={bool(os.environ.get(name))}"
            for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                         "http_proxy", "https_proxy", "all_proxy", "no_proxy")
        )
        logger.debug("JMComic 会话创建：timeout=%s 秒；代理环境变量（不代表实际路由）：%s",
                     self.config.timeout, proxy_flags)
        ca_path = certifi.where()
        logger.debug("JMComic TLS 环境：utf8_mode=%s，路径编码=%s，默认CA文件存在=%s，默认CA路径含非ASCII=%s",
                     sys.flags.utf8_mode, locale.getpreferredencoding(False),
                     os.path.isfile(ca_path), not ca_path.isascii())
        return self

    def __exit__(self, *_):
        try:
            self.session.close()
        finally:
            self.session = None
            self.uid = None
            logger.debug("JMComic 会话已释放")

    def prepare(self):
        from jmcomic import JmModuleConfig

        from jmcomic import JmMagicConstants

        self.app_version = JmMagicConstants.APP_VERSION
        explicit = [self.config.api_domain] if self.config.api_domain else self.config.jmcomic_config.domains
        updated = [] if explicit else self._discover_domains()
        domains = explicit or list(dict.fromkeys(
            [*updated, *JmModuleConfig.DOMAIN_API_LIST]
        ))
        last_error = None
        logger.debug("JMComic 初始化：域名来源=%s，候选数=%d",
                     "配置指定" if explicit else ("动态更新及内置" if updated else "SDK 内置"), len(domains))
        for index, domain in enumerate(domains, 1):
            logger.debug("JMComic 初始化尝试：%d/%d，domain=%s", index, len(domains), domain)
            self.domain = domain
            self.session.cookies.clear()
            try:
                settings = self._request("/setting", "初始化")
                version = settings.get("jm3_version")
                if isinstance(version, str) and re.fullmatch(r"\d{1,4}(?:\.\d{1,4}){1,3}", version):
                    from jmcomic import JmcomicText
                    if JmcomicText.compare_versions(version, self.app_version) > 0:
                        self.app_version = version
                        logger.debug("JMComic 本次会话更新 App 版本：%s", version)
                logger.debug("JMComic 初始化完成：domain=%s", domain)
                return
            except (JMTransportError, TaskTimeoutError) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise JMProtocolError("没有可用的 API 域名")

    def _request(self, path: str, stage: str, *, data=None, params=None) -> dict:
        from curl_cffi.requests.exceptions import RequestException, Timeout
        from jmcomic import JmCryptoTool, JmModuleConfig

        ts = str(int(time.time()))
        token, tokenparam = JmCryptoTool.token_and_tokenparam(ts, ver=self.app_version)
        headers = dict(JmModuleConfig.APP_HEADERS_TEMPLATE)
        for name, value in self.config.jmcomic_config.headers.items():
            # HTTP 头不区分大小写，避免同名头以不同大小写出现两次。
            for old in list(headers):
                if old.lower() == name.lower():
                    del headers[old]
            headers[name] = value.get_secret_value()
        headers.update(token=token, tokenparam=tokenparam, Referer=f"https://{self.domain}")
        method = "POST" if data is not None else "GET"
        started = time.monotonic()
        logger.debug("JMComic 请求开始：阶段=%s，method=%s，domain=%s，timeout=%s 秒",
                     stage, method, self.domain, self.config.timeout)
        try:
            response = self.session.request(
                method,
                f"https://{self.domain}{path}",
                data=data, params=params, headers=headers,
                timeout=self.config.timeout, allow_redirects=False,
            )
        except (Timeout, RequestException) as exc:
            code, category = network_error_info(exc)
            logger.debug("JMComic 请求失败：阶段=%s，domain=%s，curl_code=%s，类别=%s，耗时=%.3f 秒",
                         stage, self.domain, code, category, time.monotonic() - started)
            if isinstance(exc, Timeout):
                raise TaskTimeoutError(f"JMComic {stage}请求超时（curl_code={code}, {category}）") from None
            raise JMTransportError(f"JMComic {stage}连接失败（curl_code={code}, {category}）") from None

        logger.debug("JMComic 收到响应：阶段=%s，HTTP=%s，耗时=%.3f 秒",
                     stage, response.status_code, time.monotonic() - started)
        if response.status_code != 200:
            raise JMTransportError(f"JMComic {stage} HTTP 请求失败")
        try:
            envelope = response.json()
        except (ValueError, UnicodeError):
            try:
                envelope = parse_json_object(getattr(response, "text", ""))
            except JMProtocolError:
                raise JMProtocolError(f"JMComic {stage}响应不是可识别的 JSON") from None
        if not isinstance(envelope, dict) or type(envelope.get("code")) is not int:
            raise JMProtocolError(f"JMComic {stage}响应缺少有效业务码")
        logger.debug("JMComic 响应业务码：阶段=%s，code=%d", stage, envelope["code"])
        if envelope["code"] != 200:
            if isinstance(envelope.get("errorMsg"), str) and envelope["errorMsg"].strip():
                raise BusinessRejected(f"JMComic {stage}被服务端拒绝", already_signed=(
                    path == "/daily_chk" and already_signed_message(envelope["errorMsg"])
                ))
            raise JMProtocolError(f"JMComic {stage}返回未知业务码")
        encoded = envelope.get("data")
        if not isinstance(encoded, str) or not encoded:
            raise JMProtocolError(f"JMComic {stage}响应缺少加密数据")
        try:
            decoded = json.loads(JmCryptoTool.decode_resp_data(encoded, ts))
        except (ValueError, TypeError, IndexError):
            raise JMProtocolError(f"JMComic {stage}响应解密或解析失败") from None
        if not isinstance(decoded, dict):
            raise JMProtocolError(f"JMComic {stage}响应数据格式异常")
        return decoded

    def login(self):
        data = self._read_with_retry("/login", "登录", data={
            "username": self.config.username.get_secret_value(),
            "password": self.config.password.get_secret_value(),
        })
        uid = positive_id(data.get("uid"), "uid")
        session_token = data.get("s")
        if not isinstance(session_token, str) or not session_token:
            raise JMProtocolError("登录响应缺少有效会话")
        self.session.cookies.set("AVS", session_token, domain=self.domain, path="/")
        self.uid = uid

    def _read_with_retry(self, path, stage, **kwargs):
        for attempt in range(self.config.max_retries + 1):
            try:
                return self._request(path, stage, **kwargs)
            except (JMTransportError, TaskTimeoutError):
                if attempt == self.config.max_retries:
                    raise
                logger.debug("JMComic %s网络异常，准备重试 %d/%d", stage, attempt + 1, self.config.max_retries)

    def get_daily(self):
        if self.uid is None:
            raise JMProtocolError("必须先完成登录")
        return self._read_with_retry("/daily", "查询签到", params={"user_id": self.uid})

    def submit_checkin(self, daily_id):
        """单次提交；重复签到响应统一映射为 SKIPPED。"""
        if self.uid is None:
            raise JMProtocolError("必须先完成登录")
        try:
            result = self._request("/daily_chk", "签到", data={
                "user_id": self.uid, "daily_id": positive_id(daily_id, "daily_id"),
            })
        except BusinessRejected as exc:
            if exc.already_signed:
                return TaskStatus.SKIPPED
            raise
        return checkin_status(result)

    def check_in(self) -> TaskStatus:
        if self.uid is None:
            raise JMProtocolError("必须先完成登录")
        daily = self.get_daily()
        if signed_today(daily, self.today().day):
            logger.debug("JMComic 今日状态：已签到，不提交签到请求")
            return TaskStatus.SKIPPED
        logger.debug("JMComic 今日状态：未签到，准备提交一次签到请求")
        daily_id = positive_id(daily.get("daily_id"), "daily_id")
        for attempt in range(self.config.max_retries + 1):
            try:
                return self.submit_checkin(daily_id)
            except BusinessRejected as rejected:
                if attempt:
                    # 前一次可能已落库；重试被拒绝时以服务端当前状态再次核验。
                    daily = self.get_daily()
                    if signed_today(daily, self.today().day):
                        return TaskStatus.SKIPPED
                raise rejected
            except (JMTransportError, TaskTimeoutError) as uncertain:
                logger.debug("JMComic 提交结果不确定，先查询服务端今日状态")
                try:
                    daily = self.get_daily()
                    if signed_today(daily, self.today().day):
                        return TaskStatus.SKIPPED
                except (JMTransportError, TaskTimeoutError, JMProtocolError, BusinessRejected):
                    raise uncertain from None
                if attempt == self.config.max_retries:
                    raise
                daily_id = positive_id(daily.get("daily_id"), "daily_id")
                logger.debug("JMComic 确认尚未签到，准备重试提交 %d/%d", attempt + 1, self.config.max_retries)
