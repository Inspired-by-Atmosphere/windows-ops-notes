

> **适用平台**：Windows 10 / 11（含 NVIDIA 显卡、现代待机机型）  
> **一句话**：先取证据链（事件日志 + WER + 进程父子链）再下结论；提权弹窗、WDDM 显存读数这类"看着像故障"的现象要先排除。  
> **标签**：windows, hardware, gpu, egpu, bugcheck, standby

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# Windows 硬件诊断：枚举 / GPU-eGPU 溯源 / 蓝屏与待机卡死 / 显存盘点

## 触发场景
- 遍历/枚举本机硬件（CPU/内存/GPU/存储/网络/声卡/电池/外设）
- GPU/eGPU 来历溯源（外接？什么坞？什么卡？何时装的？）
- 显卡不稳定：死机重启、蓝屏、掉卡、性能骤降
- 能效优化（降频找甜点）、eGPU 安全插拔脚本、死机留证配置

## 铁律（用户纠正过，先记住）
1. **查 GPU 显存必须查实数据**：`nvidia-smi --query-gpu=index,name,memory.total,memory.free,memory.used --format=csv`。禁止凭型号印象猜显存——用户 3070 是魔改 16G，凭"3070=8G"印象会误判（memory.used 是占用不是容量，别拿它当显存大小）。
2. **魔改显存卡（魔改16G 等）：严禁设功耗墙 `-pl`**——魔改显存吃功耗，限功耗→显存供电不足→掉卡。能效只能锁频 `-lgc`（如 `-lgc 300,1650`），功耗墙保持默认。
3. **eGPU 热拔插雷电口会触发供电级断电**（Kernel-Power 41、无蓝屏 dump）→ 插拔必须关机操作，或先 pnputil 禁用再拔。OCuLink 口严禁带电插拔。
4. **交付脚本/工具前必须实测验证**（用户"你都帮我干好"= 全部验证到位，不留作业给用户）。
5. **用户习惯强制关机**：系统日志的 Kernel-Power 41/EventLog 6008"意外关机"记录 = 用户长按电源键的正常痕迹，不是故障；用户陈述"正常"优先于日志推断，别误报异常。
6. **本机服务/目录归属判定（用户三次纠正：多次实测）**：涉及 agent 自家工作区目录（宿主应用的工作区/状态目录）一律视为 **agent harness 自家资产**，严禁归因于外部第三方系统。调查本机服务（Ollama/llama-server、your-service 等）先查证再下结论：父进程链（`Get-CimInstance Win32_Process` 的 ParentProcessId）+ 端口连接（`netstat -ano | grep 端口` → client PID → 命令行）→ 可能属同一 agent 的另一进程在用（实测确认：记忆栈 + Ollama 就是另一个 agent 进程在用）→ **勿停勿删**；报告只说事实，不说"谁在用"的猜测。

## 硬件枚举（PowerShell CIM，命令避免 $_）
- 整机/CPU/内存：`Get-CimInstance Win32_ComputerSystem,Win32_Processor,Win32_PhysicalMemory`
- GPU：`Get-CimInstance Win32_VideoController`（Name/PNPDeviceID/AdapterCompatibility/ConfigManagerErrorCode）
- 磁盘/卷：`Win32_DiskDrive` + `Win32_LogicalDisk -Filter 'DriveType=3'`
- 网卡/声卡/电池：`Win32_NetworkAdapter -Filter 'PhysicalAdapter=True'`、`Win32_SoundDevice`、`Win32_Battery`
- 显示器型号：`Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID`（字节数组转字符）
- 防乱码：每条命令前加 `[Console]::OutputEncoding=[Text.Encoding]::UTF8`

### git-bash 执行模式（关键坑）
- **bash 双引号内 `$_` 会被 MSYS 展开成工作目录路径** → PowerShell 脚本被破坏。解法：a) 命令内避免 `$_`（用 Format-List / CIM -Filter 代替 ForEach+$_）b) 转义 `\$_` c) 写 .ps1 文件，bash 里一行生成 base64 用 `-EncodedCommand`：`B64=$(python -c "import base64,sys; s=open(r'...ps1',encoding='utf-8').read(); sys.stdout.write(base64.b64encode(s.encode('utf-16-le')).decode())") && powershell.exe -NoProfile -EncodedCommand "$B64"`
- 审批差异：`powershell.exe -Command`（无 `$_` 的短命令）智能审批自动过；`-File` 会卡审批超时；`-EncodedCommand` 需用户批准
- 输出被 CLIXML 包裹（noisegate 省略）→ 加 `-OutputFormat Text`
- 提权操作（reg add / pnputil / nvidia-smi -pl|-lgc）两层弹窗：harness approval（smart 模式提权才弹，用户可设 off）+ Windows UAC（无法绕过，解释给用户时说明）

## GPU/eGPU 溯源
- nvidia-smi：`-L` 列卡；`--query-gpu=index,name,pci.bus_id,...` 看总线（内置独显 bus 01:00.0，eGPU 在 0F 等大号 bus）
- **SUBSYS 厂商解析**：实例 ID `PCI\VEN_10DE&DEV_XXXX&SUBSYS_YYYYZZZZ` 中 ZZZZ=子系统厂商（17AA=<laptop OEM>、1458=技嘉、1B21=ASMedia）——非本机厂商 ID = 外接件
- **setupapi.dev.log 的 Parent Device 是连接方式铁证**：`grep -i "DEV_XXXX" "<盘符>:\Windows\inf\setupapi.dev.log"`，附近 "Parent Device: PCI\VEN_1B21&DEV_2461" = ASM2464PD USB4/雷电 eGPU 坞（ADT-Link UT3G、天钡 AG02 类）；"Boot Session" + "Device Install" 段 = 安装时刻；"Needs Reinstall" 旧实例 = 换过接口
- 当前走哪条路：`Get-CimInstance Win32_PnPEntity -Filter "DeviceID LIKE 'USB4%'"` 有 USB4 路由器 = 走雷电/USB4 口

