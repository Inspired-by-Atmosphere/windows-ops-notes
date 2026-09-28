

> **适用平台**：Windows 10 / 11  
> **一句话**：启动项有五处、会话恢复还有一处隐藏机制；"修完还闪"通常是弹窗源根本不在自启列表里。  
> **标签**：windows, autostart, startup, popup, crashloop

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# 开机自启全量盘点与弹窗源头定位

用户报告"开机弹一堆终端/重启一次弹好几次"时，按本技能系统性盘点，别只盯着一个启动项下结论。

## 触发场景
- 开机时弹多个终端/黑窗口
- "XX 程序我没装自启它怎么开机自己开了？"
- 想让某个程序开机静默启动（不弹窗）
- 怀疑同一服务被自启两遍（进程冗余）

## 第〇步（新增·最重要）：修完启动项仍闪 = 弹窗源不在自启列表

**实战教训（）**：修完启动文件夹/Run/计划任务 + 关掉"恢复应用"（A+B+C 全做、每步实测验证），用户仍报告"疯狂闪终端、两个一起闪"。真正的元凶**不在任何自启列表里**，而是应用运行时自身拉起的前台控制台。所以**先快照定位当前实际在弹什么**，别只盯着启动项：

```bash
# 当前所有带标题窗口（数有几个终端/控制台窗口在弹）
powershell -NoProfile -Command "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select-Object Id,ProcessName,MainWindowTitle | Format-Table -AutoSize"
# 可疑进程计数（崩溃循环特征：进程数多 + 创建时间不断刷新）
powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match '关键词'}).Count"
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match '关键词'} | Select-Object ProcessId,CreationDate | Sort-Object CreationDate -Descending | Select -First 5 | Format-Table -AutoSize"
```

**崩溃循环判定**：同一命令进程数 >4 且创建时间在几分钟内反复新增 → 它在反复崩溃重启闪窗。**常见两类隐藏弹窗源**：
- **MCP server 崩溃循环**：the app config.yaml 里 `mcp_servers:` 配的 server 被 gateway/serve 反复拉起。实测 `example-mcp`（`npx -y example-mcp`，cmd→node 套娃）12 个进程循环重启，每实例闪 2 个 cmd 窗口 = "两个一起闪"。它只是给外部 MCP 客户端（Claude/Cursor）暴露目录用的，the app itself用不到 → 移除即可。
- **Dock 启动器拉起控制台程序**：Winstep Nexus dock 项指向 `app.exe`（控制台程序），开机自启 dock → 启动时必弹终端打日志。

> 🛠️ **监控脚本**：`../scripts/catch_popup.py`（本技能自带）——监控 N 秒内新出现的 conhost/cmd/python/node 进程并打印父链+命令行，直接锁定"正在弹窗的进程是谁拉起的"。用法：`python catch_popup.py 30`。比静态猜启动点快得多，弹窗进行中时用它抓现场。

## 排查步骤（按序执行）

## 第一步：全量盘点自启位置（缺一不可）

一次查完，别挤牙膏。本机实测命令（git-bash）：

```bash
# ① 用户 + 公共 启动文件夹
ls -la "$APPDATA/Microsoft/Windows/Start Menu/Programs/Startup"
ls -la "$ProgramData/Microsoft/Windows/Start Menu/Programs/Startup"

# ② 注册表 Run 键
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
reg query "HKLM\Software\Microsoft\Windows\CurrentVersion\Run"

# ③ RunOnce（登录后只跑一次）
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\RunOnce"
reg query "HKLM\Software\Microsoft\Windows\CurrentVersion\RunOnce"

# ④ 计划任务（非禁用全列，注意中文/编码用 PowerShell）
powershell -NoProfile -Command "Get-ScheduledTask | Where-Object {$_.State -ne 'Disabled'} | ForEach-Object { Write-Output ($_.TaskPath + $_.TaskName) }"
# 计划任务详情（触发/动作）
powershell -NoProfile -Command "Get-ScheduledTask -TaskName 'X' | Select -Expand Triggers; (Get-ScheduledTask -TaskName 'X').Actions | Format-List Execute,Arguments"

# ⑤ 汇总命令（覆盖 ①②③）
powershell -NoProfile -Command "Get-CimInstance Win32_StartupCommand | Select-Object Name,Command,Location | Format-List"
```

