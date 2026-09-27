

> **适用平台**：Windows 10 / 11（默认终端 = Windows Terminal 时尤其明显）  
> **一句话**：任何 console 子系统程序被拉起都会弹窗；隐藏标志只对第一层进程有效——正解是绕开 console 包装器，直接用 pythonw 调模块入口。  
> **标签**：windows, console, silent-launch, pythonw, create_no_window

本笔记自包含，阅读顺序：**现象 / 触发场景 → 根因 → 命令与步骤 → 验证方式 → 坑位**。

---

# 让 console 程序无窗后台启动（Windows 无终端弹窗）

## 触发场景
用户说"开机/启动时弹终端窗口"、"vbs 隐藏了还是弹"、"这个命令跑起来老是有黑框"。目标是让 CLI/console 程序（python 脚本、PyInstaller 打包的 CLI exe、your-service 等服务）后台静默运行，不弹任何可见窗口。

## 核心认知：为什么"隐藏"会失效
Windows 11 的"默认终端应用程序"默认 = **Windows Terminal**（不是老的 conhost）。后果：
- 任何 **console 子系统程序**（python.exe、PyInstaller 默认打包的 CLI exe、`app.exe desktop` 这种 venv 包装器）启动时，Windows 用 Windows Terminal 承载其 stdout/stderr，**必弹一个可见窗口**。
- VBS `ws.Run "xxx", 0, False` 的 SW_HIDE **只对 GUI 程序有效，对 console 程序无效** —— 这是"隐藏启动仍然弹窗"的头号根因。
- 多层 python 包装（`cli.exe` → `python.exe` → `uv python` → `真正程序.exe`）每层都是 console，每层都可能带 conhost。
- 命令行里出现 `-Embedding` 的 `WindowsTerminal.exe` / `OpenConsole.exe` = 被当默认终端承载。

## 唯一可靠解法：pythonw + CREATE_NO_WINDOW
pythonw.exe 自身是 GUI 子系统（无控制台）；子进程用 `CREATE_NO_WINDOW (0x08000000)` 标志就不分配控制台。

### 1. 写启动器 `start_x.pyw`（用 pythonw 运行）
```python
import subprocess, os
os.environ.pop("PYTHONPATH", None)   # 防她机 the harness venv 污染 import（本机坑）
CREATE_NO_WINDOW = 0x08000000
subprocess.Popen(
    [r"C:\path\to\xxx.exe", "arg1"],
    cwd=r"C:\working\dir",
    creationflags=CREATE_NO_WINDOW,
    close_fds=True,
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
# 出错时写 error 日志（pythonw 无控制台，错误只能落盘）
```
注意：`0x08000000` 与 `DETACHED_PROCESS(0x8)` **互斥**，二选一。DETACHED 也可防弹窗但无 stdin/stdout。

### 2. 从 vbs / 快捷方式调用该 pyw
```vbs
Set ws = CreateObject("Wscript.Shell")
ws.Run """C:\...\pythonw.exe"" ""C:\...\start_x.pyw""", 0, False
```
改快捷方式（桌面/开始菜单）：Target = pythonw.exe，Arguments = `"C:\...\start_x.pyw"`，保留原 IconLocation。用 PowerShell 改写：
```powershell
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
$s.TargetPath = "C:\...\pythonw.exe"; $s.Arguments = '"C:\...\start_x.pyw"'
$s.IconLocation = "C:\...\原程序.exe,0"; $s.Save()
```

### 3. 验证（必须实测，不许"应该没问题"）
- 用新方式启动一次，`Get-Process | Where-Object {$_.MainWindowTitle -ne ''}` 确认**无新弹窗**。
- console 程序带单实例锁时，重复启动会安全退出、进程消失、不弹窗（这是验证的好方式）。
- 对比窗口列表前后采样，确认没新增 WindowsTerminal/conhost。

### ⚠️ console_script launcher 的 re-exec 陷阱：带 CREATE_NO_WINDOW 也闪（日期已脱敏 实测）
- **uv/pip 装的 console 程序**（`your-service.exe`、各种 `xxx_cli`）不是单进程：它是个 launcher，启动后 `re-exec` venv `python.exe` → 再 re-exec uv base `python.exe`。**每层 re-exec 都可能重建一个新 console**，把父进程传入的 `CREATE_NO_WINDOW`/`DETACHED` 丢掉 → 即便父进程带了 flags 照样闪窗。查 `Get-CimInstance` 看到 `xxx-server.exe → python.exe → python.exe` 多层父子链 + 伴随 `conhost.exe` 新建 = 就是这个。
- **正解**：绕开 launcher，直接 `pythonw -c "from xxx_cli.xxx import main; main()"` 调模块入口。⚠️ 模块入口一般从自身配置文件读 host/port（如 your-stack 从 `ov.conf`），无需透传 `--host/--port`；若入口吃 `sys.argv`，注意 `--config` 类参数仍要能传进 `-c` 串里。
- **既要无窗又要捕获 stdout**（cron 脚本场景）：不能直接用 pythonw（会丢 stdout）。照抄 the harness 的 `cron/scheduler.py::_windows_cron_python_invocation`：**绕过 venv launcher，直接用 base python.exe + 环境覆盖 venv 路径**（`VIRTUAL_ENV`=venv目录、`PYTHONPATH` 加 site-packages），再配 `creationflags=CREATE_NO_WINDOW` + `capture_output=True`。这条链无弹窗且输出可回捕。

