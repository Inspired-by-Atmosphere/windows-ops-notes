

> **适用平台**：Windows 10 / 11  
> **一句话**：逐步可照抄的作业顺序：可见窗口对号 → 五处启动点枚举 → 进程树溯源 → 改动前演练备份通道 → 修复与回滚。  
> **标签**：windows, startup, popup, scheduled-task, logging

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# 开机弹窗排查与修复作业手册（含常驻弹窗日志守护）

## 触发场景
用户说"开机弹一堆终端/弹好几次"、"两个地方在拉同一个服务会不会断联"、"清理开机自启"。

## ⚡ 首选：常驻弹窗日志守护（日期已脱敏 新增，先于临时抓现行）
弹窗偶发时"临时盯 N 秒"经常抓不到。已建**常驻后台日志守护**，持续记录所有弹窗：
- 脚本：`%LOCALAPPDATA%\app\scripts\popup_logger.py`（跑在**专用 venv** 里，自身零窗口）
- 启动：`"%USERPROFILE%/popup-logger-venv/Scripts/pythonw.exe" popup_logger.py`（Startup\the harness_PopupLogger.vbs 拉起）
- **专用 venv（日期已脱敏 起）**：`uv venv %USERPROFILE%\popup-logger-venv --python 3.11` + `uv pip install --python ...\popup-logger-venv\Scripts\python.exe pywin32`。⚠️ 不要再去偷 the app runtime的 site-packages（旧 `<app-dir>env` 已随 PM 布局迁移失效，且新环境是 py3.14，与守护的 py3.11 解释器版本不匹配 → .pyd 必加载失败）
- 运行日志：同目录 `popup_logger_run.log`（超 8MB 自动裁到尾部 2MB；2026-09 实测曾无界涨到 94MB）
- 查看：`python popup_log_view.py`（人读版；`--tail N` / `--since HH:MM:SS` / `--all` 含 bash 噪音）
- 双通道：WMI `__InstanceCreationEvent WITHIN 1`（免管理员，~1s）+ EnumWindows 窗口轮询（0.5s，抓 CASCADIA_HOSTING_WINDOW_CLASS）
- 父链解析：后台每秒拉一次进程表 + WMI 事件历史双源，**零逐环 spawn**（避免自产弹窗噪音）
- ⚠️ 关键坑：守护 spawn 的任何子进程必须 `CREATE_NO_WINDOW`，且自产 PID 需过滤（`_self_pids`），否则日志全是自己的 powershell/conhost 噪音
- ⚠️ venv pythonw 曾是假 shim 会自弹（uv ≤0.12.7，PE `Console(3)`）→ 必须用 uv base 真 GUI pythonw + 手动挂 venv site-packages。**日期已脱敏 复核：uv 0.12.15 新建的 venv `Scripts\pythonw.exe` 已是 `GUI(2)`，可直接用**（一行判定：`python %WORKSPACE%\pe_subsystem.py <exe>`）；site-packages 手挂那套已废弃（还撞版本不匹配）
- ⚠️ 注意：WMI `Win32_ProcessStartTrace` 需要管理员会被拒，用 `__InstanceCreationEvent WITHIN 1` 免管理员
- ⚠️ 单实例保护：pywin32 `CreateMutex`+`GetLastError` 不可靠（GetLastError 会被 Python 内部调用清掉）；`os.kill(pid,0)` 在 Windows 也不可靠（signal 0 不被支持会误判进程死）。**用锁文件方案**：`os.open(lock, O_CREAT|O_EXCL)` 原子创建 + ctypes `OpenProcess` 检测持有者存活
- ⚠️ 守护自身跨天文件名必须按 `datetime.now()` 动态算（启动时固定文件名会跨天继续写旧文件）

## 🎯 实战案例 日期已脱敏：Ollama llama-server.exe 弹窗（"用 the harness 时闪弹窗"真凶）
- 症状：用户"使用 the harness 过程中老是闪弹窗但找不到源头"
- 排查：常驻守护日志（新机制）显示**所有**真实可见窗口事件都是
  `title='%USERPROFILE%\AppData\Local\Programs\Ollama\lib\ollama\llama-server.exe'`
  `class=CASCADIA_HOSTING_WINDOW_CLASS owner=WindowsTerminal.exe`，约每 40 分钟一次