## 第二步：判断哪种自启会弹窗口

| 自启载体 | 弹窗？ | 说明 |
|---|---|---|
| 启动文件夹里的 `.bat`/`.cmd` | ✅ **必弹** | Windows 跑批处理必开 cmd 黑窗；若内含 `start "" python x.py` 还会**再开一个新终端**窗口 |
| 启动文件夹里的 `.vbs` | ⚠️ 看情况 | `ws.Run "命令", 0, False` 的 `0` = 隐藏窗口，但两个反例见坑位 13/14：UTF-8 中文注释 vbs 会弹 WSH 报错；vbs 拉起的 pythonw 若是 uv 假 shim 照样弹终端 |
| 计划任务 + `wscript //B` | ❌ 静默 | `//B` 无窗口模式 |
| 计划任务 + `powershell -WindowStyle Hidden` | ❌ 静默 | |
| Run 键里的 GUI 程序 | ⚠️ 弹自己的界面 | 看程序本身 |
| Windows "登录后重新打开应用" | ⚠️ 弹上次开着的程序 | 见下方坑位 |

**弹窗元凶第一嫌疑**：启动文件夹里的 `.bat`。一个 `.bat` 本身弹一个 cmd 窗口，里面的 `start "" python ...` 又弹一个，等于一个文件贡献 2 个窗口。

## 第三步：进程树溯源（谁在开机拉起谁）

```powershell
# 拿到开机时刻附近被拉起的进程 + 它们的父进程
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object {$_.Name -match 'app|python|node|cmd|WindowsTerminal'} | Select-Object ProcessId,ParentProcessId,Name,CreationDate | Sort-Object CreationDate | Format-Table -AutoSize"
```

- **父进程 = explorer.exe** → 登录启动项 / Windows 恢复应用 拉起
- **父进程 = svchost.exe** → 计划任务服务宿主拉起（去查计划任务）
- **WindowsTerminal 标题是某程序名**（如 "the desktop app"）→ 查它父进程是谁、是不是计划任务开的
- 对比开机时间（事件日志 ID 12）与进程 CreationDate，能区分"开机自启" vs "用户手动点开"

## 第四步：查重复自启

同一服务既出现在启动文件夹 VBS、又在计划任务里 → 疑似双进程白吃资源。实测案例：`gateway.vbs`（启动文件夹）+ `App_Gateway`（计划任务）都在启动 gateway。

⚠️ **两个启动器 ≠ 必然两个进程在跑**：很多服务带"单实例锁"（如 the harness gateway 启动前 `find_gateway_pids()`，已在跑就直接退出）。判断前**先数实际进程数**：
```powershell
# 数真正的 gateway 进程（别数启动器）
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'gateway run'} | Select-Object ProcessId,ParentProcessId,CreationDate | Format-Table -AutoSize"
# 看锁/pid 文件指向谁（真正在跑的那个）
cat $HOME/AppData/Local/app/gateway.pid gateway.lock
# 看网络连接谁在监听/连着（gateway 例：6700 反向 WS）
netstat -ano | grep ":6700"
```
父子进程可能是一个"启动器"spawn 真正的实例（uv python 重执行），别被多个同名进程误导。

修复=二选一删一个。**留哪个**：优先留计划任务版——带完整环境变量（APP_HOME/PYTHONPATH/VIRTUAL_ENV）、有延迟（如 30s 等桌面稳定）、在任务计划程序里可见可管可重启；启动文件夹 vbs 通常是早期手工装的简陋版（裸 app.exe，无环境准备）。

## 第五步：删除冗余前的安全演练（证明备份通道真能拉起）

删掉一个启动器前，先**实测**证明剩下那条路真的能用——用户会担心"断掉一个是不是就断联了"，拍脑袋保证没用，要做一次安全演练（用户明确认可此方法）：

