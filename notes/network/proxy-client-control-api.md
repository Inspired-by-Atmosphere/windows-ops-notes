

> **适用平台**：Windows 10 / 11 + Clash Verge Rev（mihomo 核心）  
> **一句话**：控制 API 走命名管道而不是 HTTP 端口，curl 用不了——用 ctypes 零依赖脚本直接读写管道。  
> **标签**：windows, clash-verge, mihomo, named-pipe, api

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# 通过命名管道控制 Windows 代理客户端（Clash Verge Rev）

程序化控制本机 Clash Verge Rev（mihomo 核心）代理：切节点、切模式(rule/global/direct)、查状态/延迟/连接/配置。本机实测 日期已脱敏。

## 触发场景

- 用户要"切代理节点 / 切模式 / 查代理状态 / 测速 / 接管代理网络环境"
- 需要不开 Clash Verge GUI 就能控制代理

## 关键事实（本机实测）

- 代理软件：Clash Verge Rev（clash-verge.exe + verge-mihomo.exe v1.19.x）
- 代理端口：`7897` mixed HTTP/SOCKS5、`7898` SOCKS、`7899` HTTP；TUN 已开（全系统流量已接管）
- 系统代理关闭；注册表残留 `127.0.0.1:59918` **勿用**
- **控制 API 走 Windows 命名管道 `\\.\pipe\verge-mihomo`**；HTTP 控制端口 9097/9090 默认不监听（verge.yaml `enable_external_controller: false`）→ 不要连 9097
- 配置目录：`%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\`（verge.yaml=GUI 设置；config.yaml=生成的运行配置，含 mixed-port/external-controller/tun/secret）
- secret 在 config.yaml（默认 `set-your-secret`）；mihomo 文档：**命名管道访问不校验 secret**
- 端点：`GET /version /configs /proxies`；`PATCH /configs` `{mode:...}` 切模式；`PUT /proxies/<组>` `{name:<节点>}` 切节点；`GET /proxies/<节点>/delay?timeout=&url=` 测延迟

## 控制通道：HTTP over Named Pipe

curl 不支持 Windows 命名管道。用 `../scripts/mihomo_pipe_api.py`（ctypes 零依赖，已实测打通）：

```
python ../scripts/mihomo_pipe_api.py version   # {"meta":true,"version":"v1.19.29"}
python ../scripts/mihomo_pipe_api.py configs   # 运行配置
python ../scripts/mihomo_pipe_api.py proxies   # 全节点/组列表
```

## 现成轮子（优先用，别再造）

`Hsiifu3/clash-verge-skill`（MIT，纯 Python 零依赖）—— 完整 CLI：status / groups / nodes / select / mode / delay / delay-group / conns / rules / dns / flush-dns / restart / upgrade-geo。

- 原生支持 Unix socket + HTTP；**Windows 需加命名管道传输层**（把 `UnixHTTPConnection` 换成管道客户端，约 60 行）
- 示例：`clash-verge.py select "GLOBAL" "🇯🇵 日本 01 [V]"`；`clash-verge.py mode rule`
- 环境变量覆盖连接：`CLASH_SOCK` / `CLASH_API` / `CLASH_SECRET`

## 用户偏好

- 用户明确要"灵活控制 Clash Verge：切代理模式、换节点"，用现成轮子适配而非从零写（不造轮子铁律）
- 落地方案先交付审批再执行

## Pitfalls

- 别用 `Path(sock).exists()` 判断连接通道——Windows 没有 unix socket 路径
- 先 `netstat -ano | grep 7897` 确认代理在跑（PID=verge-mihomo.exe）
- 切节点前先 `groups` 拿准确组名/节点名（常含 emoji 前缀），请求 URL 需 urlencode
- 改 verge.yaml 后需重启 Clash Verge 才生效
