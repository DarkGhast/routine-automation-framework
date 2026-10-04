"""手动真实联调入口：文件仅是测试输入，不是正式插件配置。"""

import argparse
import json
from pathlib import Path

from configuration.model import ApplicationConfig
from core.exception import TaskTimeoutError
from tasks.registry import create_tasks


def run(credentials: Path) -> dict:
    try:
        with credentials.open("r", encoding="utf-8-sig") as stream:
            text = stream.read(65537)
        if len(text) > 65536:
            raise ValueError
        raw = json.loads(text)
        if not isinstance(raw, dict) or set(raw) != {"username", "password"}:
            raise ValueError
        tasks = create_tasks(ApplicationConfig.model_validate({"tasks": {
            "picacg_live_test": {"type": "picacg", "config": raw},
        }}))
    except Exception:
        return {"status": "CONFIG_ERROR", "message": "测试凭据读取或校验失败，原始内容已隐藏"}
    try:
        result = tasks[0].execute()
        return {"status": result.status.value, "message": result.message}
    except TaskTimeoutError:
        return {"status": "TIMEOUT", "message": "请求超时"}
    except Exception:
        return {"status": "ERROR", "message": "联调异常，原始信息已隐藏"}


def main():
    parser = argparse.ArgumentParser(description="哔咔真实联调：登录、查询、未签到时提交一次")
    parser.add_argument("--credentials", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.credentials)
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["status"] in ("SUCCESS", "SKIPPED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
