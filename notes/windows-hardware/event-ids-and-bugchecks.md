# Windows 事件 ID 与 Bugcheck 码速查（显卡/eGPU 排障向）


> **适用平台**：Windows 10 / 11  
> **一句话**：一张表把 System 日志里跟显卡、电源、驱动相关的常见事件 ID 和停止码对上语义。  
> **标签**：windows, event-log, bugcheck, minidump

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

## 事件日志语义（System 日志）

| Provider / Id | 含义 | 排障价值 |
|---|---|---|
| Kernel-Power 41 | 启动时记录"上次关机异常" | 时间戳=本次启动；异常发生在**启动前**。Properties 顺序：BugcheckCode, Param1-4, SleepInProgress, PowerButtonTimestamp, BootAppStatus... PowerButtonTimestamp=0 → 硬断电/死机强关；非0 → 长按电源键（用户强关习惯=正常） |
| EventLog 6008 | "上一次系统的 HH:MM:SS 在 日期 上的关闭是意外的" | **精确锁定异常关机时刻**，和用户操作对表用 |
| nvlddmkm 13 | 显卡驱动停止响应已恢复（TDR） | 连续多条=驱动崩溃风暴；高负载/双卡/eGPU 场景常见 |
| nvlddmkm 14 | 驱动启动/恢复失败 | 严重，驱动状态坏 |
| nvlddmkm 153 | 驱动相关错误 | 辅助 |
| WER-SystemErrorReporting 1001 | 蓝屏记录，Message 含 Bugcheck 码 + dump 路径 | 蓝屏根因；旧记录会滚出日志 |
| Kernel-Boot 29 | "无法快速启动，错误状态 0xC00000D4" | 快速启动失败，常伴随 41，非主因 |
| Kernel-PnP 219 | 设备配置警告 | 插拔/驱动加载相关，参考 |
| Schannel 36871 | TLS 握手失败 | **Clash/TUN 代理环境噪音，与显卡无关，直接忽略** |

## Bugcheck 码速查

| 码 | 含义 | 典型触发 |
|---|---|---|
| 0x9F | DRIVER_POWER_STATE_FAILURE | 设备电源状态转换失败（睡眠/唤醒/插拔） |
| 0x19C | WIN32K_POWER_WATCHDOG_TIMEOUT | 电源看门狗超时，系统挂起 |
| 0x116 | VIDEO_TDR_FAILURE | 显卡驱动 TDR 崩溃（高负载/双卡） |
| 0x124 | WHEA_UNCORRECTABLE_ERROR | 硬件错误（过热/供电） |

组合诊断：驱动 TDR 风暴 + 0x9F/0x19C → "显卡驱动 × 电源管理"组合问题，长时间高负载暴露。

## minidump 访问

- `<盘符>:\Windows\Minidump\*.dmp` 普通用户**无读权限**（Permission denied）——别反复试
- 蓝屏码优先从 1001 事件拿；日志滚出后无解（除非提权）

## 本机案例档案

- 机型 the test laptop = the test laptop（RTX 5060 版），Win11 26200
- CPU Ultra 7 255H（16C16T）· 内存 2×16G 三星 DDR5-5600 · 电池 L24X4PG7
- GPU：Arc 140T 核显（内屏 3200×2000）+ RTX 5060 Laptop 8G（bus 01:00.0，SUBSYS 17AA）+ **技嘉魔改 RTX 3070 16G**（DEV_2484，SUBSYS 1458，bus 0F:00.0）
- 坞：天钡 AOOSTAR AG02（雷电4+OCuLink 双口，内置 ASM2464PD），3070 现走雷电4/USB4 口
- 驱动 595.79 / CUDA 13.2；3070 日期已脱敏 19:23 装好
- 3070 功耗墙默认 270W（魔改 BIOS 拉高），Max 2130MHz；**禁 -pl**，能效锁频 300-1650
- 排障结论：历史死机（4-6月 5 次蓝屏 + 6/27 九连 TDR）= 驱动×电源管理组合 bug，高负载触发；8/12、8/13 两次 Kernel-Power 41 = 热拔插雷电触发供电级断电 + 用户强关习惯；3070 装上后无死机
- 处置：CrashControl AutoReboot=1 + CrashDumpEnabled=3；桌面四件套脚本（断开/启用/能效/恢复）
