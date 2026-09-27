

> **适用平台**：Windows 10 / 11（有线 + 无线 + TUN 代理并存）  
> **一句话**：代理软件只管走它的流量，直连请求根本不进代理——所以要修的是直连路径，不是代理配置。  
> **标签**：windows, routing, proxy, multi-wan, mtu

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# Windows 多 WAN 代理路由冲突修复

## When to Use

- 笔记本同时连有线 + WiFi/热点，出现两条默认路由（metric 均为 0）
- app/Clash 请求间歇性超时、fallback、被 RST
- 切换网线/热点后部分模型通道莫名失效
- 校园网/办公网有线路径对 TLS/大包不通，但热点正常

## 诊断流程（先分层再动手）

1. **确认多默认路由**
   ```powershell
   Get-NetRoute -AddressFamily IPv4 -DestinationPrefix 0.0.0.0/0
   ```
   若出现多条 NextHop，且 InterfaceMetric 都是 0，就是竞争态。

2. **确认 which path the client actually takes**
   ```powershell
   Find-NetRoute -RemoteIPAddress <目标IP> | Select-Object -First 2 IPAddress,InterfaceAlias,NextHop,RouteMetric | Format-Table -AutoSize
   ```
   不带 `-InterfaceAddress` 参数时，Windows 会返回**实际选中的路由**，不是全部候选。

3. **按源地址对比两条路的真实传输能力**
   不要只测 TCP 连通性；大请求/大包会暴露 MTU 黑洞。
   ```bash
   # 不绑网卡（走默认路由）
   curl -s --ssl-no-revoke --noproxy '*' -o /dev/null -m 12 -w "直连: %{http_code} (%{time_total}s)" https://目标/api

   # 强制走热点源地址（Windows 路由 metric 较小的那个）
   curl -s --ssl-no-revoke --interface <热点IP> --noproxy '*' -o /dev/null -m 12 -w "热点: %{http_code} (%{time_total}s)" https://目标/api

   # 如果两条路小请求都通，测大包（MTU 黑洞只杀大包）
   ping -S <源IP> -n 2 -w 2000 -f -l 1472 <公网IP>
   ```
   大包全丢、小包全通 = MTU 黑洞（通常出在校园网/运营商 NAT 链路上）。

4. **判断是路径问题还是通道问题**
   - 热点路通、有线路不通 → 路径问题，修路由
   - 两条路都通、the client still falls back → 检查 the harness fallback 链配置（见坑位）

## 不要用 routing-mark 锁网卡（此路不通）

⚠️ 本技能上一版写在这里的「加 `routing-mark: <metric>` 把 Clash 出站锁到指定网卡」是**错的方向，不要再用**：

- `routing-mark` 是 mihomo 的 **Linux fwmark** 语义项，Windows 无此机制；写进 config.yaml 得到"配置已保存 + 内核重启成功"只说明配置被接受，**不说明出口变了**。
- 更根本的：**Clash 只管走它的流量**。the app 以及其它程序的直连请求（不读代理环境变量）根本不进 mihomo，改 mihomo 配置影响不到它们——而"插上有线就 fallback"恰恰是这些直连请求打进了那条死路，所以要修的是**直连路径**，不是代理配置。
- 判断出口到底变没变，只看路由层证据：`Find-NetRoute -RemoteIPAddress <目标IP>` 的实际 InterfaceAlias/IPAddress，或看对端看到的源 IP。别把「改完配置+重启成功」当验收。

真正能左右直连出口的手段在下面「替代方案」里（路由 metric / 删掉死路的默认路由 / 把那条上行链路本身修好）。

**步骤**

1. 查目标网卡的 metric（如热点 WLAN metric=50）
   ```powershell
   netsh interface ipv4 show interfaces
   ```

2. 编辑 Clash Verge 配置：
   ```yaml
   # %APPDATA%\io.github.clash-verge-rev.clash-verge-rev\config.yaml
   external-controller: 127.0.0.1:9097
   routing-mark: 50        # ← 加这一行，值=目标网卡的 RouteMetric
   external-controller-pipe: \\.\pipe\verge-mihomo
   ```

