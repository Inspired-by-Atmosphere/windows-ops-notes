

> **适用平台**：OpenWrt / ImmortalWrt 软路由（1WAN+4LAN，WiFi6 双频）  
> **一句话**：在产链路上做任何改动前先拿到可持续的 root 通道，再谈 MAC 克隆、网段迁移与备份。  
> **标签**：openwrt, immortalwrt, router, portal, mac-clone

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# 校园网出口软路由管理（Portal 认证 + WiFi + LAN 迁移）

配套：
- `openwrt-ubus-rpc.md`（ubus RPC 调用形状、ACL 白名单、踢客户端/查租约的现成调用）。
- `openwrt-ipq6018-ecosystem.md`（这台机器的软件生态实测：可装/禁装清单、缺 tun 驱动怎么办、apk 源 404、2G loop rootfs + 无 swap 的取舍、NSS 与 flow offloading 的关系）。

## When to Use

宿舍出口软路由/路由器替换、校园网新路由认证恢复、WiFi 双频配置、LAN 网段迁移、内网设备恢复上线。

## 交互纪律（先读这条）

- **能自己动手就不要给用户点菜单**。改网段、开 DHCP、配 WiFi、写静态租约、重启服务，全部可以用 ubus RPC 或 SSH 办完；交付「你去后台点 X 再点 Y」会被反问「这些不能你去办吗」。只有必须用户本人输入的（后台管理员口令）才交给用户，其余先办完再汇报。
- **指后台页面位置前先确认版本**。LuCI 25.x：「网络 → DHCP/DNS → 常规」是 dnsmasq 全局设置（没有起始/数量字段）；单接口 DHCP（起始/数量/租期）在「网络 → 接口 → LAN → 修改 → **DHCP 服务器**」标签页。指错页面比不指更糟。
- 汇报只给实测证据（见文末验收清单），不说"应该好了"。

## 核心原则

1. **认证对象是 WAN 口 MAC，不是设备**：校园网一人一设备，认证的是出口路由器的 WAN MAC。换路由后第一优先级是把新路由 WAN MAC 克隆成原路由 WAN MAC。
2. **新路由插上后会先被关进隔离网段**：表现为 TCP 全丢、DNS 不通、门户不可达。此时跑登录脚本无效，必须先完成 MAC 克隆。
3. **旧设备克隆 MAC 后不能再通电**：两台同 MAC 同时在线会造成冲突。
4. **内网静态地址是约定，别改设备**：小服务器/开发板/大服务器按固定 IP 写死在用户的脚本和文档里。新路由要把 LAN 网段改回原值、用 DHCP 静态租约把设备地址钉回去，而不是去设备上改 IP。

## 典型现场（Example University · main campus · campus broadband）

- 出口路由器：**a soft-router (OpenWrt-based)**（Qualcomm IPQ6018，ImmortalWrt SNAPSHOT，LuCI 25.x，1WAN+4LAN 千兆，WiFi6 双频）；前身an older consumer router（WAN MAC `AA:BB:CC:DD:EE:02`，校园网地址 `10.0.0.0/20`，网关 `10.0.0.254`）。
- 校园网认证：a vendor captive portal (ePortal / SSO)，门户 `http://10.0.0.254/`。认证请求体 AES-CBC 加密，**只走浏览器自动化**，不要手写协议；若协议解密失败，优先改用浏览器自动化完整回放登录流程。
- 聚合网关 `10.0.0.35:9999/api/aggregation` 学生网不可达，不要在这条路上耗时间。
- 内网约定：小服务器 `192.168.1.5`、大服务器 server-a `192.168.1.2`、the SBC node `192.168.1.15`（走 5G 无线）。

## 操作流程

### 1. 先拿到 root 通道（后面全靠它）

**优先用 SSH 免密，不靠 Web 后台**。Web 登录在 LuCI 空口令/ACL 异常时会失效，而 SSH 免密密钥不依赖口令。建立流程：

