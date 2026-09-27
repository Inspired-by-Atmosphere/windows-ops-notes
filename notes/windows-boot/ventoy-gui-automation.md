# Ventoy2Disk GUI 自动化（Windows）失败模式与可靠顺序


> **适用平台**：Windows 10 / 11  
> **一句话**：前台锁 + 全屏遮挡让物理点击落空；置前 + 坐标点击能通，但用户在场时直接让用户点最省事。  
> **标签**：windows, ventoy, gui-automation, foreground-lock

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

目标：无人值守让 Ventoy2Disk.exe 完成安装（点"安装"按钮 + 可能出现的确认框）。

## 失败模式（全部实测踩过）
1. **命令行参数不触发**：`Ventoy2Disk.exe /I /S /DRIVE=2` 只打开 GUI 停在"准备就绪"，不自动安装。必须点"安装"按钮。
2. **窗口被其他全屏应用盖住**（本机 = the desktop app 全屏）：物理鼠标点击落到盖住它的窗口上，Ventoy 收不到点击。SetForegroundWindow 因 Windows 前台锁返回 False。解法：ShowWindow(SW_RESTORE=9) + SetWindowPos(HWND_TOPMOST, 0x0001|0x0002) 置前，或直接让用户手动点。
3. **DPI 缩放坐标错位**：本机 3200x2000 @ 200%（LOGPIXELSX=192，Ventoy 是 DPI-unaware），UIA BoundingRectangle 数值 = 物理坐标 × 2，直接 SetCursorPos 会点到屏幕外。解法：**scale = GetWindowRect 物理宽 / UIA 根元素 BoundingRect 宽**（本例 454/908=0.5），物理坐标 = UIA 中心 × scale。
4. **PowerShell 5.1 中文编码**：读无 BOM UTF-8 .ps1 按 GBK 解码，中文字面量（'安装'）变乱码 → UIA PropertyCondition/匹配失败（而 TrueCondition 枚举+输出正常，因为输出不走字面量比较）。解法：脚本全 ASCII，中文用 Unicode 码点拼接：安装=0x5B89+0x88C5，确定=0x786E+0x5B9A，是=0x662F。
5. **Ventoy 控件是 Pane 不是 Button**：InvokePattern 不可用（TryGetCurrentPattern 失败），LegacyIAccessiblePattern 在 PowerShell 里可能类型加载失败 → 只能物理坐标点击（SetCursorPos + mouse_event LEFTDOWN=0x0002 / LEFTUP=0x0004）。
6. **"安装"按钮可能 disabled**：设备内已有 Ventoy 时只剩"升级"可用。用 UIA `$e.Current.IsEnabled` 检查再决定点哪个（本例安装 Enabled=True，升级=False）。

## 可靠顺序（最终走通：窗口置前 + 修正坐标点击；**兜底 = 让用户手动点，用户在场时直接走这条**）
1. `powershell Start-Process Ventoy2Disk.exe -ArgumentList '/I','/S','/DRIVE=2' -Verb RunAs`（弹 UAC，用户点是）
2. sleep 4 → Get-Process 拿 MainWindowHandle（刚启动时 UIA 树可能未就绪，重试）
3. 窗口置前：ShowWindow(9) + SetWindowPos(hwnd, -1, 0,0,0,0, 0x0001-bor-0x0002) + SetForegroundWindow
4. GetWindowRect 物理宽 ÷ UIA 根宽 → scale；目标控件中心 UIA 坐标 × scale → 物理坐标
5. SetCursorPos + mouse_event 点击；sleep 3 后 Dump-UI 验证状态变化
6. 出现确认框（确定/是）同样坐标点击
7. 失败兜底：**让用户手动点"安装"**（最快最稳）

## 关键代码模式（PowerShell，全 ASCII）
```powershell
Add-Type -AssemblyName UIAutomationClient; Add-Type -AssemblyName UIAutomationTypes
# 窗口物理矩形
Add-Type 'using System; using System.Runtime.InteropServices; public class W { [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r); [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L,T,R,B; } }'
# 中文匹配用码点：$name = -join ([char]0x5B89,[char]0x88C5)
# 枚举：$root.FindAll([TreeScope]::Descendants, [Condition]::TrueCondition)，比对 $e.Current.Name
# 物理点击：SetCursorPos(cx,cy); mouse_event(0x0002,...); mouse_event(0x0004,...)
```

## 诊断技巧
- 屏幕被盖/状态不明时：PowerShell 截全屏 `CopyFromScreen` 存 PNG → vision_analyze 看图判断窗口是否在前台、弹了什么
- 探针：tasklist /v 看窗口标题；UIA 枚举 IsEnabled/Rect/AutomationId/HelpText 判断按钮可用性