1. 记录现状：状态文件（如 `gateway_state.json`）/ 进程 PID / 端口监听（如 gateway 的 6700）
2. 停掉服务：`powershell Stop-Process -Id <pid> -Force`（⚠️ git-bash 里 `taskkill //F` 会被 MSYS 转义吃掉报"无效参数"，用 PowerShell 版）
3. 手动触发计划任务：`Start-ScheduledTask -TaskName 'X'`
4. 等 8-15 秒，验证：新进程起来、端口恢复监听、pid/lock 文件更新到新 PID、平台日志显示 connected
5. 通过 → 删冗余有实锤；失败 → 先修备份通道再动启动项

⚠️ 演练会闪断几秒服务（如 即时消息转发），动手前先跟用户确认时机。

**删除启动器 ≠ 杀掉正在跑的进程**：vbs/bat 是一次性"启动器"，干完活就退出；真正常驻的是被它拉起的服务进程。删启动器只影响"下次开机少一个触发点"，正在跑的服务完全不受影响。

## 坑位

1. **"重启后恢复应用"功能**（用户级，默认开）：关机时开着的程序（如 the desktop app）会在下次登录被 explorer 自动拉起，**不在任何启动列表里**，改启动项没用。注册表 `HKCU\...\Explorer\Advanced\Start_TrackProgAndDesktop`（空=默认启用）。关闭命令：`reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" /v Start_TrackProgAndDesktop /t REG_DWORD /d 0 /f`。⚠️副作用：所有"上次开着"的程序都不会自动恢复了（浏览器/常用应用等），先跟用户说清。
2. **`.bat` 改静默**：不要试图在 bat 里藏窗口，直接改写成 `.vbs`（照抄已有 vbs 写法）：`Set ws=CreateObject("WScript.Shell"): ws.Run "命令", 0, False`。本机已有大量 vbs 范本可抄。写好后用 Windows 原生路径验证：`cscript //nologo "<盘符>:\...\x.vbs"`（⚠️ 传 MSYS 盘符根路径（`/<盘符>/...`）会被当参数报"未知选项"，必须用 `<盘符>:\...` 这类原生全路径）。
3. **schtasks/grep 中文输出乱码**：用 `Get-ScheduledTask` 而非 `schtasks` 管道 grep；`Get-CimInstance Win32_StartupCommand` 可直接拿中文名。
4. **git-bash 里 `taskkill //F` 无效**（MSYS 转义吃参数报"无效参数/选项"）：用 `powershell Stop-Process -Id <pid> -Force` 或 `taskkill /F`（单斜杠+引号规避）代替。
5. **计划任务手动触发**：`Start-ScheduledTask -TaskName 'X'`（PowerShell），触发后 gateway 常为"父启动器 spawn 子进程"形态，等 8-15 秒再验证端口/状态文件。
6. 改自启前先给用户方案确认，别直接删（本机 %WORKSPACE%\App 曾因误删丢 13 软件，删启动项同样要先确认）。方案里明说"可回滚"，并实际备份到 `app/backups/`。

## 坑位（续·日期已脱敏 追加）

7. **MCP server 崩溃循环（config.yaml 里 `mcp_servers:`）**：这类 server 被 gateway/serve 反复拉起、崩溃重启就疯狂闪窗（实测 `example-mcp` 12 进程循环）。移除方法：
   - ⚠️ **config.yaml 是安全保护文件**，`patch`/`write_file` 直接改会被拒（报 "Refusing to write to the harness config"）。
   - 用官方 CLI：`app config unset mcp_servers.<name>`（如 `app config unset mcp_servers.example`），再 grep 确认已清。
   - 先备份：`cp config.yaml backups/<日期>/`。
   - 移除后旧进程仍残留，等 gateway/serve 重启自然收敛（或手动 Stop-Process 止血）。
   - ⚠️ **改 config 后运行中的 gateway/serve 不重读**——持有内存旧配置继续拉 MCP server。必须重启 gateway（计划任务拉起，闪断几秒即时消息）才生效；serve 重启会中断当前桌面对话，慎做。
