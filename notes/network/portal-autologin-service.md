

> **适用平台**：Linux 小主机（常驻脚本）+ 校园网 Web 认证  
> **一句话**：探测判据必须用真实站点正文而非 captive 探测 URL；链路不断但会话过期这类掉线要靠物理重连触发。  
> **标签**：portal, autologin, campus-network, watchdog, mab

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# 校园网 Portal 自动重认证服务（部署与运维）

日期已脱敏 起在**小服务器 server-b**（192.168.1.5）上线。目标：宿舍 the old router 专线的 portal 会话掉线后自动登录恢复，不再依赖人工。

## 现场事实（Example University · main campus · campus broadband）

- 宿舍出口 = **a soft-router (OpenWrt-based)**（ImmortalWrt，`192.168.1.1`）：做 portal 认证 + NAT 分网。旧中兴 the old router 已于 日期已脱敏 退役丢弃，但其 WAN MAC `AA:BB:CC:DD:EE:02` 被**克隆沿用**（校园网按 MAC 放行，换机必须沿用）。校园网是**一账号一设备**，路由器就是那"一台设备"。
- 认证平台 = **锐捷新一代 Portal/ePortal + 统一身份认证（LinkID 系 SSO）**：
  - 门户/自服务 `http://10.0.0.254/`（SPA，Angular）；自服务首页 `/self/index`；设备页 `/self/my-devices`（显示在线设备 MAC/IP/无感状态，含「下线」「注册无感/关闭无感」按钮）。
  - SSO 登录页 `http://10.0.0.254/pc/center?service=...`（`#nameInput` + `input[type=password]` + 隐私复选框 + 「立即登录」）。
  - SSO 服务器名：`/sam-sso/api/sso/server/name` → `http://10.0.0.254/cas-sso`。
  - 可达 API 前缀：`/sam/api/...`（`/sam/api/protected/...` 直出 JSON；`/sam/api/userself/...` 响应体是 **AES 加密的 base64 块**）。
  - 登录/保活接口名（在 SPA bundle 里）：`/portal/portalAuthen/login`、`/portal/portalAuthen/keepAlive`、`/eportal/network/offline`、`/portal/mabAuthen/getNoPerceptualList`（无感认证）、`/portal/user/userbind/getMaxBindNumber`（绑定上限）。**请求体为 AES-CBC 加密**（头 `isPortal: true, encrypted: true`），所以只走浏览器自动化，不要手写协议。
  - 聚合网关写在 bundle 里是 `10.0.0.35:9999/api/aggregation`，**学生网不可达**，别在这条路上耗时间。
- 无感认证（MAB）：自助中心可对某设备「注册无感」。⚠️ **MAB 只在链路 up 时触发**；链路不断但服务端会话过期/换 IP（校园侧看到的是 `10.0.0.1` 这类校园内网地址）→ 不会重新触发 → 表现为"偶尔要手动登录"。

## 部署物

| 文件 | 说明 |
|---|---|
| `~/campus_autologin.py` | 主脚本：探测外网 → 未通则登录 → 复测 → 记录；`--test-login` 只测登录不改网络，`--status` 看状态 |
| `~/.campus_cred` | 两行：账号 / 密码（`chmod 600`）|
| `~/campus_autologin.log` / `.state` | 日志 / 状态（last_ok、fails、last_try_ts）|
| `/etc/systemd/system/campus-autologin.{service,timer}` | 每 2 分钟跑一次（OnBootSec=3min）|

关键设计：**探测用纯 urllib（快）+ 只在断网时才起 headless Chrome**；`COOLDOWN=300s`、连续失败退避 1800s（**防锁号**）；登录策略先 A（`/self/index` 自助中心）后 B（门户页）。

## 运维命令

```bash
python3 ~/campus_autologin.py --status          # 状态
python3 ~/campus_autologin.py --test-login      # 只测登录链路
systemctl list-timers campus-autologin.timer    # 计时器
journalctl -u campus-autologin.service -n 20    # 最近执行
sudo systemctl disable --now campus-autologin.timer   # 停用
```

## 断链恢复（日期已脱敏 实装 your-router）：物理弹 WAN 重触发 MAB，不碰密码

现役手段 = 路由器 `/usr/bin/wan_mab_watchdog.sh`（cron `*/1`，日期已脱敏 晚从 `*/3` 提到每分钟）：抓真实站点正文 → 连续 2 次判定被门户劫持 → `ip link set wan down` 等 25s + `up` → 复测；冷却 15min、弹失败退避 30min 起（上限 2h）；日志 `/etc/wan_mab.log`、状态 `/etc/wan_mab.state`；`--status/--test/--force` 三个手工入口。已进 `/etc/sysupgrade.conf` 保留清单。