```bash
# a) 生成专用密钥
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_<别名> -N "" -C "admin@<src>-to-<dst>"

# b) 用 ubus file.write 写入（ImmortalWrt/apk 上 /etc/dropbear/authorized_keys ACL 可写）
#    rpc("file","write",{"path":"/etc/dropbear/authorized_keys","data":"<pubkey>\n"})
#    rpc("file","read",{"path":"/etc/dropbear/authorized_keys"})   # 读回校验

# c) 本机 ~/.ssh/config 加别名（支持环境变量 HOST，便于脚本复用）
#    Host <别名>
#        HostName <路由器 LAN IP>
#        User root
#        IdentityFile ~/.ssh/id_ed25519_<别名>
#        StrictHostKeyChecking accept-new
```

如果路由器有旧配置残留（`/etc/dropbear/authorized_keys` 非空），先 `read` 再 `write` 覆盖；清空重写时注意权限（通常 root 拥有）。密钥写入后立即 `ssh <别名> 'echo OK'` 验证，不要存疑继续用 Web。

> **坑位**：dropbear 有 `DirectInterface='lan'` 时，LAN 地址一变 22 端口立刻拒连，而 `rc list` 仍显示 running——删掉该选项 + commit + 重启 dropbear 即可，不要误判成 dropbear 挂了。
> **坑位**：`/etc/shadow` 里 root 为空时 LuCI/SSH 直接放行，任何能连上 LAN 的设备都能拿管理员。部署完提醒用户设口令（口令由用户本人设，不经你的手）。

### 2. WAN MAC 克隆（校园网认证）

```bash
uci set network.wan.macaddr='<原路由器 WAN MAC>'
uci commit network
ifup wan          # 或 rpc("rc","init",{"name":"network","action":"restart"})
```

验证：WAN 拿到校园网地址、`uclient-fetch http://www.baidu.com` 通、DNS 正常 = MAB 认证通过。

### 2b. 掉线恢复：物理弹 WAN 重触发 MAB（首选，不用账号密码）

校园网会把会话过期/换过 IP 的设备踢回未认证状态。症状是**看起来"半通"**：DNS 仍能解析、网关 ARP 仍
REACHABLE，但其它 TCP/ICMP 全被挡（`uclient-fetch` 报 `Failed to send request: Operation not permitted`），
访问任意 http 站点被 JS 跳转到 `http://10.0.0.254/eportal/index.jsp?...`。

此时**不必登录门户**——只要让校园网 NAC 看到一次真实链路事件，就会重新触发 MAC 无感认证（MAB）：

```bash
ip link set wan down; sleep 25; ip link set wan up    # 必须物理层 down/up
sleep 30                                              # MAB 生效有延迟，别刚 up 就判定失败
uclient-fetch -T 15 -O - http://www.baidu.com | grep -q 10.0.0.254 && echo 仍被劫持 || echo 已认证
```

- **`ifdown wan; ifup wan` 救不了这种状态**：netifd 重跑 proto 但 PHY 不 down，NAC 看不到链路事件，不会重触发。
  MAC 克隆只能救"首次接入"，救不了"会话过期"。
- 弹 WAN 期间 LAN 与内网服务不受影响，只有外网断约 1 分钟。

保活可以直接做在路由器本地，写成"探测到被劫持 → 物理弹 WAN → 冷却/退避"的看门狗，**完全不涉及账号密码、
不改任何网络配置**。可直接复用的实现：`../scripts/wan_mab_watchdog.sh`（去抖 2 次、冷却 15 分钟、弹失败退避
30 分钟起上限 2 小时、单实例锁、`--status/--test/--force` 三个手动入口）。**cron 间隔必须 ≤120 秒**（现用 `*/1`）——探测本身就是会话保活，3 分钟档实测会掉线，见 2d。

> 旧的门户登录方案（浏览器自动化 + 账号密码）仍保留作为兜底，但它会带来验证码/锁号风险；
> **先试弹 WAN 这条不需要凭据的路**，不通再动浏览器。

### 2c. 判"认证状态"的两条铁律

- **看内容，不看状态码**：劫持页是 HTTP 200 + 正文里一段 JS 跳转，最终 URL 往往仍是你请求的那个地址。
  判据取响应正文里有没有 `10.0.0.254`。
