# Windows 11 默认终端 = Windows Terminal 时的弹窗定位法


> **适用平台**：Windows 11（默认终端应用 = Windows Terminal）  
> **一句话**：conhost 与 WindowsTerminal 两种承载方式决定了 SW_HIDE 有没有用；先看窗口标题再决定改哪一层。  
> **标签**：windows, windows-terminal, conhost, diagnostics

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

## 诊断命令（弹窗定位）
```bash
# 所有可见窗口标题（识别弹窗的是哪些程序）
powershell -NoProfile -Command "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select-Object Id,ProcessName,MainWindowTitle | Format-Table -AutoSize"

# 进程父子关系 + 完整命令行（看 console 包装链）
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine | Format-List"

# conhost 是否有可见主窗口（判断 console 是否真的弹窗）
powershell -NoProfile -Command "Get-Process -Name conhost -ErrorAction SilentlyContinue | Where-Object {$_.MainWindowHandle -ne 0} | Select-Object Id,MainWindowTitle"

# 单实例锁进程树确认
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'desktop'} | Select-Object ProcessId,ParentProcessId,Name | Format-Table -AutoSize"
```

## 关键判断特征
- 命令行出现 `-Embedding` 的 `WindowsTerminal.exe`/`OpenConsole.exe`（父进程常是 svchost/explorer）→ 被 Windows 默认终端机制承载。
- console 启动链：`cli.exe` → `python.exe` → `uv python` → `真程序.exe`，每层一个 conhost。
- 某条目 "explorer 重启" 会重跑 Startup 文件夹全部项 → 一次弹多个（explorer 崩溃后更明显）。

## 实战案例（ 本机）
症状：开机"疯狂跳一堆终端窗口"，本质是：
1. `app.exe desktop`（venv console 包装器）被 vbs 隐藏启动，但因默认终端=Windows Terminal，SW_HIDE 无效，仍弹 WindowsTerminal。
2. explorer 崩溃重启 → 重跑 Startup 全部 vbs（app-desktop + memory-stack + chat-bridge）→ 一次弹多个。
3. gateway 开机被多次 SIGKILL 重启（11:08→11:34→11:42→13:29→13:42），每次重启都走 python 控制台。

解法：VBS/快捷方式全部改指 pythonw + start_desktop_hidden.pyw（CREATE_NO_WINDOW），实测无任何新弹窗、重复启动因单实例锁安全退出。

## 血泪教训（危险操作）
- 点 WindowsTerminal 关闭按钮 = 杀死其中运行的 console 程序（app.exe desktop → the desktop app 本体被连带杀掉）。清弹窗必须改启动方式重启验证，**绝不**去关那个窗口。
