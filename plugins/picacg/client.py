"""签名参考 Jckling/Daily-Bonus（MIT），许可见 THIRD_PARTY_NOTICES。"""

import hashlib
import hmac
from http.client import HTTPException
import json
import socket
import ssl
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener, getproxies

from core.exception import TaskTimeoutError
from core.logging import get_logger
from core.result import TaskStatus

from .audit import response_shape


logger = get_logger(__name__)


BASE_URL = "https://picaapi.picacomic.com"
API_KEY = "C69BAF41DA5ABD1FFEDC6D2FEA56B"
API_SECRET = "~d}$Q7$eIni=V)9\\RK/P.RM4;9[7|@/CA}b~OW!3?EV`:<>M7pddUBL5n|0/*Cn"
ALLOWED_ROUTES = {("POST", "auth/sign-in"), ("GET", "users/profile"), ("POST", "users/punch-in")}
MAX_RESPONSE = 1024 * 1024
STATIC_HEADERS = {
    "accept": "application/vnd.picacomic.com.v1+json",
    "api-key": API_KEY, "app-build-version": "45", "app-channel": "3",
    "app-platform": "android", "app-version": "2.2.1.3.3.4", "app-uuid": "defaultUuid",
    "content-type": "application/json; charset=UTF-8", "image-quality": "original",
    "user-agent": "okhttp/3.8.1", "accept-encoding": "identity",
}


class BusinessRejected(Exception):
    def __init__(self, kind):
        self.kind = kind
        messages = {
            "SIGNATURE_ERROR": "服务端明确拒绝签名",
            "CREDENTIALS_ERROR": "服务端明确拒绝账号密码",
            "TOKEN_INVALID": "服务端明确表示 Token 无效或过期",
            "AUTH_REJECTED": "服务端拒绝认证，无法可靠区分具体原因",
            "BUSINESS_REJECTED": "服务端拒绝请求，业务原因尚未识别",
            "CHECKIN_REJECTED": "签到返回失败，查询也未确认今日已签到",
        }
        super().__init__(f"哔咔 {kind}：{messages[kind]}")


class ProtocolError(Exception):
    pass


