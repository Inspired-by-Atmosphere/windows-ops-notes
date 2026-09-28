

> **适用平台**：Windows 10 / 11（无管理员账户）  
> **一句话**：免管理员装 MySQL/CLI 工具的实测路径，以及把安装步骤压成一键包交付给别人的做法。  
> **标签**：windows, install, no-admin, packaging, mysql

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# 无管理员权限下的 Windows 软件部署与一键安装包

## 权限现实（本机实测，先认命再动手）
- bash/PowerShell 会话是 UAC 降权标准令牌：`Start-Process -Verb RunAs` 静默失败（不弹窗不执行）；`schtasks /RU SYSTEM` 与 `/RL HIGHEST` 均"拒绝访问"。命令行从标准令牌**无法静默提权**（管理员组成员 + ConsentPromptBehaviorAdmin=0 也不救）。
- 别跟提权较劲 → 优先**用户级（免管理员）安装路径**：zip 免安装版 + 可写盘 + 启动文件夹 VBS 自启 + 免安装 GUI 替代品。
- 需要管理员才能装的（MSI 装 Program Files、注册 Windows 服务、装 OpenSSH Server）绕不开就换替代，不卡死。

## 免管理员装 MySQL（8.0 全流程已验证）
1. 下载 zip 版（非 MSI/Installer——MySQL Installer 只到 8.0 系列且需管理员）：华为云镜像直连（见下"下载提速"）
2. 解压到可写数据盘（如 `<盘符>:\MySQL`）
3. 写 my.ini：basedir/datadir 用**正斜杠**；utf8mb4；`default-authentication-plugin=mysql_native_password`（兼容 Navicat 等旧工具）
4. `mysqld --defaults-file=... --initialize-insecure`（生成 data，root 空密码）
5. 启动：`Start-Process mysqld -WindowStyle Hidden`——进程独立于父会话，父退出后存活（已验证）
6. 设密码：`mysql -u root --skip-password -P <port>` 执行 ALTER USER + FLUSH PRIVILEGES
7. 开机自启：启动文件夹 VBS（%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\MySQLd.vbs）：
   `ws.Run "mysqld --defaults-file=...", 0, False`（0=隐藏窗口；用户级即可，计划任务在本机被策略拒）
8. 可视化：Workbench 只有 MSI（需管理员）→ DBeaver zip 免安装版替代。DBeaver 26.x 起 asset 名改为 `dbeaver-ce-<ver>-windows-x86_64.zip`（旧 `win32.win32.x86_64` 404）；真实文件名从 GitHub `releases/expanded_assets/<tag>` 页拿（curl 抓不到时 web_extract 可），别猜