## 死机/重启/蓝屏排查
- **Kernel-Power 41**：系统**启动时**记录"上次关机异常"——时间戳=本次启动，异常发生在启动前。Properties 顺序：BugcheckCode, Param1-4, SleepInProgress, PowerButtonTimestamp, BootAppStatus,... → PowerButtonTimestamp=0=硬断电/死机强关，非0=长按电源键
- **EventLog 6008**：Message 直接给"上一次系统的 HH:MM:SS 在 日期 上的关闭是意外的"——精确锁定异常关机时刻
- **nvlddmkm**：Id 13=驱动停止响应已恢复（TDR 崩溃），Id 14=驱动启动/恢复失败，连续多条=崩溃风暴
- **Bugcheck 蓝屏码**：读 WER-SystemErrorReporting 1001 事件（旧记录会滚出日志）；minidump 文件普通用户无读权限（Permission denied，别反复试）。常见码：0x9F 电源状态失败、0x19C 电源看门狗、0x116 显卡 TDR、0x124 WHEA
- **死机留证配置**（改系统设置先征得同意）：
  ```
  reg add HKLM\SYSTEM\CurrentControlSet\Control\CrashControl /v AutoReboot /t REG_DWORD /d 1 /f
  reg add HKLM\SYSTEM\CurrentControlSet\Control\CrashControl /v CrashDumpEnabled /t REG_DWORD /d 3 /f
  ```

## 休眠/睡眠卡死排查（现代待机 + eGPU 组合，日期已脱敏 实证）
- **症状**：休眠/睡眠后卡死，只能长按电源键。事件签名 = Kernel-Power 41 且 **BugcheckCode=0**（硬冻结，无蓝屏无 dump）+ 每 2-5 天一次
- **先看睡眠状态**：`powercfg /a`（GBK 输出 `| iconv -f GBK -t UTF-8`）——S0 现代待机、无 S3（固件不支持）= 笔记本常态；S0/S4 切换 + eGPU（雷电坞） = 经典卡死源
- **佐证**：Id 42（进入睡眠）/107（已恢复）/506（进入低功耗）时间戳对照；无 minidump = 纯冻结
- **修复路径**：a) 简单=关休眠 `powercfg /h off`（提权执行；同时关快速启动、删 hiberfil.sys 释放 ~13G；S0 睡眠不受影响）b) 复杂=升 TBT 固件/换驱动（魔改卡慎动）——用户认可"不好修就关"时直接走 a
- **验证**：`powercfg /a` 显示"休眠不可用"、hiberfil.sys 消失、df 确认空间；恢复命令 `powercfg /h on`（提权）
- 提权执行（UAC 需用户点确认）：`powershell Start-Process cmd -Verb RunAs -Wait -ArgumentList '/c','<脚本.cmd>'`；harness approval超时会拦截，重试前先问用户

## 内存占用盘点（遍历内存/谁占内存）
- 全量脚本：`../scripts/memcheck.py`（OS 总览/commit 率/内存类型分解/进程 Top25/按应用聚合/分页文件/nvidia-smi+GPU 占用进程/压力速判），输出 GBK 乱码时 `PYTHONIOENCODING=utf-8 python ... > log` 落盘再读（防 noisegate 折叠）
- **关键指标**：commit 率（已提交/上限，>90%=真压力，再开大程序会 OOM）；standby 缓存计入 available（可用空间"水分"）；pagefile 峰值 vs 当前使用（实际在用就别建议缩）
- **GPU 占用进程**：`nvidia-smi --query-compute-apps=pid,process_name,used_memory`（WDDM 模式 used_memory 显示 [N/A] 属正常）；显存占满但 util 0% = 模型 keep_alive=Forever 常驻未推理（如 Ollama llama-server，内存私有提交可达 15G+）
- **服务归属判定**：谁在用某服务 = 查 client 进程（netstat 端口 → PID → 命令行/父进程）→ 见铁律 6

## eGPU 脚本模板（../scripts/gpu-power-mode/ 四件套）
- 断开显卡 / 启用显卡：`pnputil /disable-device|/enable-device "<实例ID>"`（实例 ID 硬编码，换口/重装驱动会失效→告知用户需更新）
- 能效模式：只 `nvidia-smi -i <idx> -lgc 300,1650`（**禁 -pl**）
- 恢复默认：`nvidia-smi -i <idx> -rgc`（+ 可选 -pl 恢复默认值）
- 模板要点：bat 内容全英文（避免 GBK/UTF-8 乱码），文件名可用中文；自提权段（net session 检测 + `powershell Start-Process '%~f0' -Verb RunAs`）；结尾 pause
- 交付前用等价命令实测整条链路（锁频→恢复→禁用→启用）再交给用户

## 参考
- `event-ids-and-bugchecks.md` — 事件 ID 语义、Bugcheck 码表、本机案例档案
- `../scripts/gpu-power-mode/*.bat` — eGPU 桌面四件套（断开/启用/能效/恢复）
- `../scripts/memcheck.py` — 内存占用全量盘点（日期已脱敏 实证）
