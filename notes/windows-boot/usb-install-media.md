

> **适用平台**：Windows（刷盘端）+ 目标机（Linux/Windows 装机端）  
> **一句话**：刷盘前先确认 U 盘物理身份，ISO 双重校验，Ventoy 直拷；把隔着屏幕的用户手动步骤压到最少。  
> **标签**：usb, ventoy, iso, install, dual-boot

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# 启动 U 盘制作与 Linux/Windows 装机全流程

给新机器装系统（如大服务器 server-a）的完整链路：Windows 上刷 U 盘 → 目标机装机 → 驱动/SSH 后置。

## 0. 系统版本选型：禁替用户决定
- Server（无桌面 headless）vs Desktop（图形界面）：**先问用途或按用户习惯**。习惯 Windows 图形界面的用户要 Desktop（教训：擅自推荐 Server 版被批"怎么不是桌面版的"）；只有明确无头 SSH 用途才推荐 Server。
- 官方原版 ISO，禁魔改/精简版。Desktop 版同样能装 NVIDIA 驱动/CUDA/Docker 做训练，只是多个桌面（GNOME 空载 ~1-2G 内存，64G 机器无所谓）。

## 1. 刷盘前必须确认 U 盘物理身份（防误格）
PowerShell 三步确认（git-bash 调 powershell 时 `$_` 会被 bash 吃掉 → 必须写成 .ps1 文件执行，不能内联 `-Command`）：
```powershell
Get-Volume | Format-Table DriveLetter,FileSystemLabel,DriveType,Size
Get-Disk | Format-Table Number,FriendlyName,BusType,Size,PartitionStyle
Get-Partition | Where-Object { $_.DriveLetter } | Format-Table DiskNumber,DriveLetter,Size,Type
```
确认目标 = BusType **USB** + DriveType **Removable** + 盘符对应（如 `SMI USB DISK`），绝不碰 NVMe/内部盘。

## 2. 下载 ISO + 双重 SHA256 校验
- ⚠️ **已下载到 U 盘的系统 ISO 不删**（用户明确要求"以后下载了不要删，可能用得上"）：换版本/清盘前先确认旧 ISO 已无价值，重复文件（如两盘各一份 22.04）可留，清 U 盘前先把要删的文件与另一处副本核对（大小+抽样哈希），确认不丢数据再动
- 镜像源：清华 `https://mirrors.tuna.tsinghua.edu.cn/ubuntu-releases/<ver>/`，curl 加 `--noproxy "*" --ssl-no-revoke`
- 版本确认：`curl 目录 | grep -o 'ubuntu-24.04\.[0-9]*-desktop-amd64\.iso'`（24.04 最新点版本 24.04.4；live-server ~3.2G / desktop ~6.2G）
- 下载 SHA256SUMS 对比本地 sha256；**拷贝进 U 盘后对副本再验一次**（双重校验）

## 3. Ventoy 刷盘（推荐工具）
- Ventoy = 引导工具不是系统（用户常误解）：装到 U 盘后开机出图形菜单选 ISO；MBR 方案 UEFI+Legacy 双支持
- 下载：GitHub release（`curl -sI .../releases/latest | grep -i '^location'` 拿版本号，走代理），解压出 Ventoy2Disk.exe
- 安装启动：`powershell Start-Process Ventoy2Disk.exe -ArgumentList '/I','/S','/DRIVE=<磁盘号>' -Verb RunAs`（UAC 提权；git-bash 直接调 exe 报 Permission denied）
- ⚠️ **命令行参数不自动触发安装**：GUI 弹到"准备就绪"后必须点"安装"按钮（自动化坑见 references，兜底=让用户手动点，用户在场时直接走这条最稳）
- 装完验证：U 盘变 `Ventoy`（exFAT 数据区）+ `VTOYEFI`（FAT 引导区）

## 4. 拷 ISO + 验证
- `cp` ISO 进 Ventoy 数据区（后台跑，3-6G 几分钟），完成后 `sha256sum` 副本 == 官方哈希
- 换 ISO（如 Server→Desktop）不用重刷盘：删旧文件拷新的即可