### ⚠️ 多路自动重启竞态 = "疯狂闪"（日期已脱敏 实战）
- 一个服务被**两个独立触发点自动拉起**（例：the harness 插件 auto-start + cron 崩溃守护），一旦服务**静默死亡**，两条路**同时竞速重启**，每次各弹一次窗 → 用户看到"疯狂闪终端"。单服务的防抖（15s）管不住两个独立触发者。
- **修复**：所有启动入口统一指向**同一个带单实例保护的 headless 启动器**（一个 .pyw：先探活端口/health，已在监听直接 `sys.exit(0)`，再 pythonw+模块入口拉起）。竞态里第二次触发被单实例检查拦截，天然不重弹。
- **抓"正在闪"现场（in-the-act）**：用户说"刚刚疯狂闪了"时不要猜配置，立刻：
  ```powershell
  Get-CimInstance Win32_Process | Where-Object {$_.Name -match 'python|conhost|cmd|bash'} |
    Select-Object ProcessId,ParentProcessId,Name,CreationDate,CommandLine | Sort CreationDate -Descending | Select -First 15 | Format-List
  ```
  CreationDate 同为最近几秒的进程链 = 刚被拉起的实例；沿 `ParentProcessId` 追到发起者（cron guard/插件脚本），实锤是谁在拉、拉了几层。
- **服务静默死亡是引爆点**：闪窗只是表面，先查被守护服务日志最后一刻确认死因，否则修好弹窗后重启循环仍在上演。

## ⚠️ 单实例保护（防 0xc0000142 重复启动冲突）
多启动点（开机自启 + 快捷方式 + 登录恢复）**几乎同时各拉一次**时，第二个实例的 DLL 初始化会与已存在进程冲突，弹 `0xc0000142 应用程序无法正常启动`。给无窗启动器加**单实例检测**：先探测目标是否已运行，已运行直接 `sys.exit(0)` 跳过。
```python
def running():
    import subprocess
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process -Name Something -ErrorAction SilentlyContinue).Count"],
        capture_output=True, text=True, timeout=20)
    n = r.stdout.strip()
    return n.isdigit() and int(n) > 0
```
```python
if running():
    print("已在运行，跳过", file=open(LOG,'a')); sys.exit(0)
```
**坑**：探测**不要用 `tasklist /FI "IMAGENAME eq X.exe"` 解析文本**——中文系统输出编码问题会让 `stdout` 变 `None`/乱码，`X in None` 直接抛 `'NoneType' is not iterable`，导致单实例判断失败、又拉起一个实例。用 PowerShell `Get-Process` 返回纯数字最稳。
验证：the app is already running时再调用启动器，日志应显示\"已在运行，跳过\"，窗口数不增加。

## ⚠️ 子进程再 spawn：server 类程序的\"常驻日志窗口\"
server 程序（如 your-stack）内部可能用 `sys.executable` + `subprocess.Popen` 再起一个 **console 版 python** 子进程（uvicorn 多 worker / bot 网关 / 纯 `-c` 调用）。即使外层用了 pythonw 无窗，这个子进程是 console 版，仍会弹**一个稳定常驻**的窗口承载 stdout。
- **判断它是不是\"问题\"**：窗口数是否**稳定不新增**。稳定 1 个 = 运行时日志窗口（属于程序设计，可接受或另行把 stdout 重定向到文件）；若持续新增 = 真弹窗循环，需查父进程、单实例锁。
- 根治要让子进程也无窗：查程序 bootstrap 源码里 `python_cmd = sys.executable` 那段，改 stdout 重定向到日志文件、或用 `uvicorn.run` 的日志配置关掉控制台输出。

## ⚠️ 危险操作红牌
**不要用"关终端窗口"来清弹窗**。若目标是跑在终端里的 console 程序（如 `app.exe desktop`），点终端关闭按钮会**连带杀死该 console 程序本体**（the app itself被误操作杀掉过）。正确做法：改启动方式 → 重启验证，而不是去关那个窗口。

## 排查辅助：判断弹窗源
1. 列出所有可见窗口 `Get-Process | Where-Object {$_.MainWindowTitle -ne ''}`。
2. 查进程树 `Get-CimInstance Win32_Process | Select ProcessId,ParentProcessId,Name,CommandLine`，看谁拉起了 console 链。
3. 多个 `cmd /c npx xxx-mcp` 反复新建 = MCP server 崩溃循环（每次走 cmd 弹窗）。
4. explorer 重启会重跑 Startup 文件夹全部项 → 一次弹一堆（explorer 崩溃时更明显）。
5. **抓\"疯狂跳\"现场**：`../scripts/watch_popups.py` 每 5 秒采样，凡是新出现的 conhost/cmd/python/wt 进程都打父链 + 命令行——循环弹 vs 稳定常驻一眼分清（见 ../scripts/watch_popups.py）。

## 备份与回滚
改 vbs / 快捷方式前先备份到 `%LOCALAPPDATA%\app\backups\<日期>/`，报给用户完整路径。保持 Icon/Description 一致以便回滚后视觉不变。

## 参考
- `default-terminal-diagnostics.md`：原理 + 诊断命令 + 实战案例。
- `silent-launch-case-service.md`：同目录实战案例（console_script re-exec 链 + 双触发点竞态 + 插件/守护双改法 + 验证证据）。