## 打一键安装包（给colleagues）
模式：**预解压目录 + PowerShell 安装脚本 + 纯英文 bat 入口 + 使用说明**——对方零前置：解压→双击→完成（免管理员）。
1. 打包"解压后目录"而非原始 zip（绕开对方解压环节）；zip 压缩后约减半
2. 安装脚本前置检查：`Get-NetTCPConnection -LocalPort $Port -State Listen` 端口占用、目标目录已存在 → 拒绝并提示先卸载
3. 交付前用**临时端口 + 临时目录**完整实测一遍，且**必须走真实入口**：`subprocess.run(['cmd','/c','一键安装.bat','-InstallDir',...,'-Port',3307,...], cwd=解压目录, stdin=DEVNULL)` 模拟双击（python subprocess 避开 MSYS 引号转换坑）。只测内部 ps1 不算数——入口层的编码、参数透传（bat 须带 `%*` 才能测试传参）、失败处理只有走真实入口才现形。**成功路径 + 失败路径都测**（失败=端口占用/目录已存在重复装，应显示 FAILED 且非零退出码，绝不假 Done）。测完先按 CommandLine 确认目标再杀测试实例，再删目录。示例数据用英文（见编码铁律）
3b. **必须测默认参数路径**（不是临时目录）：真实用户无参数双击 → 默认 `<盘符>:\MySQL`（盘根下一级），`Split-Path` 得 `<盘符>:\` → PS 5.1 `New-Item -Path '<盘符>:\'` 直接报「路径的形式不合法」崩溃。用临时子目录测试会绕过盘根边界（翻车实录：colleagues按默认路径装必崩，而我的测试全绿）。父目录创建一律写 `$p = Split-Path $x -Parent; if ($p -and -not (Test-Path $p)) { New-Item -ItemType Directory -Force -Path $p }`
4. 瘦身：删 `*.pdb` 调试符号（mysqld.pdb 可 300M+）、用不上的大目录（lib/mecab 日文分词、mysqlclient.lib 开发静态库）——bin 里的 dll 保留即可，客户端 `--version` 验证
5. 交付位置：`%USERPROFILE%\Desktop\share\`（via a file-sharing service发colleagues）

## 下载提速
- 大文件先测速再下：官方 CDN 走代理可能 ~100KB/s，华为云 `mirrors.huaweicloud.com`（MySQL/其他常见软件镜像齐全）`--noproxy '*'` 直连 ~10MB/s
- 镜像同步滞后：最新版常 404，列目录选可用旧版（8.0 系列教学通用）

## GUI 程序拉不到商店/更新（代理环境变量被 GUI 继承）
- 代理环境变量可以是**用户级持久化**的（`HKCU\Environment` 下的 HTTP_PROXY / HTTPS_PROXY / ALL_PROXY）→ **所有 GUI 程序（浏览器、编辑器、商店客户端）都继承**。所以「终端里代理正常」不代表 GUI 那条路通。
- 排查姿势：**同一个域名分两次 curl**——走代理 vs `--noproxy '*'`。实测踩到过代理返 `000`（不通）而**直连 `200`**（代理规则把该域名送到不通的节点）；别预设"代理=通"或"直连=不通"。
- 修法二选一：
  1. **离线装**（推荐，影响面最小）：直连下载安装包 + 命令式安装——VSCode 扩展见 `../scripts/vscode_vsix_install.py`；
  2. 让该程序自己绕过代理：支持 `http.noProxy` 的编辑器加 `"http.noProxy": ["marketplace.visualstudio.com", "*.gcdn.vsassets.io"]`（不影响其他程序和其他域名）。改用户 settings.json 属于写入用户配置，先问一句再改。

### 离线装 VSCode 扩展（代理不通 marketplace 时）
1. 查扩展 ID 与**全部版本**：POST `https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery`（Accept 头带 `api-version=7.2-preview.1`），`flags` 用 **439**（0x1B7）。**别用 951**：它含 `0x200 = IncludeLatestVersionOnly`，只回一个版本，会让你得出"没有兼容版本"的假结论（实际有 376 个）。
2. **版本必须与本机引擎对齐**：每个版本带 `Microsoft.VisualStudio.Code.Engine` 属性（如 `^1.133.0`）。先 `code --version` 拿本机版本，选**满足 engine 的最新版**；否则报 `Unable to install extension ... as it is not compatible with VS Code '<ver>'`——最新版常年要求更高，必须往历史版本回退。
3. 下载：`.../publishers/{publisher}/vsextensions/{ext}/{version}/vspackage`，**加 `--noproxy '*'`**。
4. ⚠️ 该接口返回 **gzip 包装**（魔数 `1f 8b`），不是 zip → 先 `gunzip`；装前核对魔数应为 **`PK`**，拿 `1f 8b` 直接装会失败。
5. 安装：`code --install-extension "<Windows 绝对路径>.vsix" --force`。**必须传 Windows 绝对路径**——MSYS 相对路径会被解析成 `file:///d%3A/...` 而报 `Failed Installing Extensions`。路径含空格/中文时先把 vsix 拷到无空格的临时目录再装，绕开引号坑。
6. 复核：`code --list-extensions`（依赖扩展会一并装上）。
7. `code` CLI 不在 PATH 时用绝对路径（示例：`%ProgramFiles%\Microsoft VS Code\bin\code`；装在非系统盘就换成自己的路径）；VSCode 装在 `<install>\<hash>\resources\app` 这类版本号目录下，找 `resources/app/out` 要先进版本号目录。

