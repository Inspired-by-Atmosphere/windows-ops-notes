

> **适用平台**：Windows 10 / 11（PowerShell 5.1+，含从 bash/MSYS 调用 PowerShell 的场景）  
> **一句话**：用 WMI/PnP 实例 ID + 安装史 + 父设备链，判断"这块卡是不是原装、到底接上了没有"。  
> **标签**：windows, hardware, wmi, pnp, device-enum

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# Windows 硬件枚举与设备来历调查

在 Windows（git-bash/MSYS 终端）上列出本机硬件全清单、或深挖某设备（显卡/网卡/存储）的来历、物理连接方式、驱动状态。

## 触发场景

- 用户说"历遍本机硬件设备""查设备清单""本机配置"
- 用户要深挖某个设备："这个显卡是怎么接的""什么时候装的""什么牌子""能不能用"
- 性能/算力评估前先摸清 GPU/内存/存储基线

## 核心纪律（先读，都是实测教训）

1. **命令必须轻量，用户对卡顿零容忍**。短 `powershell.exe -NoProfile -Command "..."` 走智能审批秒过；`-File x.ps1` 和 `-EncodedCommand` 都触发人工审批，无人响应会挂起超时（日期已脱敏 本机实测卡了两次，用户催"怎么还在运行"）。
2. **证据链完整再下结论，禁拿老规格印象想当然**。RTX 3070 想当然按 8GB 老版下结论，被用户纠正——2025 新版是 16GB（DEV_2484≠2482）。查完再说话。
3. **GPU 显存必须查 `memory.total`**。`Win32_VideoController.AdapterRAM` 是 32 位字段，>4GB 一律溢出显示 4293918720（4GB 假值）；`nvidia-smi --query-gpu` 必须带 `memory.total`，只看 `memory.used`（空闲=0）会误判。

## 轻量 PowerShell 命令模式（避免卡顿+乱码）

- **铁律：`-Command` 整段用单引号包裹**（`-Command '...'`）。此时 `$_` 是安全的，`Where-Object { $_.Status -ne "OK" }`、管道串 `$_` 都能放心用（本机整轮实测通过）。一旦改成双引号包裹，git-bash 会把 `$_` 展开成上条命令末参（cwd 路径）而破坏整段脚本——禁的是双引号包裹，不是 `$_` 本身。替代：用 `Format-List` / `Format-Table` + `Select-Object` 输出，不用 `ForEach-Object` 拼格式串；过滤器用 `-Filter 'DriveType=3'` 或 CIM Filter（`-Filter "Name LIKE '%Thunderbolt%'"`）。
- 每条命令开头加 `[Console]::OutputEncoding=[Text.Encoding]::UTF8` 防中文乱码。
- 多类别枚举时**并行发多条短命令**（每条一个类别），不要拼一条巨型命令。
- 避免 `Write-Host`（重定向输出会变 CLIXML 包裹）；如用了加 `-OutputFormat Text`。
- 写 .ps1 文件执行：内容全 ASCII（PS 5.1 无 BOM 按 GBK 读，中文乱码），stdout 转 UTF-8。

## 硬件清单 WMI 速查表

| 类别 | CIM 类 | 关键字段 |
|---|---|---|
| 整机/内存总量 | Win32_ComputerSystem | Manufacturer, Model, TotalPhysicalMemory |
| CPU | Win32_Processor | Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed |
| 内存条 | Win32_PhysicalMemory | Capacity, ConfiguredClockSpeed, Manufacturer, DeviceLocator |
| 主板/BIOS | Win32_BaseBoard / Win32_BIOS | Product, SMBIOSBIOSVersion, SerialNumber |
| 显卡 | Win32_VideoController | Name, PNPDeviceID, ConfigManagerErrorCode, DriverVersion, CurrentHorizontalResolution |
| 显示器 | root\wmi: WmiMonitorID | UserFriendlyName/ManufacturerName（字节数组转 char） |
| 磁盘/卷 | Win32_DiskDrive / Win32_LogicalDisk (-Filter 'DriveType=3') | Model, Size, InterfaceType; DeviceID, FreeSpace, FileSystem |
| 网卡 | Win32_NetworkAdapter (-Filter 'PhysicalAdapter=True') | Name, Speed, MACAddress |
| 声卡 | Win32_SoundDevice | Name, Status |
| 电池 | Win32_Battery | Name, EstimatedChargeRemaining |
| 设备树 | Get-PnpDevice -PresentOnly -Class X | FriendlyName, InstanceId, Status, Problem |

状态判定：`ConfigManagerErrorCode` 0 / `Problem CM_PROB_NONE` = 正常；`CM_PROB_NOT_CONFIGURED` = 需重装驱动。

## PnP 实例 ID 解码

格式：`PCI\VEN_xxxx&DEV_yyyy&SUBSYS_zzzzwwww&REV_aa\父ID&slot`

