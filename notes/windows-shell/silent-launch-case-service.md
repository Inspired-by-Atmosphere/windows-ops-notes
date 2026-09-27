# 案例：被 uv 包装的服务反复弹窗的根治实录


> **适用平台**：Windows 10 / 11 + uv/pip 安装的 console_script 服务  
> **一句话**：双触发点竞速重启 + console 包装器逐层 re-exec，是"疯狂闪窗"的两层根因；改法必须两边都改。  
> **标签**：windows, console, uv, re-exec, race

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

## 症状
用户发现"running the app over scripts 目录（cron no_agent 脚本）就疯狂闪终端窗口"。
- 实际触发时刻：OV server 静默死亡（11:25，日志无 crash traceback，最后是 LiteLLM 429 重试），随后**两个独立触发点同时竞速重启**：
  1. the harness 插件 `plugins/memory/your-stack/__init__.py::_start_local_service`（health 预检失败即拉起，11:28:56）
  2. cron 崩溃守护 `service_guard.py`（每 2 分钟）→ `service_ctl.py start`（11:29:10）
- 每次拉起 `your-service.exe` 都弹窗 → 十几秒内两次拉起 = "疯狂闪"。

## 根因（两层）
1. **console_script launcher re-exec**：`your-service.exe` 是 uv 生成的 console 启动器，启动链 `your-service.exe → venv\Scripts\python.exe → uv base python.exe`，每层 re-exec 重建 console，父进程的 `CREATE_NO_WINDOW`/`DETACHED` 被逐层丢弃 → 必弹窗。
2. **双触发点竞态**：插件 auto-start 和 cron guard 是两个独立进程，彼此的防抖（guard 15s）管不住对方。
3. **引爆点**：被守护的 server 静默死亡（11:25 无痕消失，无 crash 日志，疑似 VLM 429 重试卡死/被强杀）。

## 修复（已验证）
统一改为 **pythonw + 模块入口（headless）**，两处改动：

1. `%LOCALAPPDATA%\app\scripts\service_ctl.py`
   `start_your-stack()`：弃用 `Popen([OV_SERVER])`（console exe），改为
   `Popen([pythonw.exe, start_your-stack_hidden.pyw], creationflags=DETACHED=0x8, ...)`。
   `start_your-stack_hidden.pyw` 内部已有：单实例保护（1933 health 探测）+ 清 PYTHONPATH + litellm local cost map + 
   `pythonw -c "from your_service_cli.server_bootstrap import main; main()"`。

2. `<app-dir>\plugins\memory\your-stack\__init__.py::_start_local_service`
   Windows 分支直接 `Popen([pythonw, "-c", <同款 code>], cwd="%USERPROFILE%\.your-stack", CREATE_NO_WINDOW, stdout→log)`；
   不再 `Popen([shutil.which("your-service"), "--host", ...])`。
   host/port 由 `ov.conf` 承载，`main()` 不读 `--host/--port`，无需透传。

备份：`%LOCALAPPDATA%\app\backups\ov-noconsole-20260819\`（两文件）。

## 验证证据（实测通过）
- `python -m py_compile` 两文件通过。
- pytest smoke（临时文件，测完已删，3 passed）：
  - ctl py_compile + import
  - `_start_local_service()` 可调用并返回 `(True, "...headless...")`
  - 当前进程链无 `your-service.exe`，含 `pythonw`（headless 入口在场）
- 活体回归：`ctl start` 与插件函数各实测一次 → `/health` ok，进程链均为 `pythonw→python`，全程无弹窗。
- `ctl status` 全绿（Ollama running / the memory stack running / provider=your-stack）。

## 遗留
- 插件改动需 **重启 the harness 才生效**（已加载的模块不热更新）；guard/ctl 路径实时生效。
- <app-dir> 更新/重装会**覆盖插件文件** → 需按本文件重打 `_start_local_service` 的 headless 分支。
- 当时旧 server 静默死亡原因未深挖（用户指示跳过限流议题）；若重启循环重现，先查 server 日志最后一刻。