## 5. 装机引导（目标机侧）
详见 `linux-install-notes.md`，要点：
- 启动模式 **UEFI**（BIOS 关 CSM、Secure Boot 关；启动菜单选带 `UEFI:` 前缀的 U 盘项）；安装器挂载点列表**有 /boot/efi = UEFI 模式**，没有 = Legacy 模式要重启
- EFI 分区格式 = **vfat**（=FAT32，UEFI 规范名）；`/data` 不在挂载点预设 → 手动输入或挂 `/home`
- Ubuntu Pro 跳过即可
- 桌面版默认**没有 openssh-server**（只有客户端）→ `apt install openssh-server` + `systemctl enable --now ssh` + `ufw allow ssh`
- 显卡驱动：图形界面"软件与更新→附加驱动"选官方驱动（如 nvidia-driver-580，Ampere 全支持）；或命令行 `sudo apt install -y nvidia-driver-580` + `sudo reboot`（远程自动化走命令行，见 selfhosted-server-ops GPU 训练栈节）
- 桌面版装完默认无 openssh-server 且 SSH 端口拒连时先确认装服务端（见上），再确认目标机 IP 别猜（见 Pitfalls 1）

## Pitfalls（教训）
0. **Ventoy 数据区 exFAT = DOS/FreeDOS 读不了**：主板 BIOS 刷写工具（如华南官方 fpt.exe）常是 DOS 程序（MZ+LE 头，非 Windows PE），且 Ventoy 数据分区是 exFAT——不能把刷写文件丢 Ventoy 盘再启动 FreeDOS 读。解法：①把工具+固件+脚本打包成自包含 FreeDOS 启动 ISO 扔 Ventoy；②用 Rufus 把第二个 U 盘做成 FreeDOS 盘（内置 FreeDOS 选项，FAT32），格式前先确认盘里没有要留的数据。判断 exe 是不是 DOS 程序：xxd 看文件头，e_lfanew 偏移处是 `LE`/`LX` 而非 `PE\0\0` 即 DOS 扩展程序（dPMODE/W 等），WinPE 跑不了。刷写类 DOS 工具（fpt.exe 等）常要求**同目录伴生文件**（如 fparts.txt）——拷工具时把官方包解出来的全部文件一起拷，漏一个就报错拒绝运行（fpt 报 Error 75 file not found，并写 ERROR.LOG 到当前目录可查）
1. **IP 归属禁凭 TTL/ARP 猜**：新装机 SSH 拒连时，TTL=64 只说明"是台 Linux"，可能是别人（192.168.1.6 误判为大服务器教训，真 IP 是 10.8）。让用户在目标机跑 `ip addr` 对号入座；只有 `127.0.0.1/8` = 网卡没拿到 IP（查网线 + `sudo dhclient`）
2. **sudo -S 管道密码被 the harness security policy拦截**：用 pty 交互（background+pty，process write 密码 + submit 回车）或让用户图形界面操作
3. **SSH 首登部署公钥**：pty 交互 ssh 登录后 `mkdir -p ~/.ssh && echo '<pubkey>' >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys` → 之后免密（`-i ~/.ssh/id_ed25519_inspire -o BatchMode=yes`）
4. **Windows PTY 交互**：process(write) 发文本 + process(submit) 发回车；裸 `\n` 在 Windows PTY 不触发回车
5. **GUI 刷盘工具（Rufus 等）普通权限启动会静默失败/不弹窗**：必须 `powershell Start-Process -FilePath <exe> -Verb RunAs` 提权启动（本次实测 Rufus 普通启动进程不出现，提权后正常弹窗）。Rufus 内置 FreeDOS 选项（引导类型下拉选 FreeDOS），做 BIOS 刷写盘不需要额外下载 FreeDOS 镜像
6. **大 ISO 快速判同：先 stat 大小 + `head -c 1M | md5sum` 抽样**，全量 md5sum 4.7GB 会超时（>180s）；大小一致 + 首 1MB 哈希一致即可基本确认同一文件（如两个 U 盘上的重复 ISO），全量校验只在正式交付时做
7. **git-bash 里 curl 是原生程序，不认 `/f/` 这类 MSYS 路径**：`curl -o /f/x.iso` 会失败并疯狂重试（Warning: Failed to open the file，curl 23），**必须写 `F:/x.iso`**。而 bash 自己的重定向 / `ls /f/` 正常（MSYS 程序才认）——同一个脚本里两种写法混用是这个坑的诱因
8. **下载大 ISO 先测速再决定走不走代理**：同一微软 CDN 直连常比走 Clash 快（实测 9.1 vs 7.6 MB/s）；`-C -` 续传 + `--retry 30 --retry-all-errors` 是长时间下载的保命参数。Windows 侧确认落盘大小 == HTTP `Content-Length`
9. **Live 会话里不要指望回写 Ventoy 数据分区**：从 U 盘起的 Live 系统里 Ventoy 通过 device-mapper 占着那张盘（ISO 挂在 `/cdrom`），再 `mount /dev/sdX1` 报 `already mounted or mount point busy`，dmesg 是 `Can't open blockdev`。要改 U 盘里的文件（如更新随盘的说明文档）回宿主系统改，别在 Live 会话里试
10. **U 盘启动项是一次性的**：`efibootmgr` 里当前 USB 启动只体现为 `BootCurrent: 000X`，不在 `BootOrder` 里、重启后不保留 —— 固件会回到内置盘（默认进原系统）。所以给用户的指令必须写"重启 → 按 F11/启动菜单键 → 选 U 盘"，**不能承诺"重启会自动进 U 盘"**，也不必为此改 BIOS 启动项