- 根因链：the memory stack server（pythonw 无窗）→ 调用 Ollama 加载 9b 模型 → Ollama 拉起
  llama-server.exe（console 子系统）→ Win11 默认终端下**每次模型加载/重载都弹 Windows Terminal**
- 教训：conhost.exe 出现 ≠ 弹窗（隐藏进程也有 conhost）；**只有 CASCADIA_HOSTING_WINDOW_CLASS
  可见窗口才是真弹窗**。cron 的 conhost 是隐藏的（scheduler 已用 windows_hide_flags），
  但 cron 脚本**内部再 spawn 的子进程**不继承隐藏标志，是另一类嫌疑（本例实测 ingest_cron
  未弹窗，真凶是 Ollama）

## 排查四步（按序执行）

### 0. 先看"可见窗口"对号入座（最快定位）
用户说"弹终端"，先列出当前所有带标题的窗口 + 进程父子关系，直接对号：
```bash
# 所有可见窗口标题（识别是哪些程序在弹）
powershell -NoProfile -Command "Get-Process | Where-Object {\$_.MainWindowTitle -ne ''} | Select-Object Id,ProcessName,MainWindowTitle | Format-Table -AutoSize"
# 进程父子关系（谁拉起谁、是否套娃弹窗）
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine | Format-List"
```
**常见套路**：
- **多个 `cmd /c npx xxx-mcp` 套娃进程反复新建 = MCP server 崩溃循环**（见下方专项）
- **同一 WindowsTerminal 进程多个标签页** = 有东西用 `wt.exe`/COM 拉起了多个命令
- **应用父进程是 dock/启动器（如 Nexus.exe）** = 被第三方 dock 开机拉起

### 1. 枚举所有启动点（并行跑）
```bash
# ① 注册表 Run 键（HKCU + HKLM）
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" 2>/dev/null
reg query "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" 2>/dev/null
# ② 启动文件夹（用户 + 公共）
ls -la "$APPDATA/Microsoft/Windows/Start Menu/Programs/Startup"
ls -la "$ProgramData/Microsoft/Windows/Start Menu/Programs/Startup"
# ③ 计划任务（非禁用，含自定义任务）
powershell -NoProfile -Command "Get-ScheduledTask | Where-Object {\$_.State -ne 'Disabled'} | ForEach-Object { Write-Output (\$_.TaskPath + \$_.TaskName) }"
# ④ RunOnce / StartupApproved
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\RunOnce" 2>/dev/null
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run" 2>/dev/null
```

### 2. 识别弹窗元凶
| 类型 | 弹窗？ |
|---|---|
| `.bat` 批处理 | ✅ **必弹** cmd 窗口；内部 `start "" python x.py` 再弹 1 个新窗口 |
| `.vbs` 且 `Run "...", 0, False` | ❌ 隐藏（第 2 参数 0 = 隐藏窗口） |
| `.lnk` GUI 应用 | ❌ 各弹自己界面（非终端） |
| 计划任务 | 看执行器：`wscript //B`=隐藏；裸 `.cmd/.bat`=弹窗 |

### 3. 查进程树与"单实例"机制（判断重复启动会不会断联）
```bash
# 进程父子关系（谁拉起谁）
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object {\$_.Name -match 'cmd|python|node|app'} | Select-Object ProcessId,ParentProcessId,Name,CommandLine | Format-List"
# 单实例锁（gateway 例）
cat $HOME/AppData/Local/app/gateway.pid
# 服务监听端口（谁真在干活）
netstat -ano | grep ":<PORT>"
```

### 4. 关键：改动前先"计划任务演练"验证备份通道
删启动器前，必须实测"剩下的那条自启路能拉起服务"，否则可能真断联：
```bash
# ① 记录现状
cat gateway_state.json  # platforms 全 connected = 正常
# ② 停服务（用 PowerShell Stop-Process，git-bash 的 taskkill //F 会被转义报错！）
powershell -NoProfile -Command "Stop-Process -Id <PID> -Force"
# ③ 手动触发计划任务
powershell -NoProfile -Command "Start-ScheduledTask -TaskName 'App_Gateway'"
sleep 15   # gateway 启动需 ~15s（含 chat-bridge 反向 WS 连接）
# ④ 验证：端口 LISTENING + state 文件 platforms 全 connected
netstat -ano | grep ":6700"
cat gateway_state.json
```
**安全准则**：停服务会闪断消息通道 消息几秒，先跟用户确认时机再动手。