## Pitfalls（实踩）
- mysql.exe 客户端**默认连 3306**——服务在别的端口必须显式 `-P <port>`，否则连到本机旧实例报 Access denied（测试 3307 时踩过）
- 杀进程前先按 CommandLine 确认目标：`Get-CimInstance Win32_Process -Filter "name='mysqld.exe'"`（Filter 值要单引号包裹）——本机可能跑着正式实例，禁 taskkill //IM 全杀
- `taskkill //PID` 在 MSYS 路径转换出错 → 用 PowerShell `Stop-Process -Id`
- 测试实例残留会占目录（rm 报 Device busy 删不掉）→ 先杀进程再删目录
- 安装包内 SQL 含中文：ps1 存 UTF-8 BOM + SQL 写临时文件（UTF-8 无 BOM）+ cmd 重定向字节流 + `--default-character-set=utf8mb4`，中文才不丢
- 🔒编码铁律（用户硬性要求）：**写代码/脚本默认全英文，禁中文**（含示例数据、注释、输出）——全 ASCII 从根上消灭 GBK/UTF-8 乱码整类问题，bat/ps1 无需再纠结编码。仅当必须含中文时：ps1 存 UTF-8 BOM（patch 工具会剥 BOM，写完用 python 加回并验证文件头 EF BB BF）、bat 按 GBK 转存——且转码后必须验证字节确实已是目标编码（python 的 `decode('gbk')` 启发式会把 UTF-8 字节误判成"已是 GBK"而静默跳过转换，坑过）
- PS 5.1 原生命令 stderr 坑：`$ErrorActionPreference='Stop'` 会把原生命令的 stderr 输出包装成 NativeCommandError 抛异常——原生命令用 `cmd /c "..." >nul 2>&1` 包裹再查 $LASTEXITCODE；bash 双引号里的 `$_` 会被 shell 展开，`powershell -Command` 用单引号或写 .ps1 文件
- **bat 包装层必须检查 `%errorlevel%`**：PowerShell 失败后 bat 不检查就照常显示 "Done" = 假成功，零基础用户会以为装好了——失败时显示 FAILED 并 `exit /b 1`（假 Done 正是"没走真实入口模拟"才漏掉的）
- **"未解压"检测禁用路径名匹配**：`findstr /c:".zip\"`（不触发）和 `%HERE:.zip\=%` 字符串替换（**误伤**）都不可靠——Windows 解压向导会把文件放进**真实文件夹** `xxx.zip\xxx\`（目录名带 .zip 而非压缩包），路径名判定会拦住正常解压的用户。正确做法：`if not exist "%~dp0mysql-8.0.29-winx64\bin\mysqld.exe"` 文件存在性判定（事实为准），ps1 侧同样 Test-Path 程序目录兜底
- **测试必须复现用户真实布局**：仅解压到英文空目录不够——要模拟 ①目录名含 `.zip` 的真实文件夹（Windows 解压向导典型产物）②中文文件夹名/中文用户名桌面路径，才能碰到这类误判
- **`New-Item` 不能创建盘根**：`New-Item -ItemType Directory -Path '<盘符>:\'` → CreateDirectoryArgumentError「路径的形式不合法」。凡"创建父目录"必须先 Test-Path 判存在（盘根永远存在→跳过）。默认安装路径（`<盘符>:\MySQL`）必然踩中，临时目录测试测不出来
- **bat 检测"在 zip 内运行"**：`echo %~dp0|findstr /c:".zip\"` 实测不触发（findstr 字面匹配不可靠）→ 改用 cmd 字符串替换 `set "HERE=%~dp0"` + `if not "%HERE:.zip\=%"=="%HERE%" (echo 请先解压 & pause & exit /b 1)`；ps1 侧再兜一层：程序目录（`mysql-8.0.29-winx64` 等）不存在 → 提示先解压。用户"我在 zip 里直接双击了 bat"和"解压了"都出现过，两条路都要给明确提示
- **Copy-Item 源==目标相撞**：Windows 路径大小写不敏感，测试参数/解压目录与目标路径重合时 `Copy-Item -Recurse -Force` 报"用其自身覆盖该项"——复制前 `TrimEnd('\').ToLower()` 比较，相同则跳过