**保活纪律（日期已脱敏 定，与看门狗配套）**：`/usr/bin/wan_keepalive.sh`（cron `*/1`）每分钟从 WAN 口 ping 校园网关一次（纯保活、成功零输出、失败记 `/etc/wan_keepalive.log`）。理由见下节：平台闲置探测缺省 180s，NAT 后的路由器"长时间只转不发"会被判闲置并把会话收走。**任何改动都要保证：从 WAN 口发出的真实流量间隔 ≤120 秒。**

- **探测铁律：别用 captive 探测 URL**（`connect.rom.miui.com/generate_204` 之类）——校园网常把它放进**免认证白名单**，未认证时也回 204，脚本于是永远判"网络正常"、从不触发登录（本机 9/15 那版就栽在这：日志一路"网络正常——本轮无需登录"，实际全网被劫持）。判据必须是**真实站点正文**，并检 `10.0.0.254` 劫持标记。
- **MAB 重触发要物理 link down**：`ifdown/ifup` 不动 PHY，校园网 NAC 看不到 link flap → 不触发；必须 `ip link set <wan> down`。生效有延迟（实测数十秒到几分钟，别急着判失败）。
- 自助中心 `/self/index` 登录**不恢复线路**（9/16 六次实测证伪）；真正管用的只有设备门户认证或 MAB。
- 弹 WAN 不是万能：MAB 失效或校园网转强制门户登录时，看门狗会一直弹（退避到 2h 上限）而链路不恢复——那时才需要门户登录方案（见下节）。

## 坑位

- **别反复试密码**：SSO 失败会弹 `captcha_code` 验证码字段，脚本随即失效；路由器（the old router）3 次登录失败会锁 30~60 秒。
- the old router 超管口令：`CMCCAdmin/aDm8H%MdA`、`CMCCAdmin/CMCCAdminWoTf6&$7`、`useradmin/useradmin` 均**实测失败**（移动装维已改）；后可试标签上的普通用户口令，或 ZTE 免密路径（`/cgi-bin/telnetenable.cgi?telnetenable=1&key=<MAC大写无分隔>` → telnet root/`Fh@<MAC后6位>` → `sendcmd 1 DB p DevAuthInfo`）。
- 小服务器没有 chromium 包但有 **google-chrome-stable** → Playwright 用 `channel='chrome'`，别 `playwright install chromium`（省 150MB 下载）。
- 登录页/门户页会拦截 http 请求做重定向：探测外网时要判 `10.0.0.254` 出现在最终 URL = 未认证。
- 通知可选：脚本读 `CHAT_BRIDGE_HTTP`/`CHAT_BRIDGE_TOKEN`/`CHAT_BRIDGE_TARGET` 环境变量走 chat-bridge `send_private_msg`；未配置只写日志。

## 为什么"自助中心里开了无感，照样掉线"（日期已脱敏 机理定案草案）

- **无感 = MAB = 认证服务器记住"这个 MAC 归这个账号"，它不等于会话永续。** 在线会话仍归平台侧定时器管：H3C Portal 缺省 `idle=180s`（闲置 3 分钟无该 MAC 报文就发 ARP/ICMP 探测，`interval=3s`、`retry=3`，不应答即强制下线），另有 `offline-detect=300s`。
- 路由器是 NAT 网关，**内网设备流量对校园网是"被转发"，路由器自己可能长时间不发包** → 被判闲置 → 会话被收走；**会话被收走后 MAB 不会自己把会话拉回来**（MAB 只在链路/端口事件或新的认证触发时才生效）→ 表面上就是"无感开了也没用"。
- 现场对照：探测间隔从 3 分钟改到 1 分钟后，链路连续在线 60+ 分钟无掉线（此前 3 分钟档在 22:33 掉过一次）。**强相关，尚待整夜日志定论**——所以要靠 1 分钟保活 + 看门狗兜底双保险，别只靠其中一个。
- 自助中心 `/self/my-devices` 页可直接看到"无感"是否开着、绑的哪个 MAC、在线时长、最近上线时间——排查无感问题先看这一页，别再猜。

## 笔记本侧：为什么"断网自动切 WiFi"做不到（日期已脱敏 实测）

- the harness process**没有管理员权限**：`netsh interface ipv4 set interface <idx> metric=...` 返回 "请求的操作需要提升" → **改不了接口优先级**，笔记本在校园网断时只能靠 Windows 自身的 NLA/NCSI 失败转移（数十秒级，且当场在途的连接会断）。
- 要做到"断网无感"，二选一（都需用户在场）：①**提权**把 WLAN 的 InterfaceMetric 调到低于有线（如 WLAN=10 / 有线=25）→ 笔记本上网优先走热点；②在**路由器上做双 WAN 故障切换**（手机热点当备份出口），Windows 侧完全无感——这是最正的架构。
- 在没做上面两件事之前，抗断网的正确姿势是**把活交给 cron**：定时任务跑在全新会话里，断网只让"这一次"失败，下一次到点自己重跑，不依赖当前对话存活。