## 修复手段
1. **bat → vbs 隐藏启动**：照抄 `Run "cmd", 0, False` 模式
   ```vbs
   Set ws = CreateObject("Wscript.Shell")
   ws.CurrentDirectory = "<盘符>:\..."
   ws.Run """<盘符>:\path\to\python.exe"" ""<盘符>:\path\to\script.py""", 0, False
   ```
   校验：`cscript //nologo "<盘符>:\...\x.vbs"`（注意：**不能用 MSYS 盘符根路径（`/<盘符>/...`）**，cscript 会误当成参数）。
   ⚠️ **cscript 校验 VBS 会实际执行脚本**！若脚本会启动常驻程序，用 `wscript //nologo` 语法检查或接受它启动后自动退（多数程序检测已运行会退出）。不要用 cscript 校验含"启动服务"的 VBS 而误启一堆进程。
2. **去重复启动**：多启动点指向同一服务时，保留"带环境变量+可管理"的那个（计划任务优先），删启动文件夹裸启动器。
3. **桌面版/应用被"登录后重新打开"拉起**：这功能不在启动列表里，关它：
   ```bash
   reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" /v Start_TrackProgAndDesktop /t REG_DWORD /d 0 /f
   ```
   ⚠️ 影响：所有应用都不再自动恢复上次会话（浏览器/常用应用等）。
   ⚠️ **此功能对"第三方 dock 拉起"无效**——若应用是被 dock（如 Nexus/Winstep）拉起的，要改 dock 项，不是改这个注册表。
4. **应用被第三方 dock 开机拉起**：dock 项存在注册表（如 `HKCU\Software\WinSTEP2000\NeXuS\Docks`），项名如 `1Path12`/`1Arg12`/`1Label12`。移除该应用项的所有 `1*12` 键（用 `reg delete "..." /v 键名 /f`），dock 即不再开机拉起它。
5. **MCP server 崩溃循环弹窗**：the harness 的 `config.yaml` 里 `mcp_servers:` 段配置的 MCP server 若反复崩溃重启，每次走 `cmd /c npx xxx-mcp` 弹窗。用官方 CLI 移除（**不要直接改 config.yaml，patch 会拒绝对安全配置写入**）：
   ```bash
   export APP_HOME="%LOCALAPPDATA%\app"
   "./<app-dir>/venv/Scripts/app.exe" config unset "mcp_servers.<name>"
   ```
   ⚠️ **改 config 后必须重启 gateway/serve 才生效**——运行中的进程持有内存旧配置，还会继续拉 MCP server。重启 gateway（计划任务拉起）安全；重启 serve 会中断当前桌面会话。

## ⚠️ 核心坑：Windows 11 无法隐藏 console 子系统程序（ 实战验证）
- Windows 11 默认终端 = Windows Terminal（`设置>隐私和安全性>开发者选项>终端`）。当它开启时，**任何 console 子系统程序（python.exe、PyInstaller/console_script 打包的 exe）启动都会弹一个可见 WindowsTerminal 窗口**。
- **VBS 的 `Run "...", 0`（SW_HIDE）、`DETACHED_PROCESS`、`CREATE_NO_WINDOW` 对 console 程序在 Win11 下都无效**——窗口照样弹。这是之前"改了但没变化"的根本原因。
- **验证子系统**：`Get-CimInstance` 读 PE 头 Subsystem（3=Console 会弹窗，2=GUI 不弹）。

### 无窗启动的正确姿势（pythonw 大法）
- **GUI 启动器**：用 `pythonw.exe`（无控制台）运行一个 `.pyw`，内部 `subprocess.Popen([app.exe, "desktop"], creationflags=CREATE_NO_WINDOW)` → 无窗。
- **pip 的 console_script**（如 `your-service` = `xxx.module:main`）：不要跑 console 版 exe（会弹窗），改用 `pythonw -c "from xxx.module import main; main()"` 直接调模块入口 → 无窗。
- **但纯 PyInstaller 单文件 console exe（无 .py 模块入口）** 无法无窗——只能重打包成 GUI 子系统，或在应用内部改。
- **server 内部 spawn 的 python 子进程**（如 uvicorn worker，`sys.executable`）会继承/重建 console → 主进程 pythonw 了，子进程还是 python.exe 仍弹窗。这种"运行期常驻 1 个日志终端"属架构设计，若可接受就保留（单实例、不循环）。

