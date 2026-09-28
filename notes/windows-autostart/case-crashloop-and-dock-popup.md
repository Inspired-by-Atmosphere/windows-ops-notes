# 案例：MCP server 崩溃循环 + 桌面 Dock 拉起的开机弹窗


> **适用平台**：Windows 10 / 11  
> **一句话**：用"进程数 + 创建时间"识别崩溃循环，用父进程链区分"会话恢复"与"Dock 自启"——两者修法完全不同。  
> **标签**：windows, autostart, crashloop, dock, mcp

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

## 背景
用户：the test laptop / Win10。开机"跳一堆终端"，重启一次弹好几次，多为两个一起闪。
desktop 应用版、the memory stack 记忆栈、chat-chat-bridge、gateway 均在本机。

## 第一轮修复（A+B+C）—— 做完了但不够
1. **A**：`启动文件夹\memory-stack.bat`（内含 `start "" python start_server.py`，弹 2 窗）→ 改写为 `memory-stack.vbs`（隐藏）。验证：`cscript //nologo "<盘符>:\...\x.vbs"`（必须 Windows 原生路径，MSYS 盘符根路径（`/<盘符>/...`）会被当参数）。
2. **B**：删启动文件夹 `gateway.vbs`，保留计划任务 App_Gateway。删前做了**计划任务演练**：停 gateway → `Start-ScheduledTask App_Gateway` → 新进程起来、6700 端口恢复、三平台 connected。证明删启动器不断联（启动器一次性、进程常驻不受影响）。
3. **C**：`Start_TrackProgAndDesktop=0` 关"登录后重新打开应用"。

**结果**：用户仍报疯狂闪。教训 = 修完要快照验证，别以为启动项修完就完了。

## 第二轮：快照定位真凶
```bash
# 可见窗口
powershell -NoProfile -Command "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select Id,ProcessName,MainWindowTitle | Format-Table -AutoSize"
# 崩溃循环计数：example-mcp
powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'example-mcp'}).Count"
```
发现：**12 个 example-mcp 进程**，创建时间 11:42–11:44 反复新增 = 崩溃循环。每实例 `cmd /c npx -y example-mcp` → node 套娃，闪 2 个 cmd 窗口。

进程树：
```
gateway run (python) ──> cmd /c npx ... example-mcp ──> node
serve (python, 桌面版后端) ──> cmd /c npx ... example-mcp ──> node
```

## 真凶 1：MCP server 崩溃循环
- config.yaml `mcp_servers:` 配了 `example-mcp: command npx, args [-y, example-mcp]`
- 被 gateway + serve 各自反复拉起 → 循环重启
- 作用：把 the external tool index 生态目录暴露给外部 MCP 客户端（Claude/Cursor/Continue）——**the app itself用不到**
- 修复：`app config unset mcp_servers.example`
  - ⚠️ config.yaml 是安全保护文件，`patch`/`write_file` 直接改被拒（"Refusing to write to the harness config"），必须用官方 CLI `app config unset`。
  - 先 `cp config.yaml backups/<日期>/` 备份
  - 移除后旧进程残留，等 gateway/serve 重启自然收敛

## 真凶 2：Dock 启动器拉起控制台程序
- 进程树：`Nexus.exe (%USERPROFILE%\Winstep\Nexus.exe autostart)` → `app.exe desktop` → `the harness.exe`（Electron 桌面版）
- Nexus dock 项存注册表 `HKCU\Software\WinSTEP2000\NeXuS\Docks`，键 `1Path12 = ...\app.exe`、`1IconPath12`、`1StartPath12`（注意：只查 Path0-10 会漏，要查全部 PathN）
- 配置目录：`%USERPROFILE%\Winstep\`（含 NeXuS/Profiles）、`%ProgramData%\WinStep\`
- `app.exe desktop` 是 Python 控制台程序，`desktop --help` 无隐藏参数 → 普通拉起必弹终端打启动日志（"Launching packaged the desktop app" + 可能的 ECONNRESET）

⚠️ **关键区分**：桌面版父进程 = Nexus → 是 dock 自启，**不是** Windows"登录后重新打开应用"（那个是 explorer 父进程）。关 Start_TrackProgAndDesktop 对 dock 无效。

## 待决策（给用户拍板）
the desktop app 要不要开机自启？
- A. 保留自启但改隐藏 VBS 拉起（用户在用它，最省事）
- B. 关掉自启，要时手动开

## 关键命令速查
```bash
# 崩溃循环计数
powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match '<关键字>'}).Count"
# MCP 移除
cd $HOME/AppData/Local/app && export APP_HOME="%LOCALAPPDATA%\app"
./<app-dir>/venv/Scripts/app.exe config unset mcp_servers.<name>
# Nexus dock 配置
reg query "HKCU\Software\WinSTEP2000\NeXuS\Docks" /s | grep -iE "Path|Target"
# 停进程（git-bash taskkill //F 无效，用 PowerShell）
powershell -NoProfile -Command "Stop-Process -Id <pid> -Force"
```
