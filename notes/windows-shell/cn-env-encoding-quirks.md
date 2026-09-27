

> **适用平台**：Windows 10 / 11（中文区域设置，cmd/PowerShell 与 bash/MSYS 混用）  
> **一句话**：中文环境里脚本与补丁老是"匹配失败""报二进制""路径找不到""装不上包"时，先按这五类对号入座。  
> **标签**：windows, encoding, crlf, gbk, china, mirror

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# Windows 中文环境五类坑速查（CRLF / 编码 / 中文路径 / 代理拦截 / 镜像）

本机（Windows 10 + 中文路径 + Clash TUN 代理）反复实证的适配清单。
国外工具 × 中国环境的水土不服（"风水不合"）问题集中处理。
来源：多会话实战（2026-08），每条均为实测解法。

## 触发场景

- 文件编辑报"匹配失败"/"Binary file"、中文路径工具报错、网络请求异常、安装下载慢
- 任何"国外开发工具在中国环境表现异常"的排障

## 五类坑与解法

### 1. 中文/CRLF 文件编辑（patch 匹配失败）
现象：patch 工具 old_string 找不到匹配（仓库文件是 CRLF 行尾，匹配串是 LF）。
解法：改用 python 精确插入：
```python
import io
s = io.open(p, encoding='utf-8').read()
assert anchor in s, 'anchor not found'   # 先断言锚点存在
s = s.replace(anchor, anchor + insert, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(s)
```
预防：`git config --global core.autocrlf true`（提交 LF、检出 CRLF，统一行尾）。

### 2. 编码误判（read_file 报 Binary file）
现象：中文 Windows 输出（ipconfig 等）或混合编码文件被当二进制。
解法：python 依次尝试解码：
```python
for enc in ('utf-8', 'utf-8-sig', 'gbk'):
    try:
        text = data.decode(enc); break
    except UnicodeDecodeError: continue
```

### 3. 中文路径（ripgrep/search_files IO error）
现象：search_files/ripgrep 处理含中文路径报 `IO error / os error 3`。
解法：改用 read_file（Windows 原生路径）或 terminal 的 grep/ls。
注意：Windows 原生 python 不认 MSYS 路径（/c/...），必须用 `C:\...` 原生路径。

### 4. 网络拦截链（Clash TUN + the harness 防护）
- Clash Verge TUN + fake-ip：DNS 全解析到 198.18.0.0/15（局域网 IP 查询要排除 TUN 网卡）
- the harness SSRF guard 误拦私有地址：`security.allow_private_urls: true`（config.yaml；**按进程缓存，改后需重启**）
- `api.github.com` TLS 被 TUN 干扰（SSL UNEXPECTED_EOF）：改用 codeload.github.com / raw.githubusercontent.com / 浏览器工具
- `web_extract` 拦 raw.githubusercontent.com：raw 文件一律 curl
- 显式代理：`--proxy http://127.0.0.1:7897`

### 5. 安装加速（国内镜像）
- npm：`npm config set registry https://registry.npmmirror.com`（淘宝源，npx 装包也走）
- pip/uv：清华源 `https://pypi.tuna.tsinghua.edu.cn/simple`（uv 用 `uv.toml [[index]]` 或 UV_INDEX_URL）
- GitHub 下载：GitCode 镜像 / ghfast.top 前缀
- Electron：官方 install.sh 已内置 fallback `https://npmmirror.com/mirrors/electron/`；可设 ELECTRON_MIRROR
- Docker（如用）：docker.xuanyuan.run 轩辕镜像

### 6. MSYS 路径传给 Windows 原生程序（git/node）被误解析
现象：git-bash 里把 `/e/work/my-project` 传给原生 git clone / node，报 `destination path already exists` 或 `Cannot find module 'E:\e\work\my-project\...'`（多出一个 `e\`）。
原因：MSYS 路径转换对某些原生程序参数不生效（或半转换）。
解法：一律用 Windows 风格路径 `E:/work/my-project`（正斜杠原生程序认）。
注意：bash 内置命令（ls/cd/rm）用 `/e/...` 正常，**只有原生程序（git/node/python）参数用 `E:/...`**。

## Pitfalls

- 先确认现象属于哪一类再动手，避免瞎试
- 网络问题先看代理状态（netstat 查 7897 监听）再排查目标站点
- 改 config.yaml 后记得重启对应进程（SSRF 配置按进程缓存）
- 新增实证的坑 → 补进本技能或反哺地图 local/china-adaptation.md