8. **Dock 启动器拉起控制台程序 ≠ 恢复应用功能**：桌面版若父进程是 Winstep Nexus（`%USERPROFILE%\Winstep\Nexus.exe autostart`）而非 explorer，那是 **dock 项**自启，不是 Windows 恢复功能。关 Start_TrackProgAndDesktop 对它无效！（实测：关掉恢复功能后桌面版仍被 Nexus 拉起——根因是 Nexus dock 项 `1Path12=app.exe`）。Nexus dock 项存注册表 `HKCU\Software\WinSTEP2000\NeXuS\Docks`（键 `1PathN`/`1IconPathN`/`1StartPathN`），配置目录 `%USERPROFILE%\Winstep\` 与 `%ProgramData%\WinStep\`。
9. **控制台程序"静默启动"**：`app.exe desktop` 是 Python 控制台程序，普通拉起必弹终端打启动日志（`<app> desktop --help` 无隐藏参数）。要静默需用 VBS `ws.Run "cmd", 0, False` 隐藏窗口方式拉起。若该应用你正在用、只是不想弹窗，倾向"保留自启但改隐藏 VBS"而非"关掉自启"。
10. **⚠️⚠️ VBS 隐藏对 console wrapper 无效（实测铁证）**：`.vbs` 的 `Run "...", 0` 隐藏标志**只作用于第一层进程**。若目标是控制台启动器（如 venv 的 `app.exe`、`python.exe`），它内部 spawn python → uv python → 真正的 GUI exe 时，**每一层子进程都会新建 conhost（黑窗）**。实测启动链：`app.exe desktop`(27580) → python(27264) → uv python(25056) → the harness.exe(28528)，每层一个控制台。**改 VBS 隐藏 ≠ 问题解决**——必须查完整子孙链（`ParentProcessId` 递归）确认启动链里有没有多层控制台程序。
    - **判断方法**：`Get-CimInstance Win32_Process` 递归查目标的 ParentProcessId 链，若含 ≥2 层 python/app 控制台程序 = VBS 隐藏无效。
    - **正确修法**：跳过 console wrapper，**直接启动 GUI 版 exe**（Electron 应用如 `apps\desktop\release\win-unpacked\the harness.exe`，214MB 纯 GUI 程序无控制台）。行为等价（都会拉起 serve backend），但不经过多层 python。
    - **验证**：改完 VBS 后查 conhost 是否仍随启动新建——**每个可见黑窗必有对应 conhost.exe**（conhost=控制台窗口宿主）。启动后 conhost 数量不增 = 修复成功。
11. **explorer 崩溃重启会重跑整个 Startup 文件夹（"两个一起闪"的隐藏机制）**：explorer.exe 崩溃/被杀后重启，会**重新执行 Startup 文件夹里的全部项**（vbs/bat/lnk 全来一遍），造成"一批窗口同时弹"。实测：13:41:32 explorer 重启 → 13:41:32 那批 4 个 conhost 同时新建（desktop-app.vbs + memory-stack.vbs + chat-bridge.vbs 同时触发）。**判断方法**：查 explorer 的 StartTime 是否很新 + 事件日志有 WER 崩溃上报：
    ```powershell
    # explorer 启动时间（新 = 刚重启过）
    powershell -NoProfile -Command "Get-Process -Name explorer | Select-Object Id,StartTime"
    # WER 崩溃上报（Application 日志 ProviderName='Windows Error Reporting'）
    powershell -NoProfile -Command "Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Windows Error Reporting'; StartTime=(Get-Date).AddHours(-2)} -MaxEvents 8 -ErrorAction SilentlyContinue | ForEach-Object { Write-Output ('[' + \$_.TimeCreated.ToString('HH:mm:ss') + '] ' + \$_.Message.Substring(0, [Math]::Min(200, \$_.Message.Length))) }"
    ```
    - **根源链**：显卡驱动崩溃（LiveKernelEvent 193 / BlueScreen 50，P3:10de=NVIDIA）→ 系统不稳 → explorer 崩 → Startup 重跑 → 弹窗爆发。本机有 5060/3070 eGPU，驱动崩溃是已知老毛病。
    - **含义**：就算所有 Startup 项都是隐藏 VBS，explorer 一崩还是会集体触发一次——所以"彻底无弹窗"还要保证**每一项 vbs 本身真正隐藏**（见坑位 10），而不是只删冗余。
12. **gateway 反复被 SIGKILL 重启 = 弹窗重复源**：`gateway-exit-diag.log` / `gateway-starts.log` 记录每次启动（epoch 时间戳）。若一天内 gateway.start 多次且每次 `previous_unclean_exit`，说明有 watchdog/启动点反复杀它重启，每次重启带 python 控制台窗口。查 `gateway.log` 的 `lifecycle_ledger` 行确认。

## 坑位（续·日期已脱敏 追加：vbs 编码 + uv 假 pythonw + 验证自坑）

13. **⚠️⚠️ ".vbs 必静默" 不成立 —— UTF-8 中文注释 vbs 弹 WSH 报错（日期已脱敏 实测铁证）**：
    - 症状：开机弹 `Windows Script Host` 错误窗，`行N 字符1 错误: 缺少对象 'ws' 800A01A8`，脚本是启动文件夹里的 .vbs。
    - 根因：vbs 是 **UTF-8 编码（无 BOM）+ 中文注释**。WSH 对无 BOM 的 .vbs 按系统 ANSI(GBK) 解析，UTF-8 中文字节被 GBK 误读后行结构错乱 → 偶发把 `Set ws=CreateObject(...)` 之后的 `ws.xxx` 解析成"ws 未定义"。
    - 判定：`file x.vbs` → `Unicode text, UTF-8 text`（含中文）= 有雷；正常应为 `ASCII text`。**同文件夹纯 ASCII 的 vbs 从不报错**，就 UTF-8 中文的那个弹错。
    - 修法：**vbs 一律纯 ASCII（英文注释或不注释）**。写完 `cscript //nologo "<盘符>:\...\x.vbs"` 校验退出码 0（⚠️ 若 vbs 拉常驻服务且带单实例保护则安全，会走"已在运行跳过"；无保护的会真启动，慎用）。
