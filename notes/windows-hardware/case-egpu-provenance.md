# 案例：外接显卡来历溯源（SUBSYS 厂商比对法）


> **适用平台**：Windows 10 / 11 + NVIDIA 显卡 / USB4-雷电外接  
> **一句话**：SUBSYS 后四位是板卡厂商：与整机 OEM ID 不一致就是外接件——这条判据比"设备管理器里看着像"可靠得多。  
> **标签**：windows, egpu, hardware, provenance, subsys

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

本文件双重用途：① 本机硬件基线（未来性能/DL 任务直接查）；② windows-hardware-enum 方法的完整实例。

## 本机基线（the test laptop，2025 款笔记本，Win11 家庭版 26200 64位）

- **CPU**: Intel Core Ultra 7 255H（Arrow Lake，16核16线程无HT，基准 2.0GHz）
- **内存**: 32GB DDR5-5600 双通道（2×16GB Samsung M425R2GA3EB0-CWMOD）
- **主板**: <board-id> / BIOS <bios-version> / SN <SN-REDACTED>
- **核显**: Intel Arc 140T（16GB 共享显存）— 内屏输出 3200×2000
- **内置独显**: NVIDIA GeForce RTX 5060 Laptop 8GB（bus 01:00.0，SUBSYS 3F9617AA=<laptop OEM>）
- **外接 eGPU**: NVIDIA GeForce RTX 3070 **16GB**（bus 0F:00.0，SUBSYS 40691458=技嘉，DEV_2484=2025 新版 16GB SKU）
- **存储**: 系统盘 C: Lexar NM610PRO 500GB NVMe（曾仅剩 35GB）；数据盘 D:+E: 忆联 UMIS 1TB 分两区
- **网络**: 有线 Intel I219-V；蓝牙 Intel Wireless（MAC AA:BB:CC:DD:EE:02）；虚拟网卡=深信服VPN/Tailscale/Meta Tunnel(Clash)；⚠️WiFi 适配器未枚举到（疑禁用）
- **音频**: Realtek HDA(SST) + NVIDIA HD Audio×2 + Intel 智音；虚拟：NVIDIA/iTop/网易虚拟音频
- **虚拟显示**: 向日葵(Oray)/AskLink/GameViewer/Todesk 四个远程虚拟显卡
- **蓝牙外设**: inphic S6 鼠标、zdeer G4 键盘、左护卫设备
- **电池**: L24X4PG7

## RTX 3070 调查结论（用户问"深度研究 3070 情况"）

**结论：技嘉非公版 RTX 3070 16GB，通过 USB4/雷电 eGPU 坞（ASM2464PD 桥芯片）外接；日期已脱敏 19:23 装好驱动；当前正常但完全空闲（0% / 0 MiB），无外接屏。**

### 证据链（按发现顺序）

1. **nvidia-smi -L** → GPU 1: RTX 3070；`--query-gpu=...pci.bus_id...` → `00000000:0F:00.0`（内置独显在 bus 01）
2. **Get-PnpDevice -Class Display** → 实例 ID `PCI\VEN_10DE&DEV_2484&SUBSYS_40691458&REV_A1\6&383292C7&0&00000038`；SUBSYS 1458=技嘉 vs 本机 17AA=<laptop OEM> → 非原装
3. **setupapi.dev.log** grep `DEV_2484`（注意：不是 2482！）→ `[Boot Session: 2026/08/12 19:22]`、`Device Install ... 19:23:00`（触发原因 CM_PROB_NOT_CONFIGURED=之前配置错误需重装）、`Parent Device: PCI\VEN_1B21&DEV_2461&SUBSYS_24611B21&REV_00\5&36bb1487&1&000038` = ASM2464PD；驱动 oem141.inf WHQL 32.0.15.9579（=595.79）
4. **Get-CimInstance Win32_PnPEntity -Filter 'DeviceID LIKE "%383292C7%"'** → 显卡 + 其 HD Audio（DEV_228B 挂在同父设备）→ 坞带 HDMI/DP 音频
5. **设备树**（-Filter "Name LIKE '%Thunderbolt%' OR ..."）→ Intel USB4 主机路由器(8086 7EC3) → ASM2464 USB4 路由器 → PCIe 上/下游交换机端口 → 显卡
6. 日志 `Needs Reinstall: ...4&292984A6&0&0032`（旧实例 ID）→ 换过接口/位置

### 用户纠错教训（重要）

- 初版报告**没查 memory.total**，拿"3070=8GB"老印象说"显存与 5060 相同、跑大模型没优势"——**完全错误**，被用户纠正"这个 3070 是 16G 的"。
- 实测：`--query-gpu=...memory.total...` → **16384 MiB**；free 16177 MiB。
- 修正后价值评估：16GB 显存=本机最能打的卡；双卡 8+16=24GB，llama.cpp 分片可跑 32B Q4（~18-19GB）；短板仅 USB4 带宽（≈PCIe 3.0 x4），推理/中小规模微调够用。
- 教训固化：GPU 显存必须查 memory.total；Win32 AdapterRAM 4GB 溢出是假值；禁用规格记忆推断。

### 命令模板（可直接复用）

```bash
# 1. 显卡总览（含显存！）
"/c/Windows/System32/nvidia-smi.exe" --query-gpu=index,name,pci.bus_id,memory.total,memory.free,memory.used,driver_version --format=csv

# 2. 显示类 PnP 详情
powershell.exe -NoProfile -Command "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-PnpDevice -PresentOnly -Class Display | Format-List FriendlyName,InstanceId,Status,Problem,Class"

# 3. 父设备/同族设备
powershell.exe -NoProfile -Command "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-CimInstance Win32_PnPEntity -Filter 'DeviceID LIKE \"%383292C7%\"' | Format-List Name,DeviceID,Manufacturer,Status"

# 4. 安装史（换 DEV ID 数字）
grep -n -i -B3 -A15 "DEV_2484" /c/Windows/inf/setupapi.dev.log | head -150

# 5. USB4/雷电链路
powershell.exe -NoProfile -Command "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-CimInstance Win32_PnPEntity -Filter \"Name LIKE '%Thunderbolt%' OR Name LIKE '%USB4%' OR Name LIKE '%PCI Express%'\" | Format-Table -AutoSize Name,DeviceID | Out-String -Width 250"
```