3. 重启 Clash 核心生效：
   ```bash
   python "%USERPROFILE%/AppData/Local/app/skills/troubleshooting/clash-verge-ctl/<clash-verge-cli>" restart
   ```

4. 验证：重复步骤 3 的测试，确认所有流量走锁定网卡。

**恢复默认**：删掉 `routing-mark` 行，重启 Clash。

## 替代方案（直连流量的出口由路由决定）

1. **修改路由 metric**：给热点加更低的 metric（如 10），有线保留 25
   ```powershell
   Set-NetRoute -DestinationPrefix 0.0.0.0/0 -InterfaceAlias WLAN -RouteMetric 10
   ```

2. **删除有线默认路由**（适合固定位置使用）：
   ```powershell
   Remove-NetRoute -DestinationPrefix 0.0.0.0/0 -InterfaceAlias '以太网 3' -Confirm:$false
   ```

3. **Clash TUN 模式**：开 TUN 后 Clash 自己管理路由表，但 TUN 本身会接管默认路由，解决路径竞争（代价是 gVisor TUN 有性能开销）。

## 坑位

- **fallback-chain de-duplication**：如果两个 provider 的 `base_url` 完全相同，the harness 会判定为同一后端并跳过 fallback（日志 `Fallback skip: ... resolves to the same backend`）。这会让一个 provider 失败时直接跳到更远的备用通道，看起来像"a provider being skipped"。修法：给重复 base_url 的 provider 加不同的 `base_url` 或删掉重复项——**自定义 provider 别名之间永远做不到"接力"**，源码机制与链序纪律（CN 直连通道排在境外通道前）见 app-model-channels 的「fallback_providers 重排」节。
- **MTU 黑洞只在出校园网方向出现**：内网 ping 192.168.1.x 全通，不代表外网也通。校园网 NAT 链路常把 MTU 压到 1400 左右，TLS 握手的 ServerCertificate 包被静默丢弃，表现为 HTTPS 大请求超时。解法：让出站走不被压 MTU 的链路（热点/其他出口），或在路由器侧做 MSS clamping（`network.wan.mtu_fix`）。
- **Windows 多默认路由 metric 都是 0 时**，`Find-NetRoute` 不带 `-InterfaceAddress` 会返回候选集合而不是实际选择；判断实际走哪条路必须看第一行的 NextHop/InterfaceAlias。
- **Clash `routing-mark` 不是网卡锁定开关**：Linux fwmark 语义，Windows 上无效，且影响不到不走代理的直连流量 → 要改直连出口请动路由 metric / 删默认路由 / 修上行链路（见上两节）。
- **"有线路不通"先分清是链路态还是 MTU**：校园网把未认证设备关进隔离态时的样子很像 MTU 黑洞——DNS 还通、网关 ARP 还在，但 TCP/ICMP 全被挡、http 请求被 302/JS 跳到门户。**判据取响应正文里有没有门户地址**（别只看超时/状态码），确认是隔离态就去走认证或重触发链路（见 campus-edge-router 的「掉线恢复」节），不要在 MTU/MSS 上耗时间。
- **国内服务保持直连**：`rule` 模式下 CN 目标本来就直连，不要为了"让国内通道稳一点"把它塞进代理——境外节点访问国内 API 额外引入入口 IP 变化/握手被阻/长连接被断的故障面（实测结论：国内 API 走代理反而引入额外故障面）。
- **curl 按接口绑定时**必须用 `--interface <源IP>`，不是 `--interface <网卡名>`。反过来，`--interface <源IP>` 的失败也**不能单独当成"那条路不通"的证据**（弱主机模型下包可能仍从别的网卡出去，是绑定伪影）——先看 `Find-NetRoute` 给出的真实路由与源地址，再用**不绑网卡**的请求复核通断，否则会把"这条路上不了网"误判成 MTU/RST 之类的伪根因。

## 关联

- 代理控制/节点切换：clash-verge-ctl
- 校园网认证：campus-net-autologin
- 网络测速方法论：network-speed-diagnostics
