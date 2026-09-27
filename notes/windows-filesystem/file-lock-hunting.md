

> **适用平台**：Windows 10 / 11，含云同步客户端常驻的场景  
> **一句话**：先分清"脚本/转换问题"还是"真被锁"，再用 Restart Manager 精确定位持有进程，确认无可见窗口后才安全结束。  
> **标签**：windows, file-lock, restart-manager, permission-denied

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# Windows 文件占用排查（File in use / Permission denied）

排查"文件被另一个程序占用导致无法删除/覆盖/写入"这一类问题：先分清是**转换/脚本问题**还是**文件被锁**，再用 Restart Manager 精确锁定持有进程，确认无可见窗口后才安全结束。本机（WPS + a cloud-sync client + 频繁 md→docx/pdf 交付重跑）日期已脱敏 实战沉淀。

## When to Use

文件删不掉/覆盖写不进（`Permission denied` / `[WinError 32]`）需要找出占用进程时；判定"转换失败"还是"文件被锁"时；本技能配套脚本 `../scripts/find_file_lock.py` 一键查持有者。

## 触发场景

- 重跑 md_convert.py / pandoc / 任何覆盖写文件时报 `Permission denied`、`withBinaryFile: permission denied`、`[WinError 32] 另一个程序正在使用此文件`
- 删不掉/改不了文件，想知道是谁占着
- 判据：wkhtmltopdf stderr 已出现 `Done` 但 pandoc 报写文件 permission denied → **输出文件被别的进程持有句柄，不是转换问题**（转换本身成功了）

## 常见持有者（本机实测）

| 持有者 | 特征 | 处理 |
|---|---|---|
| **wpspdf.exe（WPS PDF）** | 常驻后台进程，无可见窗口（MainWindowHandle=0）却持有最近打开过 PDF 的句柄；凌晨启动残留到白天 | 安全 `Stop-Process -Id <PID> -Force` |
| 云同步客户端（wpscloudsvr / a cloud-sync client / OneDrive） | 正在上传/校验的文件被锁定，常伴随进程常驻 | 等待同步完成或暂停同步 |
| 用户正打开的 PDF/文档阅读器 | 有可见窗口（MainWindowTitle 非空） | **不杀**，提示用户手动关闭 |

## 排查步骤

1. **精确找持有者**（不要靠猜/全量 tasklist）：
   `python <skill>/../scripts/find_file_lock.py '<Windows原生路径>'`
   → Restart Manager（Rstrtmgr.dll）查询，输出 PID + 进程名 + 类型
2. **确认无可见窗口再结束**：
   `powershell -NoProfile -Command "(Get-Process -Id <PID>).MainWindowHandle"`
   → 0：残留后台进程，`Stop-Process -Id <PID> -Force` 安全（不打断用户正在看的东西）
   → 非 0：用户正开着窗口，让用户手动关闭后再重试
3. **删除旧文件后重跑**：md_convert.py 幂等，重跑即覆盖旧版
4. Restart Manager 返回空但文件仍锁：持有者可能是系统服务或锁刚释放，等几秒重查

## Restart Manager API 坑位（脚本已封装）

- 签名：`RmGetList(h, &pnProcInfoNeeded, &pnProcInfo, rgAffectedApps, &lpdwRebootReasons)`
  - 参数2 = **输出**需要的进程数；参数3 = **in/out** 缓冲容量/实际数量
  - 第一次传空缓冲拿 needed；返回码 **234 (ERROR_MORE_DATA) 是正常信号**（需要更大缓冲），分配 `needed` 个元素后二次调用
  - 参数顺序写反会拿到 0 或空结果（本会话踩过）
- `strAppName` 是 `WCHAR[]`，直接 `print` 中文会撞 surrogate 编码错 → `p.strAppName.encode('utf-8','replace').decode('utf-8')`
- `RmRegisterResources` 传入路径用 `c_wchar_p` 数组 + `cast(..., POINTER(c_void_p))`

## 验证

- 脚本输出持有者 PID/进程名与 Restart Manager 一致
- 结束残留进程后旧文件可删除、重转成功
- 全程未结束任何有可见窗口的进程

## 相关

- 该坑常出现在 md→docx/pdf 交付重跑场景：a markdown-export workflow
- 中文路径/编码类 Windows 坑 → windows-cn-env-quirks（）