## 6. Windows 安装介质（Ventoy 直拷，不必刷盘）
- **拿官方原版 ISO 直链**：浏览器打开 `microsoft.com/zh-cn/software-download/windows11` → 选“Windows 11（适用于 x64 设备的多版本 ISO）”→ 立即下载 → 语言选简体中文 → 确认 → 页面上那个“64 位 下载”的 `href` 就是**微软官方 CDN 直链**（`software.download.prss.microsoft.com/dbazure/Win11_...iso?t=...`，**24h 失效**，拿到就立刻下）。同页“验证你的下载”里按语言列出 **SHA-256**，拷完必须比对
- ⚠️ **Fido.ps1 已失效**：微软改了接口，`software-download-connector/api/getskus` 返回 404（Fido v1.70 也带上了“Microsoft altered their website”的提示）。别浪费时间调 Fido，走上面浏览器路线
- **Win11 绕过 TPM/CPU/SecureBoot 检测**：不刷盘也能做——在 U 盘数据区写 `/ventoy/ventoy.json`：`{"control":[{"VTOY_WIN11_BYPASS_CHECK":"1"},{"VTOY_WIN11_BYPASS_NRO":"1"}]}`（前者注入 LabConfig 四个 Bypass*，后者注入 BypassNRO 免联网账号；NRO 那条**必须断网**才出现本地账号选项）。手动兜底=安装界面 Shift+F10 → regedit → `HKLM\SYSTEM\Setup` 新建项 `LabConfig`，DWORD `BypassTPMCheck/BypassSecureBootCheck/BypassRAMCheck/BypassCPUCheck`=1
- **Ventoy 装 Windows 报“找不到任何驱动器/设备驱动程序”**：回 Ventoy 菜单，光标停在该 ISO 上按 **回车** 弹出二级菜单 → 选 `Boot in wimboot mode`（快捷键 **`Ctrl+W`**；`grub2 mode` = **`Ctrl+R`**）。⚠️ 二级菜单是**回车**触发的，**不是 F2**（F2 在这套界面里是电源相关热键，写错等于让用户在键盘上瞎按）；官方口径=先试 normal，normal 卡住才换 wimboot
- **用户说“U 盘里没有驱动”时先别信症状**：他多半在看启动后挂出来的 **ISO 虚拟光驱**，而我们的文件在 **Ventoy 数据分区**（卷标 `Ventoy`）根目录——两者在文件管理器里都像个盘；且**安装阶段本来不需要任何驱动**，"加载驱动程序"页不是缺驱动
- **判断用户到底在哪个环境**：让他 `Shift+F10` 后在命令行敲 `wpeutil` —— **报“不是内部或外部命令”= 他已不在安装介质(WinPE)里，而是进了装好的 Windows**（WinPE 里 `wpeutil` 一定存在）。对应的退出办法：WinPE 里 `wpeutil reboot` 最干净（`Alt+F4` 常无响应），任何环境都能用**长按电源键 5 秒**（没在写盘时硬断电安全）
- **NVIDIA 驱动官方直链**：先查版本再拼 URL。查询接口（**必须带 UA**，否则空响应）：`https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/AjaxDriverService.php?func=DriverManualLookup&psid=101&pfid=933&osID=<135=Win11/57=Win10>&languageCode=1033&beta=0&isWHQL=1&dltype=-1&dch=1&upCRD=0&qnf=0&sort1=0&numberOfResults=5`（RTX 3070: psid=101/pfid=933）；下载 URL 规律 `https://us.download.nvidia.com/Windows/<ver>/<ver>-desktop-win10-win11-64bit-international-dch-whql.exe`。⚠️ 新版本 **Game Ready 与 Studio 常为同号同包**，不必再找“Studio 专用文件”。拷完用 `Get-AuthenticodeSignature` 验签（应为 NVIDIA Corporation / Valid）
- **Win11 Setup 出现"勾选同意删除所有内容，包括文件、应用和设置"= 走错到升级/重置分支**：这是 upgrade 那条路（选项为保留个人文件/仅保留个人文件/不保留任何内容），**不要确认**——退回"安装类型"页选 `自定义：仅安装 Windows(高级)`（有的版本把这行渲染成底部不显眼的小字链接）。装到已有 Linux 的机器上，凡出现"删除/格式化/擦除磁盘"的确认页一律往回退，让用户拍屏而不是猜点哪。（25H2 存在新旧两套安装器 UI，经典 UI 才有完整的"自定义"流程——用户口述的页面可能对不上任何一套，别据描述推断）
- **可以全程拔网线装**：ISO 与驱动都在 U 盘，安装不需要联网；`VTOY_WIN11_BYPASS_NRO` 本来就要求断网才出本地账号选项，先拔正好；还省掉 Setup 顺手拉更新导致的多余重启。唯一代价是网卡驱动靠 inbox——装前先 `lspci -nn | grep -i ethernet` 确认型号是通用款（Realtek 8111/8168 = `10ec:8168` 有 inbox 驱动），装完插回网线再让 WU 补最新版
- **Win11 装到现有 Ubuntu 机器（同盘双系统）**：ext4 **必须离线缩** → 从 U 盘起 Live（Try Ubuntu）用 GParted 缩 p2（**Free space preceding 必须保持 0**），末端留未分配给 Windows；然后 Windows Setup 只选那块未分配（**不要手动分区、不要格式化 EFI 分区**，Setup 会把引导写进现有 ESP）。装完 Windows 引导顺序被夺 → Ubuntu 侧 `GRUB_DISABLE_OS_PROBER=false` + `sudo update-grub` 找回 Windows 菜单项
  - **默认就用用户手里这块盘做双系统，不要提议"再加一块盘"**：对只有一块盘的机器提双盘方案会被直接否掉（用户第一反应是"我上哪给你搞一个盘"）。只在用户自己提出加盘时才写双盘方案
  - **先问 Windows 要多大**（用户会给一个具体的数），Ubuntu 拿剩下的：`目标 ext4 = 盘可用空间 - Windows 需求 - ~2 GiB 余量`；GiB/扇区换算写清楚（`348 GiB = 729,809,760 个 512B 扇区`），缩完末端那块未分配空间**整块**交给 Windows Setup 自己分
  - 离线缩的命令等价物：`e2fsck -f <part>` → `resize2fs <part> <size>` → `parted <disk> unit s resizepart <n> <end>`（`end = start + size/512 - 1`，起始扇区**永不改**）；GParted 一次操作同时把文件系统和分区表改对，优先 GUI，命令行只在 GUI 不可用时用
  - 缩之前先备份目标机数据（`/home` 全量 tar 回控制端 + 一份系统清单：系统版本/分区/已装包/自启服务/docker 镜像/crontab），缩分区前的基本礼貌
  - ⚠️ **`parted --script ... resizepart` 会静默"不执行"**：缩小分区时 parted 要问 "Shrinking a partition can cause data loss"，`--script` 把提问吃掉后 **`rc=1` 退出、分区表一字未改**（既不是成功也不是失败，是没做）。非交互执行必须走 `echo Yes | sudo parted ---pretend-input-tty <disk> unit s resizepart <n> <end>`（`---` 三横杠是它自带的调试入口，专用来喂交互答案）。症状识别：`rc=1` 且 `parted print` 里分区大小没变 = 数据没动，改写法重跑即可，别慌
  - **扇区数用工具算，别手算**：`end = 起始扇区 + (numfmt --from=iec <SIZE>)/512 - 1`；起始扇区一律从 `parted -m <disk> unit s print` 现读（不要假设 1MiB 对齐、不要用上次的读数）。手算 348 GiB 的扇区数曾差 864 扇区。分区可以比文件系统略大，**绝不能比它小**
  - **缩完必须三件套复验**（"完成"以这三条全过为准，缺一不算）：① `e2fsck -f -n <part>` 只读校验零错误 ② `mount -o ro <part> /mnt` 真读到文件（`/etc/hostname`、`/home/<user>` 各看一眼）再 umount，`df` 的已用应与缩前一致 ③ `sgdisk -v <disk>` 报 `No problems found`（GPT 备份头已迁到新盘尾）
  - 完整命令序列、定尺寸算法、回滚 → `offline-ext4-shrink.md`