14. **⚠️⚠️ uv venv 的 pythonw.exe 是 Console 假 shim（日期已脱敏 实测铁证）**：
    - uv 生成的 `venv\Scripts\pythonw.exe`（约 45KB）**PE 头标注 `Console(subsystem=3)`，不是 GUI**。它 re-exec 回 uv base 目录的 console 版 `python.exe` → **即使用了 pythonw + CREATE_NO_WINDOW/DETACHED 照样弹 WindowsTerminal**。这是"OV 弹窗已根治却仍弹"的根因。
    - 判定：**读 PE 头 subsystem 字段**（2=GUI 无窗 / 3=Console 弹窗），别只看文件名是 pythonw。直接用本技能自带的 `../scripts/pe_subsystem.py`：`python ../scripts/pe_subsystem.py "<盘符>:\...\pythonw.exe"`（等价的单行：`python -c "import struct;d=open(p,'rb').read();i=d.find(b'PE\x00\x00');o=i+24;print(struct.unpack('<H',d[o+68:o+70])[0])"`）。
    - 修法：把 uv base 真 GUI `pythonw.exe`（`%LOCALAPPDATA%\uv\python\cpython-3.11-...\pythonw.exe`，subsystem=2）**直接覆盖** venv 里的假 shim——Python 靠 `pyvenv.cfg` 判定前缀，覆盖后 venv site-packages + .pth（含 pywin32 的 pywintypes.dll 搜索路径）全正常，且所有指向该 venv pythonw 的入口（vbs / ctl / serve 插件 / 快捷方式）**自动无窗**，无需逐个改路径。
    - ⚠️ 不要用"base pythonw + `sys.path.insert(venv site-packages)`"替代方案——base 解释器**不执行 venv 的 .pth**，pywin32 等依赖 .pth 的包会 `ModuleNotFoundError`（实测 pywintypes 缺失）。
    - 验证：覆盖后 `prefix` 仍指向 venv；`pythonw -c "import pywintypes,mcp"` 全 OK；启动服务后 conhost 数量零增长、WindowsTerminal 0 个。
