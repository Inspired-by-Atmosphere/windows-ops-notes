

> **适用平台**：Windows 10 / 11（含校园网、代理环境）  
> **一句话**：套餐档位 / 设备链路 / 互联 peering / 代理线路四层分层测，先定位再谈提速，禁止凭感觉下结论。  
> **标签**：network, speedtest, diagnostics, proxy, campus

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# 网络测速与提速诊断（四层瓶颈定位）

> 日期已脱敏 首建：校园网提速体检（读 校园网档案.md → 四层实测 → 定位瓶颈）。用户常问"网怎么这么慢/校园网能不能提速"，通用方法在此。

## 触发条件

- 用户抱怨网慢、问校园网/宿舍宽带能否提速、代理慢、出口 IP 疑问
- 需要"实测带宽"而不是猜（用户抓"估算结论会被质疑"，必须有实测依据）
- 涉及 Clash/TUN、校园网认证、运营商套餐、WiFi 频段

## 四层瓶颈框架（先分层再下结论，禁止武断）

网慢先分清是哪一层，各层测法不同：
1. **运营商套餐档位**（校园网=运营商"手机号卡+宽带"套餐，学校骨干通常不是瓶颈）→ 查官方说明/营业厅确认档位（100M/300M/500M）
2. **设备链路**（路由器/网卡/WiFi 频段）→ 千兆口/AC1200 对 100M 宽带远够用；无线看 5G vs 2.4G
3. **互联 peering**（电信↔教育网↔CDN 节点路径质量）→ 同一线路测多个不同网络目标，差异巨大=互联问题非线路上限
4. **代理线路**（Clash/机场节点吞吐）→ 境外流量单独测；往往是"感觉慢"的最大来源

## 实测方法（curl 测速）

```bash
# 关键：Windows 原生 curl 写 /dev/null 会报错且 speed 读 0（假象），必须写真实临时文件
T="$LOCALAPPDATA/Temp/spd.bin"
curl -s --noproxy "*" --ssl-no-revoke --connect-timeout 8 --max-time 20 -o "$T" \
  -w "速度: %{speed_download} B/s | 下载%{size_download}B | %{time_total}s | HTTP %{http_code}\n" \
  "<大文件URL>" && rm -f "$T"
```
- 国内直连用 `--noproxy "*"`（绕 env 代理；但 TUN 虚拟网卡接管默认路由，流量仍过 mihomo，规则决定直连/代理）
- 境外走代理用 `-x http://127.0.0.1:7897`
- **交叉多源**：同一线路测教育网（TUNA/USTC）+ 电信 CDN（腾讯/阿里）+ 境外各 1 次，速度差异大=互联 peering，非线路硬上限
- 镜像文件路径要真实存在：先 `curl 目录 | grep -oE 'href="[^"]*\.iso"'` 找文件名，别猜版本号（404）
- 大文件 URL 例：TUNA/USTC `ubuntu-releases/24.04/ubuntu-24.04.4-desktop-amd64.iso`（约6GB，--max-time 20 足够取样）；公共 CDN 上的软件安装包（示例：`https://<cdn-host>/setup.exe`）

## Clash Verge TUN 要点（用户默认代理）

- 配置在 `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\clash-verge.yaml`（用户可编辑档；运行时 external-controller 常为 ''，API 端口难查，节点切换让用户在 Verge 界面手动做）
- TUN 默认路由 metric 0（198.18.0.1）接管全部流量；`--noproxy` 不绕过 TUN，规则决定直连/代理
- 判断"是否国内直连分流"：直连 vs 走代理查 `myip.ipip.net`，出口同国内 IP=规则已直连国内（别误判全流量走境外）
- 机场节点常共用中转 server（如 `*.cnrcz.cn`），境外吞吐差≠节点少，是选中节点/中转线路问题

## 提速 lever 排序（收益降序）

1. 代理线路：境外吞吐 1Mbps vs 国内 70M 时，换节点/换机场收益最大
2. 运营商套餐升档（先确认当前档位再建议；路由器/网卡支持千兆则升档不用换设备）
3. 无线设备连 5G 频段（2.4G 减半）
4. 校园内网/数据库资源走教育网出口（认证选教育网，免费且快）

## 坑位

- Windows curl `-w "%{speed_download}"` 写 `/dev/null` → 0 B/s 假象 + exit 23；必须 `-o` 真实文件
- 阿里云镜像 302 不跟跳（-L 也 0 字节）→ 别用，换腾讯/中科大
- 实测结论前先查官方（学校官网"校园网介绍"页有骨干带宽/到桌面速率/套餐归属）——分清楚"学校骨干" vs "运营商套餐"
- 校园网档案/硬件档案在 `%USERPROFILE%\Documents\`，体检后把实测数据补进对应档案

## 关联

- 校园网档案模板（官方事实/拓扑/实测带宽/纪律四块）：`campus-network-profile-template.md`
- 出口软路由与 portal 认证恢复：`campus-edge-router.md`
- 代理拦截 / 镜像加速 / 编码坑：`../windows-shell/cn-env-encoding-quirks.md`
- 硬件体检方法论：`../windows-hardware/hardware-diagnostics.md`
