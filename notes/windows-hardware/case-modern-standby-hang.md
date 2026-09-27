# 案例：合盖进现代待机后系统僵死（症状判读与取证顺序）


> **适用平台**：Windows 11（仅支持 S0 现代待机的机型）  
> **一句话**：服务 30 秒超时风暴 + Kernel-Power 41 的组合，是判断"整机僵死"而非"单纯重启"的指纹。  
> **标签**：windows, modern-standby, s0, kernel-power, hang

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

## 症状
合盖 → 锁屏 → 系统"特别特别卡" → 卡死 → 只能长按电源键强制关机 → 重启。

## 事件时间线（当天，System 日志）
| 时间 | 事件 ID | 含义 |
|------|---------|------|
| 17:56:28 | Kernel-Power **506** | 进入 S0 现代待机，**原因: Lid**（合盖触发点）|
| 17:56-17:57 | 506/507/566 | 待机反复切换（AC/DC、Austerity Battery Drain、INPUT_SUPPRESS=1 锁屏）|
| 17:57:00 | Kernel-Power 507 | 开盖退出待机 |
| 17:57:31 起 | SCM **7011/7009/7000** | **服务 30 秒超时风暴**（vendor PC-manager / function-key services 启动失败、vendor process manager、Camera Frame Server、vendor hotkey service、DCOM **10010** 注册超时）→ 系统已僵死的指纹 |
| 18:03:47 | DriverFrameworks-UserMode **10120（关键）** | 用户态驱动主机进程被终止 |
| 18:03:48 | DriverFrameworks-UserMode **10111（关键）** | **Goodix 指纹传感器驱动崩溃，设备离线**（卡死唤醒的肇事候选）|
| 18:08:47 | **Kernel-Power 41（关键）** | 强制重启 |
| 18:09:01 | EventLog **6008** | "上一次关闭是意外的"（精确异常关机时刻）|

## Kernel-Power 41 关键字段判读（本次）
- `BugcheckCode=0` → 无内核崩溃，**不是蓝屏**（硬冻结）
- `PowerButtonTimestamp≠0` → **长按电源键强制关机**（非硬断电）
- `ConnectedStandbyInProgress=true` + `CsEntryScenarioInstanceId=14` + `LidState=1` → **合盖现代待机中被强制关机**
- 开机时 `WHEABootErrorCount=0`、NTFS 卷全健康 → 非硬件故障

## 判别是不是 GPU 问题（WER 1001 LiveKernelEvent 解码）
- `P1=141` → **0x141 VIDEO_TDR_FAILURE（GPU 显示驱动超时）**
- `P3=0x10de` → 10DE = **NVIDIA 厂商 ID**（显卡驱动/GPU 相关）
- 本次当天无 P3=0x10de 的 141 → 纯冻结，与 GPU 无关（历史 08-18~08-20 的 0x50/0x3B/0x141 蓝屏是另一条 GPU 线）

## 根因
本机仅支持 **S0 现代待机**（`powercfg /a`：无 S3、休眠被禁）+ 高性能电源方案。合盖进 S0 待机时，**指纹驱动崩溃 + OEM 后台服务卡住** → 待机/唤醒流程挂死 → 整机冻结。

## 修复选项
- a) 电源选项把**合盖动作改为"不采取任何操作"**（绕开现代待机，适合外接屏/eGPU 当台式机用）→ 最直接
- b) 保留合盖睡眠 → 更新/重装 **Goodix 指纹驱动** + Intel/NVIDIA 显卡驱动

## 诊断脚本要点（本次用，PS 落盘到 ASCII 路径再 read_file）
- `Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=...}` 取 4 天错误/关键
- 单独拉 Kernel-Power 41 的 `ToXml()` 读 BugcheckCode/PowerButtonTimestamp/ConnectedStandbyInProgress
- WER 1001（Application 日志）拉 LiveKernelEvent/BlueScreen 签名
- 注意：**.ps1 里硬编码中文路径会乱码（GBK 读 UTF-8）→ 输出写到纯 ASCII 路径**
