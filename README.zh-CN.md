# windows-ops-notes

真实 Windows / OpenWrt / 校园网排障现场留下的笔记与零依赖脚本。

## 为什么有这份东西

这类问题在网上一搜，要么是一行对不上症状的 Stack Overflow 回答，要么是假设你那个 GUI
还长三年前样子的厂商文档。这里记的是另一样东西：**取证据的顺序**、**真正得出答案的那条命令**、
以及**花了时间的那个坑**。

组织方式按诊断过程走，不按手册走：

> **现象 / 适用场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**

每篇自包含，都贴着写它时的那台机器 / 那台路由器。所有环境相关的值都换成了占位符
（见 [docs/SANITIZE_LOG.md](docs/SANITIZE_LOG.md)）；占位符是示例，不是让你照抄的值。

## 目录结构

```
windows-ops-notes/
├── README.md                  # 英文版
├── README.zh-CN.md            # 本文件
├── notes/
│   ├── network/               # 校园网、OpenWrt、代理、网速诊断
│   ├── windows-apps/          # 无管理员权限装软件
│   ├── windows-autostart/     # 启动项、弹窗溯源、崩溃循环
│   ├── windows-boot/          # U 盘安装盘、Linux 装机、双系统缩容
│   ├── windows-filesystem/    # 文件占用
│   ├── windows-gui/           # 窗口枚举/恢复、代理客户端
│   ├── windows-hardware/      # 硬件枚举、GPU/eGPU、蓝屏与待机卡死
│   └── windows-shell/         # 控制台窗口、静默启动、中文环境坑
├── scripts/                   # 笔记里调用的工具，也可单独使用
└── docs/SANITIZE_LOG.md       # 发布前删掉了什么
```

## Quickstart

1. 先看对得上症状的那篇，例如 `notes/windows-hardware/hardware-diagnostics.md`。
2. 跑笔记里点名的 `scripts/` 探针，先不带参数跑（有 `--help` 的先看 `--help`）——工具只用标准库。
3. 把 `<占位符>`（`<GPU_INDEX>`、`<GPU_INSTANCE_ID>`、`<口令>` …）换成你自己的值，再跑任何会改状态的命令。

```bash
python scripts/check_secrets.py .        # 隐私门禁，发布前先跑
python scripts/memcheck.py > mem.txt     # 整机内存全貌
python scripts/pe_subsystem.py <exe>     # 2=GUI（不弹窗），3=Console（会弹窗）
```

## 笔记目录

### 网络

| 笔记 | 什么时候用 | 一句话思路 |
|---|---|---|
| [campus-edge-router.md](notes/network/campus-edge-router.md) | 换宿舍/办公室出口路由、portal 认证恢复、WAN MAC 克隆、LAN 网段迁移 | 动生产链路前先拿到可持续的 root 通道（SSH 密钥） |
| [campus-network-profile-template.md](notes/network/campus-network-profile-template.md) | 给任意校园网/单位网络建档的空模板 | 钉死四块：官方事实 / 接入拓扑 / 实测带宽 / 限制与纪律 |
| [multi-wan-proxy-routing.md](notes/network/multi-wan-proxy-routing.md) | 有线 + 无线 + TUN 代理同时存在，"有的站能上有的上不了" | 代理只管走它的流量——要修的是直连路径，不是代理配置 |
| [network-speed-diagnostics.md](notes/network/network-speed-diagnostics.md) | 说"网慢"、准备动手之前 | 四层分开测：套餐档位 / 设备链路 / 互联 peering / 代理线路 |
| [openwrt-ipq6018-ecosystem.md](notes/network/openwrt-ipq6018-ecosystem.md) | 小内存 IPQ6018 机型上跑 OpenWrt、缺内核模块 | 缺 `tun` kmod 是硬伤；三条替代路线按成本排序 |
| [openwrt-ubus-rpc.md](notes/network/openwrt-ubus-rpc.md) | 路由器 ubus 能通但 SSH 挂了，或要脚本化改配置 | ubus RPC 是后路：读文件、改配置、重启服务都能办 |
| [portal-autologin-service.md](notes/network/portal-autologin-service.md) | 写 captive portal 保活/自动登录看门狗 | 探测必须用真实站点正文，别用 captive 探测 URL（常被白名单） |
| [proxy-client-control-api.md](notes/network/proxy-client-control-api.md) | 在 Windows 上脚本化控制 Clash Verge Rev / mihomo | 控制 API 在命名管道上，`curl` 打不开——用 ctypes 自己写客户端 |

### Windows：应用、自启、装机

