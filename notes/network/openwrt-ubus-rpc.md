# OpenWrt / ImmortalWrt 路由器 ubus RPC 速查


> **适用平台**：OpenWrt 系路由器（ubus + dropbear）  
> **一句话**：SSH 掉线时还能用 ubus RPC 读文件、改配置、重启服务——先记住这条后路。  
> **标签**：openwrt, ubus, rpc, ssh

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

后台被 ACL 限制、SSH 又掉线时，直接用 HTTP JSON-RPC 读写路由器——LuCI 后台本身就是这套。

## 调用骨架

```python
import requests
base = "http://<LAN IP>/ubus"          # 用 /ubus；/cgi-bin/luci/admin/ubus 会因 ACL 返回 Access denied
s = requests.Session(); s.verify = False

login = s.post(base, json={"jsonrpc": "2.0", "id": 1, "method": "call",
    "params": ["00000000000000000000000000000000", "session", "login",
               {"username": "root", "password": "<口令>"}]},
    headers={"Content-Type": "application/json"}, timeout=15).json()
tok = login["result"][1]["ubus_rpc_session"]

def rpc(ns, method, args):
    return s.post(base, json={"jsonrpc": "2.0", "id": 1, "method": "call",
        "params": [tok, ns, method, args]},
        headers={"Content-Type": "application/json"}, timeout=20).json()
```

- namespace 与 method **分开传**；写成 `"uci.set"` 单串会 `-32700 Parse error`。
- root 空口令时 `password` 传任意值即可（LuCI 对空口令直接放行）。

## 实测可用的调用

| 调用 | 用途 |
|---|---|
| `rpc("uci","get",{"config":"network"})` | 读整份配置（带 `.name`/`.type`/`.index`） |
| `rpc("uci","set",{"config":..,"section":..,"option":..,"value":..})` | 改单值，返回 `[0]` |
| `rpc("uci","add",{"config":"dhcp","type":"host"})` | 新增段，随后用 `dhcp.@host[-1]` 继续 set |
| `rpc("uci","delete",{...})` | 删选项/段 |
| `rpc("uci","apply",{"rollback":False,"timeout":30})` | **提交并生效**；`commit` 不在 ACL 里 |
| `rpc("file","read",{"path":"/etc/config/network"})` | 返回 `[0,{"data":...}]` |
| `rpc("file","write",{"path":..,"data":..})` | 返回非负 fd 即成功 |
| `rpc("rc","list",{})` | 服务清单 + `running` 标志 |
| `rpc("rc","init",{"name":"dropbear","action":"restart"})` | 重启服务——字段是 **name** |
| `rpc("luci-rpc","getDHCPLeases",{})` | 租约（v4+v6） |
| `rpc("hostapd.phy0-ap0","del_client",{"addr":"<MAC>","deauth":True,"reason":5,"ban_time":0})` | 踢无线客户端逼它重新 DHCP |
| `rpc("system","board",{})` / `rpc("system","info",{})` | 型号 / 固件 / 内存 |

## 写文件的 ACL 白名单

`file.write` / `file.read` 只对白名单路径开放。实测可写：`/etc/dropbear/authorized_keys`、`/etc/rc.local`、`/tmp/*`。
`/etc/config/*` 通常**不在**白名单里——改配置走 `uci set`，不要硬写配置文件（写了也不会被 netifd 吃进去）。

## 对象名怎么找

- 无线 hostapd 对象：`ubus list | grep hostapd`（通常是 `hostapd.phy0-ap0` = 5G，`hostapd.phy1-ap0` = 2.4G）。
- 服务是否在跑：`rpc("rc","list")` 的 `running` 字段，比看日志快。
- MAC → 交换机口：SSH 跑 `brctl showmacs br-lan`（WiFi 侧是独立 port 号）。

## SSH 掉线时的判断顺序

1. `rpc("rc","list")` 看 dropbear 是否 running。
2. 端口是 **RST（"积极拒绝"）** 而非超时 → 没有监听，不是防火墙问题。
3. `rpc("uci","get",{"config":"dropbear","section":"main"})`：有 `DirectInterface` 就删掉再重启（LAN 地址变更后它会绑到不存在的地址上）。
4. 仍不通再考虑 `wifi reload` / `network reload` 期间的服务启动竞态。
