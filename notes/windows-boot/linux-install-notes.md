# Linux 装机实操笔记（引导模式 / 分区 / 装完第一轮）


> **适用平台**：x86_64 目标机安装 Ubuntu 类发行版  
> **一句话**：先判引导模式再分区；装完第一轮必须做网络/SSH/驱动体检，否则后面每一步都在猜。  
> **标签**：linux, ubuntu, install, partition, uefi

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

## 启动模式判定（卡住时先查这个）
- 安装器分区界面的**挂载点列表有没有 /boot/efi**：有 = UEFI 模式（正常，能建 EFI 分区）；没有 = Legacy/BIOS 模式（EFI 分区被系统拒绝，必须重启改 UEFI）
- 走 UEFI：BIOS Boot Mode=UEFI Only（关 CSM）、Secure Boot 关；启动菜单选带 `UEFI:` 前缀的 U 盘条目
- 硬盘残留旧 Windows：选"清除整个磁盘"或手动分区删旧分区即可清干净，无副作用

## 分区方案（桌面版图形安装器）
| 分区 | 大小 | 格式 | 挂载点 |
|---|---|---|---|
| EFI | 1G | vfat（=FAT32） | /boot/efi |
| 根 | 200G | ext4 | / |
| 数据 | 剩余 | ext4 | /home 或手动输入 /data |
- swap 不建（64G 内存 + 桌面版自动 swapfile）
- 挂载点下拉没有 /data（非预设目录）：选"手动输入/Enter manually"，或直接用 /home
- 引导加载器装到整盘（/dev/nvme0n1），不是分区

## Ubuntu Pro
- 跳过（Skip for now）。标准支持到 2029；个人免费 ESM 以后 `sudo pro attach` 可补，不用重装

## 装完第一轮（关键）
1. **SSH 服务端**：Ubuntu 桌面版默认只有 ssh **客户端**，无服务端！`sudo apt install -y openssh-server && sudo systemctl enable --now ssh && sudo ufw allow ssh`
2. **确认 IP**：`ip addr` 看 `inet 192.168.1.x/24`；只有 127.0.0.1/8 = 网卡没拿到 IP → 查网线 + `sudo dhclient`
3. **NVIDIA 驱动**：图形界面"软件与更新 → 附加驱动"选 `nvidia-driver-XXX (proprietary, tested)`（24.04 源有 535~610；Ampere 3070 选 580 这类成熟版；Secure Boot 关着则无需 MOK 签名），装完重启
4. 验证：`nvidia-smi` 显示 GPU + 显存

## 远程体检一条命令（SSH 免密后）
```
ssh -i ~/.ssh/id_ed25519_inspire -o BatchMode=yes inspired@<ip> 'hostname; LANG=C lscpu | grep "Model name"; free -h | head -2; df -h | grep -v tmpfs; nvidia-smi 2>&1 | head -15; ip -4 addr show | grep inet | grep -v 127.0.0.1'
```
注意目标机 locale 中文时 lscpu 输出乱码 → 加 `LANG=C`。

## 第二轮：GPU 训练软件栈初始化（CUDA/Docker/Container Toolkit，全部实测）

装完系统 + 驱动 + SSH 后，训练栈按此序（每步验证过）：

1. **换清华 apt 源**（24.04 是 deb822 格式 `sources.list.d/ubuntu.sources`）：`sed` 把 `archive/security.ubuntu.com` 换 `mirrors.tuna.tsinghua.edu.cn/ubuntu`，实测 8.8MB/s。⚠️ 全新机常没 curl → `apt install -y curl`
2. **CUDA toolkit**：`sudo apt install -y nvidia-cuda-toolkit`（Ubuntu 源给的是 CUDA 12.0 nvcc；PyTorch 用户其实靠自带 CUDA runtime 就够，系统级 nvcc 用于编译 CUDA 扩展）
3. **Docker + Compose**：`sudo apt install -y docker.io docker-compose-v2`
4. **Docker 镜像源（坑！）**：写 `/etc/docker/daemon.json` 加 `{"registry-mirrors":["https://docker.1ms.run"]}` 后**必须 `sudo systemctl restart docker`**——docker.io 安装时服务已在跑，`systemctl enable --now` 不会重载已运行 daemon 的配置（实测：不重启则拉镜像直连 registry-1.docker.io 超时；`docker info | grep -A2 Registry` 确认镜像源生效）
5. **NVIDIA Container Toolkit**（Docker --gpus 直通）：
   - ⚠️ 清华 `nvidia-container-toolkit` 镜像目录是空的（gpgkey 404，实测）→ 用**官方源** `nvidia.github.io/libnvidia-container`（国内直连 200）
   - `curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg`（keyring 已存在会问"是否覆盖"，回 y）
   - 官方 `.../stable/deb/nvidia-container-toolkit.list` 生成源（sed 加 `signed-by=`），`apt update && apt install -y nvidia-container-toolkit` → `sudo nvidia-ctk runtime configure --runtime=docker` → `systemctl restart docker`
6. **容器验证**：`sudo docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` 看到 GPU 即直通成功
7. **免 sudo 跑 docker**：`sudo usermod -aG docker $USER`（新 SSH 会话生效）

## 硬件参考（本次装机：大服务器 server-a）
- X99 + E5-2686v4（18C/36T 无核显）+ DDR3 1866 四通道 64G + SN730 512G NVMe
- 当前 RTX 3070（自带视频输出，可当亮机卡）；**后期 2×V100（Tesla 无显示输出）+ X99 无核显 → 必须插 AMD 亮机卡**（推荐 RX550 4G，比 W5100 新、驱动干净）才能看 BIOS/装系统；装完无头跑，亮机卡可拔屏幕
- V100(sm_70)+3070(Ampere) 同代 NVIDIA 驱动共存无冲突；CUDA 12.x 支持 V100
- 3070 16G 版非原厂（原厂 8G），魔改卡装完先烧机测试再上长训练
