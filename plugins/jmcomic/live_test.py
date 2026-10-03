"""手动真实联调入口：只输出固定脱敏结论，不属于自动测试。"""

import argparse
import json
import logging
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


def run(credentials: Path) -> dict:
    # 这是独立联调进程的输出策略，不改变框架或插件的日志配置。
    previous_level = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink), redirect_stderr(sink):
            from core.exception import TaskTimeoutError
            from core.result import TaskStatus
            from plugins.jmcomic.client import JMProtocolError, JMTransportError
            from configuration.model import ApplicationConfig
            from tasks.registry import create_tasks

            try:
                # 限定为两个凭据字段；不输出原文及校验异常。
                raw = json.loads(credentials.read_text(encoding="utf-8-sig"))
                if not isinstance(raw, dict) or set(raw) != {"username", "password"}:
                    return {"status": "CONFIG_ERROR", "message": "凭据文件格式错误"}
                tasks = create_tasks(ApplicationConfig.model_validate({"tasks": {
                    "jm_live_test": {"type": "jmcomic", "config": raw},
                }}))
            except Exception:
                return {"status": "CONFIG_ERROR", "message": "凭据文件读取或配置校验失败"}
            try:
                result = tasks[0].execute()
            except TaskTimeoutError:
                return {"status": "TIMEOUT", "message": "请求超时"}
            except JMTransportError:
                return {"status": "NETWORK_ERROR", "message": "网络或 HTTP 请求失败"}
            except JMProtocolError:
                return {"status": "PROTOCOL_ERROR", "message": "接口响应不符合已知协议"}
            except Exception:
                return {"status": "ERROR", "message": "执行异常，原始信息已隐藏"}
            messages = {
                TaskStatus.SUCCESS: "登录成功，签到成功",
                TaskStatus.SKIPPED: "登录成功，今日已签到",
                TaskStatus.FAILED: "服务端拒绝请求，原始信息已隐藏",
            }
            return {"status": result.status.value, "message": messages[result.status]}
    except Exception:
        return {"status": "ERROR", "message": "联调初始化失败，原始信息已隐藏"}
    finally:
        logging.disable(previous_level)


def main():
    parser = argparse.ArgumentParser(description="JMComic 脱敏真实联调（会登录并按需签到）")
    parser.add_argument("--credentials", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.credentials)
    # ASCII JSON 避免 Windows 终端代码页导致中文乱码。
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["status"] in ("SUCCESS", "SKIPPED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