class TransportError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def signed_headers(method, path, token=None, *, timestamp=None, nonce=None):
    timestamp = str(int(time.time())) if timestamp is None else str(timestamp)
    nonce = uuid.uuid4().hex if nonce is None else nonce
    raw = (path + timestamp + nonce + method + API_KEY).lower()
    signature = hmac.new(API_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    headers = {**STATIC_HEADERS, "time": timestamp, "nonce": nonce, "signature": signature}
    if token:
        headers["authorization"] = token
    return headers


def rejection_kind(obj, path):
    # 只识别明确文字，不把 HTTP 401/403 武断解释成密码或签名错误。
    markers = {obj.get(key, "").strip().lower() for key in ("error", "message", "detail") if isinstance(obj.get(key), str)}
    if markers & {"invalid signature", "signature invalid", "invalid_signature"}:
        return "SIGNATURE_ERROR"
    if path == "auth/sign-in" and markers & {"invalid email or password", "invalid credentials", "incorrect password", "invalid_credentials"}:
        return "CREDENTIALS_ERROR"
    if path == "users/profile" and markers & {"invalid token", "token expired", "jwt expired", "token invalid", "invalid_token", "token_expired"}:
        return "TOKEN_INVALID"
    return "AUTH_REJECTED" if obj.get("code") in (401, 403) else "BUSINESS_REJECTED"


def system_proxies(mode):
    """复用本机代理设置；仅支持标准库的 HTTP CONNECT，不记录代理地址或认证信息。"""
    if mode == "direct":
        return {}
    discovered = getproxies()
    address = discovered.get("https") or discovered.get("all")
    if not address:
        return {}
    try:
        address = address if "://" in address else "http://" + address
        parsed = urlsplit(address)
        if (parsed.scheme != "http" or not parsed.hostname or parsed.port == 0
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or any(ch.isspace() or ord(ch) < 32 for ch in address)):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("哔咔系统代理格式不支持：需要 HTTP CONNECT 代理，地址已隐藏") from None
    return {"https": address}


class PicACGClient:
    def __init__(self, config, audit, *, opener=None, sleep=time.sleep):
        self.config, self.audit, self.sleep = config, audit, sleep
        proxies = system_proxies(config.proxy_mode)
        # 系统代理仅建立 CONNECT 隧道，仍校验目标站点 TLS，不跨站点转发。
        self.opener = opener if opener is not None else build_opener(
            ProxyHandler(proxies), HTTPSHandler(context=ssl.create_default_context()), NoRedirect(),
        )
        self.audit.write("transport", proxy_mode=config.proxy_mode, proxy_configured=bool(proxies))
        logger.debug("PicACG 会话创建：proxy_mode=%s，代理已配置=%s，timeout=%s 秒，GET 额外重试=%d（不输出代理地址）",
                     config.proxy_mode, bool(proxies), config.timeout, config.max_retries)
        self._token = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._token = None
        logger.debug("PicACG 会话结束，已清除内存认证状态")

    def _request(self, method, path, payload=None):
        if (method, path) not in ALLOWED_ROUTES:
            raise ValueError("哔咔接口不在插件允许范围")
        attempts = 1 + (self.config.max_retries if method == "GET" else 0)
        for attempt in range(1, attempts + 1):
            headers = signed_headers(method, path, self._token)
            request = Request(BASE_URL + "/" + path, headers=headers, method=method,
                              data=json.dumps(payload).encode() if payload is not None else None)
            self.audit.write("request", method=method, path=path, origin=BASE_URL, attempt=attempt)
            started = time.monotonic()
            logger.debug("PicACG 请求开始：method=%s，path=%s，尝试=%d/%d", method, path, attempt, attempts)
            try:
                try:
                    response = self.opener.open(request, timeout=self.config.timeout)
                except HTTPError as exc:
                    response = exc
                with response:
                    status = response.code
                    raw = response.read(MAX_RESPONSE + 1)
                    # 内置处理器禁止跳转；再次检查最终地址，防止替换传输层绕过约束。
                    target_valid = response.geturl() == request.full_url
            except (URLError, OSError, HTTPException) as exc:
                reason = exc.reason if isinstance(exc, URLError) else exc
                timeout = isinstance(reason, (TimeoutError, socket.timeout))
                tls = isinstance(reason, ssl.SSLError)
                kind = "TIMEOUT" if timeout else "TLS_ERROR" if tls else "NETWORK_ERROR"
                logger.debug("PicACG 请求失败：path=%s，类别=%s，耗时=%.3f 秒", path, kind, time.monotonic() - started)
                self.audit.write("transport_error", path=path, attempt=attempt, kind=kind)
                if not tls and attempt < attempts:
                    logger.debug("PicACG 准备重试查询：path=%s，退避=%d 秒", path, min(2 ** (attempt - 1), 4))
                    self.sleep(min(2 ** (attempt - 1), 4))
                    continue
                error = TaskTimeoutError if timeout else TransportError
                raise error(f"哔咔 {kind}：请求未完成，原始异常已隐藏") from None
            try:
                obj = json.loads(raw) if len(raw) <= MAX_RESPONSE else None
            except (ValueError, UnicodeError, RecursionError):
                obj = None
            business_code = obj.get("code") if isinstance(obj, dict) else None
            logger.debug("PicACG 收到响应：path=%s，HTTP=%s，业务码=%s，字节数=%d，耗时=%.3f 秒",
                         path, status, business_code if type(business_code) is int else None,
                         len(raw), time.monotonic() - started)
            self.audit.write("response", path=path, attempt=attempt, http_status=status,
                             bytes=len(raw), oversized=len(raw) > MAX_RESPONSE,
                             target_valid=target_valid, body=response_shape(obj) if obj is not None else "<非JSON或超限，正文未保存>")
            if not target_valid or 300 <= status < 400:
                raise TransportError("哔咔 REDIRECT_BLOCKED：请求目标变化或重定向已拒绝")
            if status in (429, 500, 502, 503, 504):
                if attempt < attempts:
                    logger.debug("PicACG HTTP 暂时不可用，准备重试查询：path=%s，退避=%d 秒", path, min(2 ** (attempt - 1), 4))
                    self.sleep(min(2 ** (attempt - 1), 4))
                    continue
                raise TransportError(f"哔咔 HTTP_ERROR：HTTP {status}，未确认业务成功")
            if not isinstance(obj, dict) or type(obj.get("code")) is not int:
                raise ProtocolError("哔咔 UNKNOWN_RESPONSE：响应不是已知业务结构")
            if obj["code"] != 200:
                if not 400 <= obj["code"] < 600:
                    raise ProtocolError("哔咔 UNKNOWN_RESPONSE：未知业务码")
                kind = rejection_kind(obj, path)
                logger.debug("PicACG 业务拒绝：path=%s，类别=%s", path, kind)
                raise BusinessRejected(kind)
            if not 200 <= status < 300:
                raise ProtocolError("哔咔 UNKNOWN_RESPONSE：HTTP 状态与业务成功码冲突")
            if not isinstance(obj.get("data"), dict):
                raise ProtocolError("哔咔 UNKNOWN_RESPONSE：缺少业务数据")
            return obj["data"]

    def login(self, username, password):
        self._token = None
        data = self._request("POST", "auth/sign-in", {"email": username, "password": password})
        token = data.get("token")
        if not isinstance(token, str) or not token or len(token) > 16384 or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise ProtocolError("哔咔 UNKNOWN_RESPONSE：登录响应缺少有效 Token")
        self._token = token
        logger.debug("PicACG 登录响应已验证，Token 仅保留在内存")
        return token

    def get_profile(self):
        if self._token is None:
            raise ValueError("查询哔咔用户前必须先登录")
        try:
            data = self._request("GET", "users/profile")
            user = data.get("user")
            if not isinstance(user, dict) or not isinstance(user.get("_id"), str) or not user["_id"].strip():
                raise ProtocolError("哔咔 UNKNOWN_RESPONSE：缺少可识别的当前用户")
            return user
        except Exception:
            self._token = None
            raise

    def login_and_verify(self, username, password):
        self.login(username, password)
        return self.get_profile()

    @staticmethod
    def signed_today(profile):
        """使用服务端当日标志，不推测服务端时区或把缺失字段当成未签到。"""
        value = profile.get("isPunched")
        if type(value) is not bool:
            raise ProtocolError("哔咔 UNKNOWN_RESPONSE：缺少明确的今日签到状态")
        return value

    def submit_checkin(self):
        """单次提交并查询确认；也供显式授权的重复调用诊断使用。"""
        if self._token is None:
            raise ValueError("哔咔签到前必须先登录")
        try:
            data = self._request("POST", "users/punch-in")
            result = data.get("res")
            status = result.get("status") if isinstance(result, dict) else None
            if status not in ("ok", "fail"):
                raise ProtocolError("哔咔 UNKNOWN_RESPONSE：未知签到响应")
        except (TransportError, TaskTimeoutError, ProtocolError) as uncertain:
            # 提交可能已生效；只查状态，不重放 POST，避免消耗一次性机会。
            self.audit.write("checkin_uncertain", action="query_only_no_resubmit")
            logger.debug("PicACG 签到提交结果不确定，仅查询服务端状态，不重发提交")
            try:
                confirmed = self.signed_today(self.get_profile())
            except (TransportError, TaskTimeoutError, ProtocolError, BusinessRejected):
                raise uncertain from None
            self.audit.write("checkin_reconciled", isPunched=confirmed)
            logger.debug("PicACG 签到状态核对完成：isPunched=%s", confirmed)
            if confirmed:
                return TaskStatus.SUCCESS
            raise uncertain from None
        confirmed = self.signed_today(self.get_profile())
        self.audit.write("checkin_verified", response_status=status, isPunched=confirmed)
        logger.debug("PicACG 签到确认：提交状态=%s，isPunched=%s", status, confirmed)
        if not confirmed:
            if status == "fail":
                raise BusinessRejected("CHECKIN_REJECTED")
            raise ProtocolError("哔咔 UNKNOWN_RESPONSE：签到响应成功但用户状态未确认")
        return TaskStatus.SUCCESS if status == "ok" else TaskStatus.SKIPPED

    def check_in(self):
        """正常每日任务先查再提交，已签到时不重复调用写接口。"""
        if self.signed_today(self.get_profile()):
            logger.debug("PicACG 今日已签到，跳过提交")
            self.audit.write("checkin_skipped", reason="already_punched")
            return TaskStatus.SKIPPED
        logger.debug("PicACG 今日未签到，准备提交一次")
        return self.submit_checkin()