## 7. 把用户的手动步骤压到最少（远程接管 Live 会话）

装机类任务里"用户必须在机器前敲命令"既是成本也是风险源。默认先自问"这一步我能不能远程做"，只保留物理上做不到的动作：BIOS/启动菜单选项、Windows 安装器 GUI 点击。可压缩到的上限 = **所有可离线做的分区/文件系统操作都由我远程执行**。

- **先远程把能查的都查完**：分区字节数、`/sys/class/tpm` 是否存在、Secure Boot EFI 变量读数、`/home` 体积与备份、现有启动项（`efibootmgr`）——这些都在 SSH 里查完再定方案，别让用户在机器前逐条念结果。
- **让 Live 会话自己长出 SSH（用户只贴一行）**：Live 系统默认没有 sshd 也没我的密钥。在**局域网常开的 Linux 主机**当落点机挂 HTTP 分发脚本，用户只需在 Live 终端执行：
  `curl -s http://<落点机>:<port>/live_ssh.sh | sudo bash`
  脚本职责：等 DHCP → 换国内 apt 镜像 → `apt-get install -y openssh-server` → 把控制端公钥写进 live 用户（`ubuntu`，Live 会话免密 sudo）与 `/root` → 重启 sshd → 打印 IP 与 22 端口监听状态。之后控制端 `ssh ubuntu@<LiveIP>` 接管：fsck / resize2fs / parted / 复验全部自己跑。
  脚本要点：等 DHCP → 换国内 apt 镜像 → `apt-get install -y openssh-server` → 把控制端公钥写进 live 用户（`ubuntu`，Live 会话免密 sudo）与 `/root` → 重启 sshd → 打印 IP 与 22 端口监听状态。落点机用 `ssh <落点> 'cat > /var/www/live_ssh.sh' < live_ssh.sh` 推送（同一条命令里接 `chmod +x` 与 `sh -n` 语法检查）；在 ssh 里后台启动长驻进程要 `nohup ... &` 或 `setsid`，直接 `&` 会随会话退出被杀。之后控制端 `ssh ubuntu@<LiveIP>` 接管：fsck / resize2fs / parted / 复验全部自己跑。