- **在持有这条上行链路的那台机器上探**：下游设备（小服务器/开发板）自己可能还有第二条默认路由（比如它自己的
  WiFi/热点，`ip route` 里 metric 更小），它报"网络正常"只说明它自己通，不代表宿舍出口通。

### 2d. 无感/MAB「开了也掉线」的机理：绑定表项 ≠ 在线会话

- 无感（MAB）只是认证服务器记住 MAC↔账号 的绑定；**在线会话另外归平台侧定时器管**：企业级 Portal 平台默认「闲置探测 `idle` 180 s、间隔 3 s、重试 3 次」+「下线探测 `offline-detect` 300 s」——闲置约 3 分钟即被 ARP/ICMP 探，连续不应答就强制下线。**表项还在、会话已经死了**，这就是"无感开着却像没用"的机理。
- **现场怎么踩中的**：软路由是 NAT 网关，内网设备的流量在校园网侧只是"被转发"，出口自己"很安静"→ 判闲置 → 会话被收走；收走后 MAB 不会自动重新拉起（只在链路/端口事件、新认证触发时才生效）。所以"无感不工作"多半不是绑定问题，是保活问题。
- **探测与保活二合一**：让出口每 ≤120 秒有真实流量出去（低于 180 s 闲置阈值）。实测把看门狗探测间隔从 3 分钟降到 1 分钟后，链路连续在线 60+ 分钟不再掉（同期 3 分钟档掉过一次）。保活动作可以更轻——对网关 arping、发一个真实 DNS 查询即可，不必真抓网页。
- **断链后别指望"软触发"**：DHCP 续约（`kill -USR1 udhcpc`）不改 IP 时不重新认证；`ifdown/ifup` 不动 PHY 无效。已验证有效的零凭据手段只有物理弹 WAN。**会话在 → 用心跳保活；会话没了 → 弹 WAN。**

### 2e. 在产链路（整栋宿舍唯一出口）上做侵入实验的安全姿势

验证"是不是闲置回收""弹 3 秒够不够"这类问题必须让链路真掉一次，直接改生产看门狗会把自己和所有内网设备一起断掉。

1. 先备份 crontab：`cp /etc/crontabs/root /etc/crontabs/root.bak-<窗口名>`。
2. 把弹链路那条 cron 换成**只观察**的探测脚本（绝不碰链路），恢复脚本挂成**一次性 cron 兜底**（如 `59 0 * * * /usr/bin/<restore>.sh`）。cron 兜底跨重启有效，比 `nohup sleep ... &` 可靠；恢复脚本从备份还原 crontab + `cron restart`，还原后它自己那行也消失，天然一次性。
3. 给观察脚本留**升级出口**：连续被劫持 N 分钟且自救失败时，自己调恢复脚本 + 跑一次 `--force` 弹 WAN——保证实验失败最多断十几分钟，不会挂一整夜。
4. **观察窗本身就是污染源**：任何探测都要走 WAN，等于持续保活，所以"窗口内没掉线"**不能**读成"平台会自己恢复"。要答这个问题只能停掉保活或另设对照。
5. 汇报时写清窗口、兜底机制与最坏断网时长。用户准的可能是"断几十秒"，别把它默默放大到十分钟。
6. 若笔记本是唯一观测端，**先给它备一条独立出口**（手机热点等）：外网全走有线时，链路一断 agent 自己也掉线，实验就只能盲跑。救援动作教给用户一句：**拔掉笔记本网线**，默认路由回落到热点，agent 立刻恢复。

### 3. 改 LAN 网段 + 开 DHCP

- 目标：LAN 回原网段（如 `192.168.1.1/24`），DHCP 池避开静态设备（例：起 `100`、数 `150`、租期 `12h`）。
- 用 `uci set` 改完再一次性 reload；`uci commit` 走 ubus 会被拒，用 `uci apply`。
- reload 后立刻用新地址继续操作；**Windows 客户端必须断连/重连网卡**（或 `ipconfig /release` + `/renew`）才会拿新网段地址——不要因为客户端还停在旧地址就以为路由器没改成功。

### 4. WiFi 配置（双频分开命名，历史名对齐）