### 单实例保护（防 0xc0000142）
- **0xc0000142（应用程序无法正常启动）= 重复启动时 DLL 初始化冲突**：开机自启 vbs + 快捷方式/登录恢复几乎同时各拉一次同一程序，第二个实例 python 初始化与已存在进程冲突失败 → 弹错。
- **修复**：启动器里加单实例检测（`(Get-Process -Name <App>).Count > 0` 则跳过），+ 所有入口（vbs/快捷方式）指向同一个带保护的启动器。实测第二次调用被正确拦截、不再弹 0xc0000142。
- ⚠️ 单实例检测用 PowerShell `Get-Process` 比 `tasklist` 可靠（中文系统 tasklist 输出编码可能 None）。

### ⚠️⚠️ uv 生成的 venv pythonw.exe 是"Console 假 shim"（日期已脱敏 实测铁证）
- **uv 创建的 venv（`Scripts\pythonw.exe` 约 45KB）PE 头标注 `Console(subsystem=3)`**，不是 GUI。它会 re-exec 回 uv base 目录里的 console 版 `python.exe` → **即使用了 pythonw + CREATE_NO_WINDOW 照样弹 WindowsTerminal**。这是"OV 弹窗已根治却仍弹"的根本原因。
- **判断方法（PE 头直接看，别猜）**：
  ```python
  import struct
  def subsys(p):
      d=open(p,'rb').read(); i=d.find(b'PE\x00\x00'); o=i+24
      return struct.unpack('<H',d[o+68:o+70])[0]  # 2=GUI无窗 3=Console弹窗
  ```
- **正确修法（日期已脱敏 实测生效）**：把 uv base 的真 GUI `pythonw.exe`（`%LOCALAPPDATA%\uv\python\cpython-3.11-...\pythonw.exe`，PE 头 `GUI(subsystem=2)`）**直接覆盖** venv 里的假 shim。Python 靠 `pyvenv.cfg` 判定前缀，真 pythonw 放 venv\Scripts 下仍自动识别 venv（site-packages + .pth 全部正常，包括 pywin32 的 pywintypes.dll 路径）。
  - ✅ 验证：覆盖后 `prefix` 仍指向 venv；`pythonw -c "import pywintypes,mcp,your_service_cli"` 全部 OK；启动服务后 conhost 数量零增长、WindowsTerminal 0 个。
  - ⚠️ 别用"base pythonw + sys.path.insert(venv site-packages)"替代方案 —— base 解释器**不执行 venv 的 .pth**，pywin32 等依赖 .pth 的包会 `ModuleNotFoundError`。
- **覆盖后所有指向该 venv pythonw 的入口自动无窗**（vbs / ctl / serve 插件 / 快捷方式），无需逐个改路径。

## 铁律
- **改任何启动项前先备份**到 `%LOCALAPPDATA%\app\backups\<日期>/`，报备份路径给用户。
- **taskkill 在 git-bash 里 `//F` 会报"无效参数"**，改用 PowerShell `Stop-Process -Force`。
- **cscript 校验 VBS 用 Windows 原生路径**，MSYS 盘符根路径（`/<盘符>/...`）会被当成命令行参数。
- 宣布完成前必须实测验证（计划任务演练 + 端口 + 服务状态三方核对），不许"应该没问题"。
- **杀 gateway/服务进程后可能断联**（消息转发中断）——立即用计划任务 `Start-ScheduledTask` 拉起并确认恢复（6700 端口 + state 文件 platforms 全 connected）。杀进程前先告知用户会有几秒闪断。
- **重启 gateway 前先确认对话走哪个进程**：桌面版对话走 `serve`，即时消息通道转发走 `gateway`。重启 gateway 只闪断消息通道；重启 serve 会中断当前桌面对话，慎做。
- **判断循环 vs 存量孤儿**：查进程 `CreationDate` 是否持续新增。持续新增=仍在循环重启（需重启父进程）；停更=残留孤儿进程（不再弹窗，下次重启自然消失）。