- **落点机选常开的 Linux 主机，不要指 Windows 笔记本**：Windows 防火墙拦入站，同网服务器连 ping 都不通，HTTP/SSH 一样可能被挡。
- **Live 会话选 U 盘上最新的 LTS**：救援/缩分区时工具链只有更新的那一侧才保险（`resize2fs` 所属 e2fsprogs 版本要 ≥ 被操作文件系统的生成版本，用更老的一侧可能被拒）；同族旧 LTS 也能用，U 盘上最老的那版别用。
- **开不了 SSH 时的兜底**：把"一条龙脚本"（如 shrink.sh）同时拷到 U 盘根目录，用户在 Live 终端直接跑。脚本必须自带**基线校验**（设备名/分区字节数与实测基线不符即拒绝执行）+ 要求手打确认词，且日志可回看。
- **脚本一律英文**（shell/ps1/bat 的编码安全），中文只写在交付文档与对话里。
- **随盘说明书**：把一步步的装机指引写成 md 放到 U 盘根目录（`装机指引_*.md`），用户人在机器前不用翻聊天记录；每完成一大步就更新它，否则他会按旧步骤重复操作（U 盘插在目标机上时改不了，见 Pitfalls 9——要改得等盘插回控制端）。
- **“省心版介质”是可选项**：Ventoy 的菜单/模式对非技术用户是额外认知负担，可主动提出"把盘做成插上直接进安装程序"的直铺方案，让用户自己选；不主动改盘。
- **决策点问一次就够**：版本/驱动/分区比例这类选项用一次表单问完；表单空回或被关掉（用户没答上）就**按推荐默认值继续做，并在正文写明"要改说一声"**，别反复弹表单把进度卡住。

