# Windows 代理客户端（Clash Verge Rev）使用与排障要点


> **适用平台**：Windows 10 / 11  
> **一句话**：GUI 与内核是两套进程：GUI 重启不断网；DNS fake-ip 会污染"内网地址"判定，直连工具必须显式走代理端口。  
> **标签**：windows, proxy, clash-verge, tun, fake-ip

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

Clash Verge Rev v2.5.2（Tauri 2 + mihomo v1.19.29 内核），安装于 `%ProgramFiles%\Clash Verge\`，配置目录 `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\`（verge.yaml=GUI 设置、dns_config.yaml=DNS、profiles.yaml=订阅清单、clash-verge.yaml=当前生效完整配置）。本文件同时是"本机代理环境"知识库，任何工具链遇到 fake-ip/代理问题先读这里。

## 本机关键配置（2026-08 实测）

| 项 | 值 |
|---|---|
| TUN 模式 | 开（全流量接管；系统代理关闭） |
| 混合端口 | 7897（HTTP+SOCKS5 同端口，程序手动代理用这个） |
| DNS | fake-ip 模式，范围 198.18.0.1/16（**所有域名解析到 198.18.0.x**） |
| 订阅 | XFLTD（get.cctvclient.cn），XFLTD 组当前=美国 03 [V]，自动选择组=香港 01 [V] |
| 代理组 | XFLTD（Selector 手动）、自动选择（URLTest）、故障转移（Fallback） |
| 模式 | 规则（516 条规则，Match 兜底走 XFLTD） |
| 开机自启 | 开 |

## 进程结构

- `clash-verge.exe` = GUI（可重启，不影响代理）；`verge-mihomo.exe` = 内核（Services 会话，TUN 由它提供）；`clash-verge-service.exe` = 守护服务。

## 8 页 UI 速查

1. **首页**：订阅用量、当前节点、TUN/系统代理开关、规则/全局/直连模式、出口 IP 卡片。
2. **代理**：换节点。每个代理组一张卡片（右侧⚡测速/排序/过滤/隐藏细节），展开点选节点。
3. **订阅**：顶部输入框粘贴订阅链接 →「新建」；卡片 🔄 刷新单个，工具栏可全部更新/重新激活。
4. **连接**：实时连接表（主机/流量/链路/命中规则/源地址）。源地址 `198.18.0.1` = fake-ip 入口证据。「关闭全部」一键断开；过滤框按域名筛选。排障先看这里。
5. **规则**：规则顺序匹配，命中即停。过滤框查域名走哪条规则。
6. **日志**：内核流水账 `[协议] 源 → 目标 match 规则 using 链路`。级别下拉切 ERROR/DEBUG 排障。
7. **测试**：解锁测试（ChatGPT/Claude/Netflix/Disney+/YouTube/TikTok/B 站等），「测试全部」一键。
8. **设置**：TUN 开关（旁有「卸载服务」勿乱点）、系统代理、自启、端口 7897、外部控制（默认关）、WebDAV 备份、配置目录（异常时备份删除重启）。

## 与其他工具链的关联（重要）

- **the harness web_extract 的 SSRF 拦截根因**：fake-ip 解析到 198.18.0.0/15（保留内网段），提取器 SSRF 防护把所有域名误判为"internal network address"拒绝（`Blocked: URL targets a private or internal network address`）。解法：改用 Obscura（`--proxy http://127.0.0.1:7897`）或 browser 工具，不要重试 web_extract。
- **Obscura 直连必挂**：拿到 fake-ip 后直连不走 TUN，必须显式 `--proxy http://127.0.0.1:7897`（或 socks5:// 同端口）。Obscura 二进制在 `%LOCALAPPDATA%\app\tools\obscura\`，另有 `web/obscura` 技能。
- curl/浏览器走 TUN 正常，无需配置。
- 规则模式下国内流量 DIRECT（不耗订阅流量），国外走 XFLTD 组。

## 常见问题

- 订阅更新失败：机场抽风或证书校验，稍后重试/切直连再更新。
- 节点全红：换节点重测。
- 某网站没走代理：连接页看链路与命中规则，切全局可定位是规则还是节点问题。
- 软件异常：备份并删除配置目录重启即恢复（官方指引）。
