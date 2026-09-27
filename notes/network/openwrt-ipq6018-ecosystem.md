# OpenWrt 在 IPQ6018 小内存机型上的软件生态实测


> **适用平台**：OpenWrt / ImmortalWrt，IPQ6018 平台，2GB 内存 + 2GB 分区、无 swap  
> **一句话**：缺 tun 驱动是这批机型的硬伤；缺模块的三条替代路线按性价比排序，自编 kmod 基本不值得。  
> **标签**：openwrt, ipq6018, kmod, tun, tailscale

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

宿舍主路由这台机器能装什么、不能装什么、装之前必须知道的硬事实。除标注"未验证"外，均为本机 `ssh your-router` 实测。

## 平台事实

| 项 | 实测值 |
|---|---|
| SoC / 固件 | Qualcomm IPQ6018（4×A53），ImmortalWrt SNAPSHOT，内核 6.12.45，LuCI 25.x，**apk** 包管理（非 opkg） |
| 内存 | 1.86 GiB，available ≈1.7 GiB，**Swap = 0** |
| 存储 | eMMC 8G，但 rootfs 是 **2.0G 的 loop 镜像**（f2fs，`/dev/loop0` → `/overlay`），`/rom` 14.5M squashfs；`/tmp` 是 951MB tmpfs（不磨损 flash） |
| 加速 | NSS/ECM 真在跑：`lsmod` 见 `ecm` 458752、`qca_nss_drv`、`qca_ssdk` |
| 包索引 | ≈10k 包，源可正常 update |

**无 swap 是这台机器唯一真风险**：OOM 直接杀进程，可能杀掉 dnsmasq/netifd 导致全网断——禁装内存大户（见下表）。

## 三个改变结论的硬事实

1. **apk 源里有 3 个 feed 已下线（404）**：`nss_packages`、`sqm_scripts_nss`、`video`（就在 `/etc/apk/repositories.d/` 列表里）。表现是 `apk update` 报 `3 unavailable`、看起来"源是空的"。**修法是删掉这三行**（改前备份）。`base`/`packages`/`luci`/`routing` 正常。
2. **没有 tun 驱动**：`/lib/modules/$(uname -r)/` 里没有 `tun.ko`，`modules.builtin`/`modules.dep` 里也没有（只有 `tunnel4.ko`/`tunnel6.ko`，那是 IPv4/IPv6 tunnel，与 TUN/TAP 无关）。`/dev/net/tun` 节点虽然存在（crw 10,200）**但驱动不在 → 打开必然失败**，`mknod` 修不了这个。任何走内核 TUN 的（WireGuard/OpenVPN/Tailscale）都上不去。⚠ 自编 `tun.ko` 不只看 vermagic，还要 `struct module` 尺寸一致（见下文实测），单靠"交叉编译一个"并不成立。
3. **官方 kmod 源只保留最新内核版本**：本机 `uname -r` 6.12.45 对应目录已从 snapshot 的 kmods 里下架（目录里只有更新的版本）。所以"缺哪个 kmod 就 apk 装"这条路对本机不成立。

## 缺 tun 的三条路线（按性价比）

| 路线 | 代价 | 建议 |
|---|---|---|
| 交叉编译匹配版本的 `tun.ko` | 工具有，但**必须拿到该 revision 的内核配置**，否则加载被拒（见下节实测） | 仅在能复现官方构建系统时才考虑 |
| userspace 模式（`tailscaled --tun=userspace-networking`） | 26 MiB 安装、常驻 15–25 MB，吞吐低、CPU 高 | 要在这台机器上跑节点时用 |
| 把节点跑在**已有 TUN 的 Linux 主机**上，由它播 `--advertise-routes=<宿舍网段>` 当子网路由 | 几乎为零，不动路由器 | **首选**：要的是"从外网进宿舍网段"时，这才是最短路径 |
| 重刷内置 Tailscale 的固件 | 推倒已验收的 WAN MAC 克隆 / LAN 网段 / SSID / 看门狗配置 | **不推荐** |

## 自编 tun.ko 的实测结论（日期已脱敏，别重踩）

**vermagic 对上了也没用——内核还要查 `struct module` 尺寸。** 加载失败的原话：

```
module tun: .gnu.linkonce.this_module section size must match the kernel's built struct module size at run time
```

- **先量目标尺寸**（路由器没有 binutils，把模块拷到 Linux 机器上量）：
  `ssh your-router 'cat /lib/modules/$(uname -r)/tunnel4.ko' > x.ko` → `readelf -SW x.ko | grep this_module`。
  本机 r35949/6.12.45 的答案是 **0x2c0（704 字节）**。
- **defconfig 编译必被拒**：用 vanilla 6.12.45 + arm64 defconfig 编出来的 tun.ko 是 **0x440（1088）**，
  比内核大 384 字节（defconfig 开了一堆 OpenWrt 没开的调试/追踪能力），加载当场被拒。
- **跨 revision 借官方 kmod 也不行**：snapshot 的 `kmods/<kver>-<hash>/` 目录虽保留多个内核版本，
  但最近一版（6.12.63）的官方 `tun.ko` 是 **0x4c0（1216）**，且它的 vermagic 是
  `6.12.63 SMP mod_unload aarch64`（**没有 preempt**），与本机 `6.12.45 SMP preempt mod_unload aarch64` 不同
  → ImmortalWrt 两个快照间连内核配置都改了，不能跨版本借用。
- **老快照的内核配置拿不到**（三条都试过）：`/proc/config.gz` 不存在（未开 IKCONFIG_PROC）；快照目录已轮换；
  `archive.immortalwrt.org` 302 到 kyarucloud 归档站，那里只留 releases、没有 snapshot。唯一可靠路线是把
  ImmortalWrt 构建系统按该 revision 起起来（小时级 + GB 级），只为装个 Tailscale 不值得。