## 8. 现场指导纪律（用户人在机器前，我隔着屏幕）

这类任务卡住的原因往往不是技术，而是**信息带宽**：用户在机器前只有两只手和一个屏幕。本类任务里用户连续三轮"我没看懂你让我干这些干嘛 / 我搞不明白你要我干嘛 / 搞半天又要插网线"，全部源于下面几条没做到。

- **一次只给一个动作**："选带 Windows 的那一行 → 回车"。不要在同一屏塞 A/B/C 分支、不要"如果是 X 就那样、如果是 Y 就这样"——分支留给我自己判断，操作屏上只留下一步。
- **先确认他在哪个界面，再给下一步**：让他**拍整屏**（照片 > 让他描述 > 让他按我说的去找菜单）。同一句抱怨在不同界面下解法完全相反，猜错一轮就多耗他十几分钟。
- **绝不凭假设重发整段流程**：用户其实已经装完、我却让他"再装一遍"，等于告诉他我根本没跟上进度——发流程前先问一句"现在屏幕上是什么/装完了吗"。
- **必需 vs 可选要显式标注**：装完跑 Windows Update / 激活这类是**以后想弄再弄**的，必须写成"可选、不是装机前提"；只说"插网线跑更新"会被理解成"必须联网才能装"（用户原话："搞半天又要插网线"）。
- **用他屏幕上真实存在的字**：`Boot Override`、`F2`、`Windows Boot Manager` 这类词他常常对不上号；换成"BIOS 最下面那个能选设备的列表 → 选带 Windows 的那行"就通了。术语先映射到可见字样，再给动作。
- **他提出的捷径先答"对"**：用户问"我直接在 BIOS 启动 Windows 不就行了？"——先一句"对，就是这个意思"，再补最多一句细节；不要把他刚说的话换成我的说法重讲一遍。
- **卡住时给的是"退出来重来"而不是"继续点"**：安装器走进死胡同时（页面只有"加载驱动程序"、`Alt+F4` 无响应），给物理兜底（`Shift+F10` → `wpeutil reboot`，或长按电源键 5 秒）＋重来路径，并明确"此刻硬盘没在写，硬断电安全"，先打消他"会不会弄坏"的顾虑。
- **他答不上问题就换问法**：连续两次答非所问（如把"哪个界面"答成"我在 BIOS"）说明问法太技术，直接要一张照片。

## references
- `ventoy-gui-automation.md` — Ventoy GUI 自动化完整坑位与 UIA 代码模式
- `linux-install-notes.md` — 装机引导详细（分区/UEFI/驱动/SSH/体检命令）
- `offline-ext4-shrink.md` — 离线缩 ext4 做同盘双系统：定尺寸算法、parted 非交互坑、复验三件套、Live 会话坑、回滚
