# Routine Automation Framework

用于执行多个网站/软件日常任务的轻量 Python 自动化框架。

## 当前状态

当前版本完成了框架基础能力：

- YAML 配置加载
- `${ENV}` / `${ENV:default}` 环境变量解析
- Pydantic 配置校验
- 显式 Task Registry
- Task 失败隔离
- 通知策略（`always` / `error_only`）
- Notification Channel Registry
- Console 通知渠道

真实业务任务（例如 JM）将在后续版本接入。

## 本地启动

1. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```

2. 复制示例配置：

   ```bash
   cp config/application-example.yaml config/application.yaml
   ```

   Windows PowerShell：

   ```powershell
   Copy-Item config/application-example.yaml config/application.yaml
   ```

3. 根据 `application.yaml` 中的注释设置所需环境变量。

4. 从项目目录运行：

   ```bash
   python -m app.main
   ```

`config/application.yaml` 已加入 `.gitignore`，不会作为正常源码提交。