- **别靠猜配置**：一次性关掉 ftrace / kprobes / tracepoints / event_tracing / livepatch / module_sig /
  BTF / CFI / bpf_syscall 之后，`struct module` 尺寸**一个字节都没变**（仍 0x440）→ 影响在更底层的配置差异上，
  盲试不收敛。

**可复用的手法（下次上手快很多）**：

```bash
# 1) 交叉编外部模块（不要编内核树里的 drivers/net，那里会因缺 Module.symvers 报 8192 个未解析符号）
mkdir -p $BASE/tunmod && cp $SRC/drivers/net/tun.c $BASE/tunmod/ && echo 'obj-m := tun.o' > $BASE/tunmod/Makefile
make -C $SRC ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- O=$OUT M=$BASE/tunmod \
     KBUILD_MODPOST_WARN=1 modules -j$(nproc)     # 外部模块的未解析符号降级为警告，运行时解析
# 2) 量尺寸 / 核 vermagic（Ubuntu 那版 modinfo 可能读不出 cross 编的模块元数据）
readelf -SW $KO | grep this_module ; readelf -p .modinfo $KO | grep vermagic
# 3) 解包官方 apk（v3/ADB 格式，普通 tar 解不开；apk extract 不查依赖，绕开 kernel=<ver> 约束）
mkdir -p /tmp/x && cd /tmp/x && apk extract --allow-untrusted /tmp/kmod-tun-*.apk
```

**制造机与下载**：编内核模块放 Linux 机上，`setsid nohup` 跑成脱离会话的进程（agent 会话断网不会杀它）；
国内拉内核源码用镜像（阿里云 14 MB/s、清华 6.5 MB/s），`cdn.kernel.org` 只有约 40 KB/s（145 MB 要一小时）；
`shake -C $SRC` 与 `O=` 同时用，否则 `olddefconfig` 报 "没有规则可制作目标"、配置悄悄不生效。

**优先级提示**：如果目的只是"从外网进宿舍网段"，先看已有 Linux 主机能不能当 Tailscale 子网路由
（`tailscale set --advertise-routes=192.168.1.0/24`，需 `net.ipv4.ip_forward=1`），它**不需要任何内核模块**，
比在路由器上折腾 tun.ko 快一个数量级；只在必须让路由器本体做节点时才回到 tun.ko。

## 可装 / 禁装（2G 内存 + 无 swap + 2G 分区）

**建议装（零内核依赖、体积极小）**：`vlmcsd` 47 KiB、`adblock`+`luci-app-adblock` ≈190 KiB、`ddns-scripts`+`ddns-scripts-cloudflare`+`luci-app-ddns` 共 124 KiB、`ttyd` 618 KiB、`zerotier` 1007 KiB（**userspace 实现，不依赖 kmod-tun**，是当前唯一能直接用的异地组网）。

**禁装/换替代**：`adguardhome`（32 MiB / RSS 60–120 MB，需求被 77 KiB 的 adblock 覆盖）、`samba4-server`、`frps`（18 MiB）、`ddns-go`（10 MiB，同需求 ddns-scripts 只需 71 KiB）、`openclash`（依赖 3 个本机拿不到的 kmod：kmod-tun / kmod-nft-tproxy / kmod-inet-diag，外加 ruby/bash/unzip）、`homeproxy`（只差 kmod-nft-tproxy，但后端 sing-box 39 MiB，合计反超）。`mihomo` 与 watchdog 类包在源里根本不存在。

## 透明代理与 NSS

- **NSS/ECM 与 flow offloading 不是同一层的两个开关**：前者是 IPQ6018 专用硬件引擎（基本绕过 CPU），后者是上游 netfilter 快速路径。两者独立、可共存；社区惯例是**开 NSS、关 flow offloading**（本机现状即如此）。
- 两者的共同敌人是 **TProxy**：TProxy 要在 PREROUTING 精确拦包，任何提前接管的机制都会漏流量。上透明代理前先按"关 flow offloading → 再看 ecm 的 offload 开关"逐项验证，别为代理长期关掉 NSS（宿舍出口正需要它）。
- IPQ6018 的 A53 单核才是瓶颈（不是内存）：单核 AES-GCM/ChaCha20 约 100–200 Mbps，宿舍 200–300 Mbps 下代理必然成为瓶颈，必须 GEOIP CN 直连分流。

## 备份与持久化

- 固件自带 `sysupgrade -b/-r`；要定时备份就自己写脚本 + **写进 `/etc/sysupgrade.conf`**（默认空白，不写就刷机即丢），Windows 侧用 `ssh '<别名>' 'cat /root/xxx.tar.gz' > 本地` 拉回。
- dropbear 一般没有 `sftp-server` → **scp/sftp 不可用**，推拉文件都用 `ssh ... 'cat > 路径' < 本地文件`。
- 装包前记下 `apk list --installed | wc -l`（本机 311），改动后比对，便于发现依赖污染。

## 来源

- 包/固件目录：`downloads.immortalwrt.org/snapshots/packages/aarch64_cortex-a53/`（逐 feed 判 404）、`downloads.immortalwrt.org/snapshots/targets/qualcommax/ipq60xx/kmods/`
- Tailscale userspace：`tailscale.com/kb/1112/userspace-networking/`
- OpenClash / HomeProxy 仓库 README 的依赖列表（`vernesong/OpenClash`、`immortalwrt/homeproxy`）
- NSS 加速说明：`github.com/qosmio/openwrt-ipq`、`github.com/iFHaxx/openwrt-nss`、`openwrt-libwrt` 的 NSS 文档
- flow offloading 与 fw3/fw4：`openwrt.org/docs/guide-user/firewall/fw3_configuration`