```bash
uci set wireless.radio0.country='CN'                    # 两个 radio 都要设
uci set wireless.default_radio0.ssid='<SSID-5G>'
uci set wireless.default_radio0.encryption='psk2'
uci set wireless.default_radio0.key='<口令>'
uci set wireless.radio1.country='CN'
uci set wireless.default_radio1.ssid='<SSID-2.4G>'
uci set wireless.default_radio1.encryption='psk2'
uci set wireless.default_radio1.key='<口令>'
uci commit wireless && wifi reload
```

- **SSID 名必须和用户设备的历史名对齐**：开发板/手机记的是旧 SSID，改名 = 它再也不自动回连。先从用户机器上取历史名（Windows `netsh wlan show profiles` 就是历史 SSID 列表），能沿用就沿用；Windows 中文输出**别接 `iconv | grep` 管道**（会静默空结果），用 Python 捕获 stdout 后按 gbk 解码再筛。
- 用户先说"双频同名"后改口"分频段"很常见：改名只是一条 `uci set ssid` + `wifi reload`，按最新要求做，别为改不改纠结。
- 校验：`iwinfo phy0-ap0 info` / `phy1-ap0 info` 看 ESSID/Channel/Tx-Power；核对密钥用哈希比对，不要把口令回显到汇报里。
- 无线硬件有 `country` 未设会让部分信道/功率受限；2.4G 常漏设，两个都补。
- **密钥一致性校验**：改完 WiFi 后必须做哈希比对（`echo -n "<口令>" | sha256sum | cut -c1-12`），不要只看 iwinfo 里显示 "已设密钥"就认为和用户要求一致。

### 5. 内网设备地址钉死 + 强制重取

静态租约写在 `/etc/config/dhcp` 的 `host` 段，重启路由器也会保留。

```bash
# 静态租约（MAC 从 /tmp/dhcp.leases 或 brctl showmacs br-lan 取）
while uci -q delete dhcp.@host[0]; do :; done   # 幂等清理旧段（可选）
uci add dhcp host
uci set dhcp.@host[-1].name='<主机名>'
uci set dhcp.@host[-1].mac='<MAC>'; uci set dhcp.@host[-1].ip='<固定IP>'
uci commit dhcp; /etc/init.d/dnsmasq restart

# 无线客户端：踢下线，它重连时会重新 DHCP 并拿到新租约
ubus call hostapd.<phy>.del_client '{"addr":"<MAC>","deauth":true,"reason":5,"ban_time":0}'

# 有线客户端：弹它所在的交换机口
ip link set lan2 down; sleep 4; ip link set lan2 up
```

端口归属先用 `brctl showmacs br-lan` 确认（WiFi 侧是独立 port 号），别乱弹别的口。写完之后检查 `/tmp/dhcp.leases` 里的 `expires` 字段是否从 `0` 变成正常时间戳；`0` = 租约刚写入但客户端还没重连。

> **坑位**：`uci delete dhcp.lan` 之类会整段误删；静态租约一定用 `uci add dhcp host` 追加，不要改 `dhcp.lan` 段本身。

### 6. 备份与恢复

```bash
sysupgrade -b /root/backup.tar.gz              # 备份全配置
sysupgrade --restore-backup /tmp/backup.tar.gz # 恢复
```

## 坑位

