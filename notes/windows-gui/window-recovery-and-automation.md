

> **适用平台**：Windows 10 / 11（Tauri/Electron 桌面应用）  
> **一句话**：窗口"消失"多是 Tauri 应用窗口被隐藏或重建，按阶梯恢复；别把 GUI 重启当成服务重启。  
> **标签**：windows, gui, window-enum, tauri

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# Windows 桌面窗口丢失/枚举失败的排查与恢复

Windows 上用 `computer_use` 驱动桌面应用（Tauri/Electron/原生）时，窗口状态异常与 cua-driver 枚举失败的排查手册。适用于：点击后窗口消失、`list_windows` 找不到实际存在的窗口、`focus_app` 报 "No on-screen window found"、capture 报 "no on-screen window matched app=..."。

## 症状识别（本机实测，Clash Verge Rev）

1. 操作 Tauri 应用时窗口意外进入**损坏的最小化状态**：`GetWindowRect` 返回 `0,0 -> 13,13`（13×13 残影），或 AX bounds 全为 `-32000`（最小化特征坐标）。
2. cua-driver 的 `list_windows` 不再列出该窗口（app 元数据 `windows: []`），即使 PowerShell 确认窗口存在、`IsWindowVisible=True`、`IsIconic=False`。
3. `focus_app` 失败：`No on-screen window found for app 'X'`。
4. 窗口重启后，之前 capture 的元素索引全部失效：点击报 `Element N not in cache for hwnd=...`。

## 诊断（PowerShell，从 git-bash 调用）

```bash
powershell -NoProfile -Command "
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public class WR { [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L,T,R,B; } [DllImport(\"user32.dll\")] public static extern bool GetWindowRect(IntPtr h, out RECT r); [DllImport(\"user32.dll\")] public static extern bool IsIconic(IntPtr h); [DllImport(\"user32.dll\")] public static extern bool IsWindowVisible(IntPtr h); }';
\$p = Get-Process clash-verge;
\$h = \$p.MainWindowHandle;
\$r = New-Object WR+RECT;
[WR]::GetWindowRect(\$h, [ref]\$r) | Out-Null;
Write-Output ('hwnd=' + \$h + ' iconic=' + [WR]::IsIconic(\$h) + ' visible=' + [WR]::IsWindowVisible(\$h) + ' rect=' + \$r.L + ',' + \$r.T + ' -> ' + \$r.R + ',' + \$r.B);
"
```

## 恢复阶梯（按顺序尝试）

1. **SW_RESTORE**：`ShowWindow(h, 9)` —— 对真最小化有效，但对 13×13 残影无效（IsIconic 已为 False）。
2. **SetWindowPos 强制恢复尺寸**：`SetWindowPos(h, 0, x, y, w, h, 0x40)`（0x40=SWP_SHOWWINDOW），把窗口设回正常位置尺寸（如 1900×1420 @ (1200,260)）。窗口恢复显示，但 cua-driver 可能仍枚举不到（缓存未刷新）。
3. **重启 GUI 进程（最终方案）**：`Stop-Process -Id <pid> -Force; Start-Process -FilePath '<exe 全路径>'`。窗口重建后 cua-driver 重新枚举成功。**后台服务/内核不受影响**（如 Clash Verge 的 TUN + mihomo 服务独立运行，GUI 重启不断网）。
4. 重启后**必须重新 capture** 再点击——元素索引绑定旧 hwnd，直接点会报 "Element N not in cache"。

## 陷阱

- **git-bash 里 `taskkill //PID x //F` 会被转义成无效参数**（报"无效参数/选项"），用 PowerShell `Stop-Process -Id x -Force` 替代。
- cua-driver 的 `list_windows` 窗口 ID ≠ OS 窗口句柄（PowerShell 的 MainWindowHandle）。capture 用 `pid=` + `window_id=` 时 window_id 必须是 cua 枚举的 ID，不是 OS 句柄。
- Tauri webview 应用在 SOM 模式下可能只暴露少量 chrome 元素（标题栏/最小化等）；**切 `mode="ax"` 可拿到完整 UIA 树**（侧边栏导航按钮等全部可点）。
- `list_apps` 的 app 元数据会缓存旧窗口列表；重启进程后重新枚举即可。

## 与其他技能的关系

bundled `computer-use` 技能（不可编辑）覆盖通用 capture/click/升级阶梯；本技能补充其 Failure modes 表缺失的 Windows 窗口丢失/残影场景。若两者内容合并到同一 umbrella 更合适，交由 curator 处理。

## 参考文件

- `proxy-client-windows-notes.md` — 本机 Clash Verge Rev 完整使用指南 + 代理环境（fake-ip/TUN/7897 端口）知识库。遇到 fake-ip 引起的 SSRF 拦截、代理端口查询、Clash Verge UI 操作问题时先读它。