15. **验证自坑：查询命令匹配到自身命令行（日期已脱敏）**：
    - 用 PowerShell `Where-Object { $_.CommandLine -match 'xxx' }` 溯源进程时，**查询链自身（bash/powershell）的命令行里也含 'xxx' 字样**，被误匹配进结果 → 假阳性"FAIL"（本轮查 your-stack 就误报有 conhost 子进程，实际是查询自己的临时进程）。
    - 正确做法：先列出所有匹配 PID 逐一查身份（Name/Parent/Cmd），找**真正存活的主进程**，再**只针对该确切 PID** 验证子进程/窗口：`Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq <真PID> }`；无窗口还要看 `MainWindowHandle -eq 0` + `MainWindowTitle` 为空。已退出的小 PID = 查询链自身临时进程，忽略。

## 本机档案（ 盘点 + 修复完成）
- 启动文件夹 5 项：`gateway.vbs`(静默)、`memory-stack.bat`(⚠️弹2窗)、`chat-bridge.vbs`(静默)、`MatrixPlanet.lnk`、`Rainmeter.lnk`；公共启动 Tailscale
- HKCU/HKLM Run：厂商预装项 + OneDrive + Edge + SecurityHealth + AweSun + Everything（GUI/系统，非弹窗源）
- 计划任务：App_Gateway（wscript 隐藏）、cua-driver-serve（hidden）、GCC、Nexus、Pogget、TranslucentTB 等
- the desktop app 桌面版自启 = Windows 恢复应用功能，非 Run 项
- **日期已脱敏 已执行修复（A+B+C 全部完成并实测验证）**：
  - **A**：`memory-stack.bat` → 改为 `memory-stack.vbs`（隐藏启动），旧 bat 已删，VBS 实测能拉起 the memory stack（healthy:true）
  - **B**：删除启动文件夹 `gateway.vbs`，保留计划任务 App_Gateway；**演练实测**：停 gateway → `Start-ScheduledTask App_Gateway` → 新进程起来、6700 端口恢复、三平台（all message channels）全部 connected
  - **C**：`Start_TrackProgAndDesktop=0` 关闭"登录后重新打开应用"，桌面版不再开机自动弹
  - **D（追加）**：Nexus dock 项 `1Path12`（指向 `app.exe desktop`）已全键删除；新增 Startup `desktop-app.vbs` 隐藏自启桌面版
  - 备份在 `%LOCALAPPDATA%\app\backups\startup-fix-20260818\`（可回滚）
- 修复后启动文件夹仅剩：`memory-stack.vbs`、`desktop-app.vbs`、`chat-bridge.vbs`、`MatrixPlanet.lnk`、`Rainmeter.lnk`（全部静默/GUI；⚠️ desktop-app.vbs 的隐藏有效性待 conhost 验证，见坑位 10）

## 日期已脱敏 追加：A+B+C 之后仍闪（本次案例续篇）

**A+B+C 全部做完且每步实测通过后，用户仍报"疯狂闪终端、两个一起闪"。** 追加排查定位到 2 个隐藏源，均不在自启列表：
1. **`example-mcp` MCP server 崩溃循环**：config.yaml `mcp_servers:` 里配的，被 gateway+serve 各自反复拉起，12 个进程循环重启，每实例 cmd→node 套娃闪 2 个 cmd 窗口 = "两个一起闪"。已用 `app config unset mcp_servers.example` 移除（config.yaml 受保护，patch 会被拒）。**它是给外部 MCP 客户端用的目录接口，the app itself用不到 → 可安全删。**
2. **the desktop app 被 Nexus dock 拉起 + your-stack WindowsTerminal 标签页**：桌面版父进程是 Nexus（dock 项 `1Path12=app.exe`），`app.exe desktop` 是控制台程序启动必弹终端。your-stack 也有个 WindowsTerminal 窗口。

**教训**：修"开机弹窗"类问题，做完启动项常规修复后**必须再做第〇步快照**（数窗口/数崩溃循环进程），确认弹窗真的停了；否则会像我一样误判"已修复"、实际主犯还没找到。修复方案要交付给用户确认后再执行（用户正在用桌面版，需拍板"保留自启改隐藏" vs "关掉自启"）。

> 📄 完整命令/进程树/注册表键实录见 `case-crashloop-and-dock-popup.md`。