| 笔记 | 什么时候用 | 一句话思路 |
|---|---|---|
| [software-deploy-no-admin.md](notes/windows-apps/software-deploy-no-admin.md) | 没有管理员权限却要装软件 | 免提权便携安装路径，再把步骤压成一键包交付 |
| [autostart-inventory-and-popup-source.md](notes/windows-autostart/autostart-inventory-and-popup-source.md) | 开机弹东西但自启列表里找不到它 | 自启有五处，外加一处隐藏的会话恢复路径 |
| [case-crashloop-and-dock-popup.md](notes/windows-autostart/case-crashloop-and-dock-popup.md) | 窗口反复出现，或只出现一次 | 用"进程数 + 创建时间"区分崩溃循环与会话恢复 |
| [startup-popup-playbook.md](notes/windows-autostart/startup-popup-playbook.md) | 要完整可照抄的作业顺序，而不是单个技巧 | 对号窗口 → 五处启动点 → 进程树 → 备份通道 → 修复与回滚 |
| [linux-install-notes.md](notes/windows-boot/linux-install-notes.md) | 在 x86_64 机器上装 Ubuntu 系发行版 | 先判引导模式再分区；装完第一轮就做体检 |
| [offline-ext4-shrink.md](notes/windows-boot/offline-ext4-shrink.md) | 给已经装了 Linux 的盘腾双系统空间 | 先备份；尺寸、`e2fsck`、复验三件套缺一不算完成 |
| [usb-install-media.md](notes/windows-boot/usb-install-media.md) | 做可启动 U 盘（Ventoy、ISO、混合 ISO） | 先确认 U 盘物理身份，ISO 双重校验，交给 Ventoy 直拷 |
| [ventoy-gui-automation.md](notes/windows-boot/ventoy-gui-automation.md) | 自动化 Ventoy2Disk GUI，或"点了没反应" | 前台锁 + 全屏遮挡让物理点击落空，先置前再点 |

### Windows：文件系统、GUI、硬件、Shell

| 笔记 | 什么时候用 | 一句话思路 |
|---|---|---|
| [file-lock-hunting.md](notes/windows-filesystem/file-lock-hunting.md) | "文件被另一个进程占用"，要找具体是谁 | Restart Manager 给准确持有者；确认无可见窗口才结束它 |
| [proxy-client-windows-notes.md](notes/windows-gui/proxy-client-windows-notes.md) | 代理客户端的日常使用与排障 | GUI 与内核是两套进程；fake-ip 会污染"内网地址"判定 |
| [window-recovery-and-automation.md](notes/windows-gui/window-recovery-and-automation.md) | 桌面应用窗口"不见了"（Tauri/Electron） | 按阶梯恢复；GUI 重启不等于服务重启 |
| [hardware-diagnostics.md](notes/windows-hardware/hardware-diagnostics.md) | 枚举硬件、GPU/eGPU 溯源、蓝屏、待机卡死 | 先建证据链：事件日志 + WER + 进程父子链 |
| [hardware-enumeration.md](notes/windows-hardware/hardware-enumeration.md) | "这块卡是原装吗？到底接上了没有？" | WMI/PnP 实例 ID + 安装史 + 父设备链能同时回答两个问题 |
| [event-ids-and-bugchecks.md](notes/windows-hardware/event-ids-and-bugchecks.md) | 手里有 System 日志或停止码，要查语义 | 一张表把显卡/电源/驱动的事件 ID 与 Bugcheck 码对上 |
| [case-egpu-provenance.md](notes/windows-hardware/case-egpu-provenance.md) | 要证明一块显卡是原装还是外接 | SUBSYS 厂商 ID 与整机 OEM ID 不一致就是外接铁证 |
| [case-modern-standby-hang.md](notes/windows-hardware/case-modern-standby-hang.md) | 笔记本在待机/空闲切换后整机僵死 | 30 秒服务超时风暴 + Kernel-Power 41 = 整机僵死的指纹 |
| [cn-env-encoding-quirks.md](notes/windows-shell/cn-env-encoding-quirks.md) | 中文环境：补丁打不上、"匹配到二进制"、安装卡住 | 五类对号：CRLF / 编码 / 路径 / 代理拦截 / 镜像源 |
| [console-silent-launch.md](notes/windows-shell/console-silent-launch.md) | 开机弹控制台窗口（或疯狂闪窗） | 任何 console 子系统进程都会弹窗；改用 pythonw 调模块入口 |
| [default-terminal-diagnostics.md](notes/windows-shell/default-terminal-diagnostics.md) | Windows 11 默认终端 = Windows Terminal | conhost 与 WindowsTerminal 决定 SW_HIDE 有没有用 |
| [silent-launch-case-service.md](notes/windows-shell/silent-launch-case-service.md) | uv/pip 装的服务反复闪窗 | 两个触发点在竞速重启 + 包装器逐层 re-exec，两边都要改 |

## 脚本

Python 脚本全部只用标准库；打到 stdout，失败时退出码非零，可以直接当门禁用。