- **rpcd 的 `rc` 插件字段是 `name` 不是 `service`**：传 `service` 返回 code 2 且**什么也不做**——服务照样显示 running，你以为重启了其实没有。排查"重启没生效"先核对字段名。
- **`uci commit` 不在 ubus ACL 里**（返回 `Access denied`），改用 `uci apply {"rollback":false,"timeout":30}`；`uci set/add/delete` 是允许的。
- **dropbear 有 `DirectInterface='lan'` 时，LAN 地址一变 22 端口立刻拒连**，而 `rc list` 仍显示 running：删掉该选项 + commit + 重启 dropbear 即可，不要误判成 dropbear 挂了或防火墙拦了。
- **ubus 的 namespace 和 method 必须分开传**：`["call",[tok,"uci","set",{...}]]`。把 `uci.set` 当整串方法名会得到 `-32700 Parse error`。
- **`file.write` 返回非负数（0 或 fd 号）即成功**，不是错误码；写完要 `rc init`/`uci apply` 才生效。
- **门户劫持页会被误当成路由器响应**：请求一个路由器已经不再持有的旧 LAN IP 时，包按默认路由出去，被校园网 HTTP 劫持成 `location.href="http://10.0.0.254/eportal/index.jsp?wlanuserip=..."` 的跳转页。看到它应先怀疑"这个 IP 已经不在路由器上了"，而不是后台坏了。认准路由器本体：`/cgi-bin/luci/` 返回 `ImmortalWrt - LuCI`。
- **netifd 可能保留旧地址**：reload 后 `ip addr` 还显示双 IP 时，用 `network.interface.lan` 的 `uptime`/`updated` 判断是否真的重启过，必要时重启接口——别反复写配置。
- **旧路由器退役后不要再通电**（MAC 冲突）。
- **别用"源地址绑定"的探测结果判定某条链路是死的**：笔记本同时插网线+连热点时会有两条默认路由，
  `curl --interface <有线IP>` / `ping -S <有线IP>` 的失败常是绑定伪影（弱主机模型下包仍可能从别的网卡出去），
  不等于那条路真不通。拿权威结论用 `Find-NetRoute -RemoteIPAddress <目标IP>`（它给出的 InterfaceAlias +
  IPAddress 才是 Windows 实际会用的路由与源地址），再用**不绑网卡**的请求测通断。切换链路/拔插网线后先固定这一步，
  否则会把"这条路上不了网"误判成 MTU 黑洞之类的伪根因。
- **给路由器推脚本别用 scp**：dropbear 多数没装 sftp-server（报 `ash: /usr/libexec/sftp-server: not found` +
  `Connection closed`）→ 用 `ssh <别名> 'cat > /路径/脚本.sh' < 本地脚本.sh` 传输（可在同一条命令里接
  `chmod +x` 和 `sh -n` 语法检查），比换协议省事。
- **固件里没有 curl**（本机 ImmortalWrt）：可用的是 `uclient-fetch`（`-T 超时 -O -` 打 stdout）与 `wget`。
  写探测/看门狗脚本按 busybox 能力写，别按桌面 Linux 的 curl 习惯写。
- **路由器上的脚本一律纯 ASCII 英文**（用户规矩 + busybox ash 更挑剔）：单行 case 分支、`$(...)` 里带括号等
  写法在 busybox ash 直接 `syntax error: unexpected "("`；中文串也会让排查更乱。部署后先 `sh -n 脚本` 再跑。
- **持久化位置**：定时任务写 `/etc/crontabs/root` + `/etc/init.d/cron restart`（cron 默认 enabled）；自己加的
  脚本/日志/状态文件必须写进 `/etc/sysupgrade.conf`（该文件默认空白）才会在刷机/升级后保留。
- **审批门会因超时静默作废**：向路由器 `/etc` 写文件、重启服务这类改动会弹确认，用户不在场时 5 分钟到期即作废
  （≠ 已同意）。发起远程写操作前先在对话里说明"要写哪些文件 + 怎么回滚"，等用户在场；超时后不要重试原命令，
  先把待办和回滚方式讲清楚。
- **后台 root 空口令**：`/etc/shadow` 里 root 为空时 LuCI/SSH 直接放行，任何能连上 LAN 的设备都能拿管理员。部署完提醒用户设口令（口令由用户本人设，不经你的手）。

## 验收清单（汇报前逐条实测）

```bash
ssh <别名> 'uci show wireless | grep -E "ssid|encryption"; \
  iwinfo phy0-ap0 info | grep -E "ESSID|Channel|Tx-Power"; \
  iwinfo phy1-ap0 info | grep -E "ESSID|Channel|Tx-Power"; \
  cat /tmp/dhcp.leases; ip neigh show dev br-lan; \
  brctl showmacs br-lan; \
  uclient-fetch -q -O /dev/null http://www.baidu.com && echo 外网OK'
# 客户端侧
ping -n 2 <静态设备IP>            # 内网设备是否在线
curl -s https://myip.ipip.net     # 笔记本默认出口是否合意
ssh <设备别名> 'ip -4 -br addr'    # 设备自己的地址/网关/DNS
```
