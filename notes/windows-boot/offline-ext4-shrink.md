# 离线缩 ext4：给已装 Linux 的单盘机器腾出双系统空间


> **适用平台**：Live 会话中对 ext4 根分区做离线缩容  
> **一句话**：缩容铁律是先备份再动手；尺寸算好、e2fsck 过一遍、复验三件套缺一不算完成。  
> **标签**：linux, ext4, resize, dual-boot, live-usb

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

适用：机器只有一块盘、Linux 已装，要再挤出空间装 Windows（或另一个系统）。

## 0. 铁律
- ext4 **不支持在线缩小**：根分区挂着就缩不了（内核限制，跟权限无关）→ 必须从 U 盘起 Live 会话离线做。同理，事后想扩容也得回 Live 会话。
- 顺序不可反：**先缩文件系统（`resize2fs`），再缩分区表条目（`parted`）**。反过来会把文件系统截断。
- 分区缩到**保持起点不动**，腾出的未分配空间才会落在盘尾（另一系统的目标位置）。

## 1. 动手前先把事实查完（全部在 SSH 里做，别让用户在机器前念）
```bash
lsblk -b -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT /dev/nvme0n1   # 分区字节数（做基线）
parted -m /dev/nvme0n1 unit s print                          # 起始/结束扇区（唯一可信来源）
blockdev --getsz /dev/nvme0n1                                # 盘总扇区
blockdev --getsize64 /dev/nvme0n1p2                          # 目标分区当前字节数
ls /sys/class/tpm 2>/dev/null || echo "no TPM"               # 决定要不要绕过 Win11 检测
od -An -t u1 /sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c   # 第5字节 0=关 1=开
efibootmgr -v                                                # 现有启动项（回装引导菜单时对照）
```
备份（在线就能做，缩分区前必做）：`tar czf - -C /home <user> | ssh 控制端 'cat > backup.tar.gz'`，另存一份系统清单（dpkg selections / 自启服务 / docker images / crontab）。

## 2. 定尺寸（给 Linux 留多少、Windows 拿多少）
```bash
SIZE=348G                                                   # 想给 Linux 留多少
BYTES=$(numfmt --from=iec "$SIZE")                          # 用工具换算，别手算
SECTORS=$((BYTES/512))
START=$(parted -m /dev/nvme0n1 unit s print | awk -F: -v n=2 '$1==n{gsub(/s$/,"",$2); print $2}')
END=$((START + SECTORS - 1))
```
- 报给用户时**同时给 GiB 与 Windows 会显示的 GB**（同一块盘两种读数差约 7%，用户说"128G"通常指后者）。
- 缩完末端那块未分配空间**整块**交给目标系统安装器自己分，不要预先手建分区。

## 3. 执行（在 Live 会话里）
```bash
sudo umount /dev/nvme0n1p2 2>/dev/null
sudo e2fsck -f -y /dev/nvme0n1p2                            # 不干净不许缩
sudo resize2fs /dev/nvme0n1p2 348G                          # ① 文件系统（快，几十秒量级）
echo Yes | sudo parted ---pretend-input-tty /dev/nvme0n1 unit s resizepart 2 "$END"   # ② 分区表条目
sudo partprobe /dev/nvme0n1; lsblk -o NAME,SIZE,FSTYPE /dev/nvme0n1
```
- ⚠️ **`parted --script` 对"缩小分区可能丢数据"的确认会 `rc=1` 且什么都不做**（提问被吃掉 = 未执行）。非交互正解是 `---pretend-input-tty` + `echo Yes |`。看到 `rc=1` 且分区大小没变 = 数据没动，换写法重跑即可。
- GUI 可用时优先 GParted：它一次操作同时把文件系统与分区表改对（`Free space preceding` 保持 0）。命令行只在 GUI 不可用时用。

## 4. 复验三件套（缺一不算完成）
```bash
sudo e2fsck -f -n /dev/nvme0n1p2                            # ① 只读校验，必须 0 错误
sudo mkdir -p /mnt/chk && sudo mount -o ro /dev/nvme0n1p2 /mnt/chk && \
  ls /mnt/chk && head -3 /mnt/chk/etc/hostname && ls /mnt/chk/home/<user> | head -8 && \
  df -h /mnt/chk && sudo umount /mnt/chk                    # ② 真读到数据（已用应与缩前一致）
sudo sgdisk -v /dev/nvme0n1                                 # ③ No problems found（GPT 备份头已迁移）
sudo parted -m /dev/nvme0n1 unit GiB print free             # 盘尾未分配 == 计划值
```
只读挂载是这里的关键证据：`e2fsck -n` 只能证明元数据没坏，挂上去列出真实文件才证明数据在。

## 5. 接着装 Windows 的关键点击（同盘双系统）
- 启动菜单仍要**手动**选 U 盘（U 盘启动项不持久，见 usb-install-media 的 Pitfalls 10）。
- 分区页**只选那块未分配空间**：不删现有分区、不格式化 EFI 分区（Windows 把引导写进现有 ESP，512 MiB 够）。
- OOBE 拔网线走本地账号（Ventoy 已注入 BypassNRO）；弹"无法运行 Win11"时按 Pitfalls 里的 LabConfig 兜底。
- 装完 Windows 抢走引导顺序：回 Linux 执行 `GRUB_DISABLE_OS_PROBER=false` + `sudo update-grub`（`os-prober` 在 Ubuntu 22.04 默认关闭），再用 `efibootmgr -o` 排启动顺序；Windows 大版本更新偶尔把自己改回第一项，复发就重排一次。

## 6. Live 会话特有的坑
- **同一 IP 的主机密钥与已装系统不同** → `ssh -o StrictHostKeyChecking=no ubuntu@<ip>`（一次性会话，不必往 known_hosts 里种）
- Live 默认用户 `ubuntu`，**免密 sudo**（不需要 `sudo -S` 喂密码）
- Live 去 `archive.ubuntu.com` 很慢 → 换清华源再 `apt install`（装 sshd 那步）
- **回写 U 盘的 Ventoy 数据分区会失败**（Ventoy 用 device-mapper 占着设备，`Can't open blockdev`）→ 要改 U 盘里的文件回宿主系统改
- Live 会话重启后不会自动回到自己，见 Pitfalls 10

## 7. 回滚
- 分区表缩了、文件系统没动（`rc=1` 那种）：结束扇区加回去即可。
- 文件系统已缩、要救数据：用第 1 步的备份 tar 恢复（`tar xzf backup.tar.gz -C /home`）。
- 要把空间还回去（扩 Linux）：回 Live 会话，先 `resize2fs <part>`（先要 `parted resizepart` 把分区放大到 ≥ 目标），顺序与缩相反——**扩的时候先放分区、再放文件系统**。