| 脚本 | 用途 |
|---|---|
| [check_secrets.py](scripts/check_secrets.py) | 零依赖仓库扫描器：凭据、高熵串、内网 IP、MAC、邮箱、用户目录路径、内网主机名 |
| [memcheck.py](scripts/memcheck.py) | 整机内存全貌：commit 率、内存类型分解、按应用聚合、分页文件、GPU 显存 |
| [catch_popup.py](scripts/catch_popup.py) | 采样进程表，打印每个新出现的 console 类进程及其父进程链 |
| [watch_popups.py](scripts/watch_popups.py) | 同一个探针，针对开机闪窗洪峰调过（登录后立刻跑） |
| [read_visible_windows.ps1](scripts/read_visible_windows.ps1) | 列出可见顶层窗口及其所属进程 |
| [find_file_lock.py](scripts/find_file_lock.py) | 用 Restart Manager API 查谁占着文件 |
| [pe_subsystem.py](scripts/pe_subsystem.py) | 不运行程序就读 PE 头：子系统 2=GUI，3=Console |
| [mihomo_pipe_api.py](scripts/mihomo_pipe_api.py) | 通过 Windows 命名管道调用 mihomo（Clash Meta）控制 API |
| [vscode_vsix_install.py](scripts/vscode_vsix_install.py) | 用 VSIX 离线装 VS Code 扩展，自动挑兼容版本 |
| [wan_mab_watchdog.sh](scripts/wan_mab_watchdog.sh) | OpenWrt/busybox ash 保活看门狗：探真实内容 → 物理弹 WAN 重触发 MAC 认证 |
| [gpu-power-mode/](scripts/gpu-power-mode/) | 四个 `.bat` 模板：断开 eGPU / 启用 eGPU / 锁频能效模式 / 恢复默认 |

## 配置

不需要配置文件。环境变量与默认值：

| 变量 | 用于 | 默认值 | 含义 |
|---|---|---|---|
| `MIHOMO_PIPE` | mihomo_pipe_api.py | `\\.\pipe\verge-mihomo` | 控制 API 的命名管道 |
| `MIHOMO_SECRET` | mihomo_pipe_api.py | 空 | 控制 API 的 bearer secret（若有） |
| `LOCALAPPDATA` | vscode_vsix_install.py | （Windows） | 探测 VS Code CLI 的位置 |
| `PORTAL_MARK` | wan_mab_watchdog.sh | `10.0.0.254` | 响应正文里出现它 = 未认证 |
| `PROBE_URLS` | wan_mab_watchdog.sh | `http://www.baidu.com http://www.163.com` | 用作认证探测的真实站点 |
| `WAN_IF` | wan_mab_watchdog.sh | `wan` | 要弹的 WAN 链路接口名 |
| `LOG` / `STATE` | wan_mab_watchdog.sh | `/etc/wan_mab.log` / `/etc/wan_mab.state` | 日志与状态文件（要活过刷机需写进 `/etc/sysupgrade.conf`） |
| `FAIL_NEED` / `COOLDOWN` | wan_mab_watchdog.sh | `2` / `900` | 连续失败几次才动作 / 两次动作间隔秒数 |
| `DOWN_SECONDS` / `SETTLE` | wan_mab_watchdog.sh | `25` / `25` | 物理掉线时长 / 复探前的静默时长 |
| `BACKOFF_STEP` / `BACKOFF_MAX` | wan_mab_watchdog.sh | `1800` / `7200` | 弹失败后的退避步长与上限 |

## 运行环境要求

- **Windows 相关笔记与脚本**：Windows 10 / 11，Windows PowerShell 5.1+，Python 3.x（仅标准库）；
  GPU 部分需要 `nvidia-smi`（没有就跳过该节）。
- **路由器相关笔记与看门狗**：OpenWrt / ImmortalWrt，`ubus` + `dropbear`，busybox `ash`
  （不假设有 `curl`，也不假设有 `sftp-server`）。
- **装机/双系统笔记**：ext4 缩容需要 Linux live 会话；U 盘部分需要 Ventoy。
- 无第三方 Python 依赖，见 [requirements.txt](requirements.txt)。

## 局限

- **天生环境特定。** 每篇只描述一台真实机器、一款路由器、一家 portal 厂商。推理过程可迁移，具体输出不能。
- **占位符必须替换。** `AA:BB:CC:DD:EE:02`、`192.168.1.x`、`10.0.0.x`、`<GPU_INSTANCE_ID>`、`<口令>`
  都是示例。换雷电口或重装驱动后，设备的实例 ID 与 GPU 索引都会变。
- **结论有时效。** Portal 菜单、LuCI 页面布局与路由器固件都按各篇标明的版本验证过，厂商会改版。
- **部分操作会改系统状态**——崩溃转储设置、电源设置、UCI 配置、防火墙、禁用设备。先读回滚段，
  先做备份再动手。
- **不提供任何保证。** 笔记记的是"当时这么做有效"；用在你真正在乎的机器上之前，请自行验证。

## 许可

MIT，见 [LICENSE](LICENSE)。Copyright (c) 2026 Inspired-by-Atmosphere。