- **SUBSYS 后 4 位 = 板卡厂商**：`17AA`=<笔记本整机厂商>、`1458`=技嘉 GIGABYTE、`1B21`=ASMedia(祥硕)、`10DE`=NVIDIA、`8086`=Intel、`14C0`=Intel 主机板。
- 原装设备 SUBSYS 与整机厂商一致；不一致 = 外接/第三方卡（第一判据）。
- 实例 ID 后缀（父 ID）不同 = 设备换过接口/被重新枚举过（日志会出现旧实例需重装）。

## 设备来历深挖流程（2026-08 实证有效）

1. **nvidia-smi**：`"/c/Windows/System32/nvidia-smi.exe" -L` 列卡；`--query-gpu=index,name,pci.bus_id,memory.total,memory.free,memory.used,driver_version --format=csv`。bus `01:00.0`≈内置独显；`0F:00.0` 等大 bus 号≈外设桥后面（eGPU/坞）。
2. **PnP 详情**：`Get-PnpDevice -PresentOnly -Class Display | Format-List FriendlyName,InstanceId,Status,Problem`（Class 换 System/Bluetooth/USB 等查其他类）。
3. **父设备**：`Get-CimInstance Win32_PnPEntity -Filter 'DeviceID LIKE "%<父ID>%"'`。
4. **安装日志**（判来历的决定性证据）：`grep -i -B3 -A15 "DEV_2484" /c/Windows/inf/setupapi.dev.log`。看 `[Boot Session: 时间]`、`>>> [Device Install ...] 时间`、**`Parent Device:` 行**。
   - 连接方式判定：父设备 `VEN_1B21&DEV_2461` = **ASM2464PD USB4-PCIe 桥芯片** = USB4/雷电 eGPU 坞（ADT-Link UT3G 类）。完整链路：Intel USB4 主机路由器(8086 7EC3) → ASM2464 桥 → PCIe 交换机端口 → 显卡+其 HDMI/DP 音频。
5. **驱动安装时间**：日志 `Section start` 时间戳即装驱动时刻；驱动 INF 版本即 WHQL 版本。

## 「某设备到底接上了没有」判定流程（用户问"本机有没有接上 X"）

四维并行查，全空才敢说没接上；结论要落到链路上，不要落到驱动上。

| 维度 | 命令 | 判据 |
|---|---|---|
| USB 设备全集 | `Get-PnpDevice -PresentOnly \| Where-Object { $_.InstanceId -like "USB\*" } \| Select -ExpandProperty InstanceId \| Sort -Unique` | 列出全部 VID/PID，对照厂商 VID：1A86=CH34x、10C4=CP210x、0403=FTDI、1D6B=Linux gadget、2207=Rockchip |
| 串口 | `(Get-ItemProperty "HKLM:\HARDWARE\DEVICEMAP\SERIALCOMM")` + `[System.IO.Ports.SerialPort]::GetPortNames()` | 只剩 BthModem 的 COM 口 = 没有 USB 转串口设备 |
| 异常设备 | `Get-PnpDevice -PresentOnly \| Where-Object { $_.Status -ne "OK" }` | 空输出 = 连"未知设备/黄色感叹号"都没有 |
| 插拔活动 | `setupapi.dev.log` 尾部的 `>>> [Device Install ...]` / `[Boot Session:]` 段 + `Get-WinEvent -LogName System` 过滤 `PnP\|USB\|USB4\|UCSI` | 尾部长时间无新段 = 这段时间系统从未感知到插拔 |

**决定性机制**：只有 USB **Device/OTG 口**（串口打印口、gadget 口）才会让 PC 侧枚举出设备；**HOST 口和纯供电口（PD IN）插 PC 永远零枚举**——与线材、雷电口、驱动全无关。设备手册的接口表写 HOST 还是 HOST/Device 是唯一依据。四维全空就直说"这条链路不通"，并给出正确通道（见 dev-board-bringup 技能），别顺着"装驱动"排查。

## Pitfalls

- `setupapi.dev.log` 里 `Section start 20:30:26.153` 只有时分秒，而日志混着多个 boot session：必须往上找到同段的 `>>> Section start 2026/09/17 ...` 或最近的 `[Boot Session: ...]` 确认日期，否则会把几天前的事件读成"刚刚插上的"并据此下错结论。
- `pol: Blocking Core Device Install` 是每次安装都走的"设备安装限制策略检查"的正常输出，**不等于设备被策略拦下**——别拿它当"被策略阻止"的证据。
- `nvidia-smi --query-gpu` 的字段名要用 `name`（`product_name` 不是合法字段）；`-d` 参数只用于 `-q` 详情模式。
- USB4/雷电 eGPU 插拔前先设备管理器禁用该卡，否则下次以 CM_PROB_NOT_CONFIGURED 状态出现需重装。
- 笔记本多显卡时 CurrentHorizontalResolution 只有输出屏的卡有值；其余卡为空是正常的（≠故障）。
- 通用 PowerShell/MSYS 调用坑（$_ 展开、CLIXML、审批挂起、UTF-8）也见 windows-cn-env-quirks 技能第 6 节（，未收录时以此为准）。

## 支持文件

- `case-egpu-provenance.md` — 本机（the test laptop）硬件基线 + 3070 eGPU 调查完整案例（证据链、命令、结论），可当模板用。
