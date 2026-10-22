# RM27_Client

T06 干净骨架：C++17 / Qt 6 / QML 客户端，Python 独立模拟器。

当前只提供启动、运行模式标记、配置校验、基础日志及测试入口。窗口显示“正式/模拟”和“未连接”，回放按钮禁用。没有比赛业务、通信、图传、机器人操控或演示数据；客户端不会自动启动模拟器。

学习整个骨架的目录、文件、函数、每行代码及运行流程，见 [骨架结构与逐行解读](docs/骨架结构与逐行解读.md)。

## 目录

```text
RM27_Client/
├─ .vscode/                   # Task Buttons 任务、按钮和 C++ 调试配置
├─ CMakeLists.txt             # C++ 构建与 CTest 入口
├─ CMakePresets.json          # Windows MinGW Debug / Release
├─ apps/client/
│  ├─ main.cpp                # 客户端启动与模块组装
│  └─ qml/Main.qml            # 最小窗口
├─ libs/
│  ├─ domain/                 # 与 Qt 无关的运行模式定义
│  ├─ config/                 # JSON 读取及错误定位
│  └─ diagnostics/            # 启动、错误、退出 JSONL 日志
├─ configs/                  # 公共默认配置和模拟模式示例
├─ simulator/
│  ├─ server/main.py          # 独立常驻入口，Ctrl+C 退出
│  └─ tests/                  # Python 标准库测试
├─ tests/unit/               # 配置、日志、QML 启动检查
├─ docs/T06验收记录.md
└─ 开发环境.md               # 本机工具版本和路径
```

后续模块按任务增加，不预建完整业务目录。参考项目固定副本在上级 `research/reference/RM26_Client`，仅借鉴 C++17、Qt、CMake/CTest 和独立 Python 入口的组织方式，未复制其业务代码或素材。

## 构建与启动

VS Code 请打开本 README 所在的内层 `RM27_Client` 文件夹。本机路径沿用 [开发环境.md](开发环境.md)：Qt 6.11.2 MinGW x64、Qt 配套 G++ 13.1.0、CMake 3.30.5、Ninja 1.12.1，Python 为 `E:/miniconda3/python.exe`。

构建、运行和测试命令直接定义在 `.vscode/tasks.json`，不再依赖独立 PowerShell 脚本。`Ctrl+Shift+B` 默认配置并构建 Debug；普通启动使用下文的 RM运行按钮。

不使用 VS Code 时，可以在项目根目录执行等价命令：

```powershell
# 配置并构建 Debug（Release 替换预设名中的 debug）
& 'D:/Qt6/Tools/CMake_64/bin/cmake.exe' --preset windows-mingw-debug
& 'D:/Qt6/Tools/CMake_64/bin/cmake.exe' --build --preset windows-mingw-debug

# 为当前终端补充运行依赖路径，然后启动正式模式
$env:PATH = 'D:/Qt6/6.11.2/mingw_64/bin;D:/Qt6/Tools/mingw1310_64/bin;' + $env:PATH
& './build/windows-mingw-debug/bin/RM27_Client.exe'

# 启动模拟模式；不会启动或连接模拟器
& './build/windows-mingw-debug/bin/RM27_Client.exe' --config './configs/simulation.example.json'
```

在另一个 PowerShell 窗口中，独立启动模拟器：

```powershell
Push-Location ./simulator
& 'E:/miniconda3/python.exe' -m server.main
# Ctrl+C 正常退出

# 仅检查模拟器入口，立即退出
& 'E:/miniconda3/python.exe' -m server.main --check
Pop-Location
```

也可在 `simulator` 目录执行 `E:/miniconda3/python.exe -m server.main`。当前模拟器只记录启动/退出并等待，不打开网络端口，不收发数据，不需要 Broker、第三方 Python 包或客户端。

## VS Code / Task Buttons

VS Code 请打开本 README 所在的内层 `RM27_Client` 文件夹。`.vscode/tasks.json`（文件名带 `s`）定义任务，`.vscode/settings.json` 为已安装的 Task Buttons 插件绑定状态栏按钮：

| 按钮 | 操作 |
| --- | --- |
| RM构建 | 选择 Debug/Release，直接执行 CMake 配置和构建 |
| RM运行 | 选择构建类型和正式/模拟模式，先构建，再直接启动 exe |
| RM测试 | 选择 Debug/Release，依次配置、构建、运行 CTest 和 Python unittest |
| RM模拟器 | 使用指定的 Python 执行 `server.main`；可常驻或仅检查入口 |

`Ctrl+Shift+B` 默认构建 Debug。`Ctrl+Shift+P` → `Tasks: Run Task` 可选择全部 15 个任务，其中配置、CTest、Python 单测是组合任务调用的子步骤。按钮没有显示时，执行 `Developer: Reload Window`；原有 CMake Tools 按钮属于另一套入口，不会自动调用这些 VS Code 任务。

F5 使用 `.vscode/launch.json`。在“运行和调试”中选择 `RM27: Debug Client (Official)` 或 `RM27: Debug Client (Simulation)`，在 `main.cpp` 等 C++ 文件中设置断点，然后按 F5。调试前自动执行 `RM27: Build Debug`，随后由指定的 GDB 直接启动客户端，PATH 显式包含 Qt 和 MinGW DLL 目录。F10 单步跳过，F11 单步进入，F5 继续，Shift+F5 停止。

普通运行任务直接启动 exe，任务的 `options.env.PATH` 显式包含 Qt 和 MinGW DLL 目录；C++ 断点调试由 GDB 启动 exe。当前 launch 配置用于 C++，QML/Python 断点不在本次配置范围。关闭客户端窗口可结束运行任务；模拟器在任务终端按 Ctrl+C 退出。

任务采用 `type: process` 直接调用程序，不需要 PowerShell 执行策略或脚本编码设置。`dependsOn` 和 `dependsOrder: sequence` 保证按顺序执行，前一步失败则停止后续依赖链。任务的环境变量只作用于任务进程及其子进程，不修改 Windows 用户或系统 PATH。移动工具安装位置时，同步调整 tasks、CMake 预设及 launch 中的工具/DLL 路径。

Debug 的完整测试依赖链为：`Test Debug → CTest Debug → Build Debug → Configure Debug`；配置、构建、CTest 成功后，`Test Debug` 再执行 `Python Tests`。F5 的 `preLaunchTask` 仍指向 `Build Debug`。

## 配置与日志

默认配置 `configs/defaults.json` 在构建时嵌入客户端，内容为 `{"mode":"official"}`，启动不依赖当前工作目录。修改该文件后需重新构建。客户端使用 `--config` 指定外部 JSON；相对路径按客户端工作目录解析，VS Code 模拟模式任务传入的是绝对路径。

当前只接受一个必填字段：`mode`，值为 `official` 或 `simulation`。回放值、未知字段、错误类型、损坏 JSON 和文件读取失败均报错。真实配置可保存为被 Git 忽略的 `configs/local*.json`。

配置失败时窗口仍打开，显示“未确定（配置错误）”“未连接”，并列出配置绝对路径、错误原因；JSON 解析失败还显示字节偏移。不回退到其他配置。骨架尚无网络模块，也没有默认服务器地址。

客户端日志：项目根目录下的 `logs/client.jsonl`，窗口底部显示实际绝对路径。项目根目录由 CMake 在编译时注入，不受启动时工作目录影响；移动源码目录后需重新配置和构建。`logs/` 和项目根目录散落的 `.log`、`.jsonl` 文件均由 `.gitignore` 排除。日志记录 UTC 时间、级别、事件与启动模式/错误，写入失败在启动窗口提示。当前只有基础启动日志，日志轮转及诊断导出属于 T26。模拟器日志输出到终端。

## 检查与后续范围

```powershell
# VS Code 的 RM测试按钮会先构建，再依次执行下面两部分
& 'D:/Qt6/Tools/CMake_64/bin/ctest.exe' --preset windows-mingw-debug --no-tests=error
Push-Location ./simulator
& 'E:/miniconda3/python.exe' -m unittest discover -s tests -p 'test_*.py' -v
Pop-Location
```

CTest 检查配置边界、JSONL 写入/打开失败，以及正式/模拟/配置错误窗口中的“未连接”和禁用回放入口。Python 检查模拟器入口和退出行为。实际验证结果见 [T06 验收记录](docs/T06验收记录.md)。

本机预设显式选择 Qt 附带工具，不使用全局 PATH 中的 MSYS2 编译器。换机器需同步调整 `CMakePresets.json`、`.vscode/tasks.json`、`.vscode/launch.json` 中的工具路径；个性化预设可放入被忽略的 `CMakeUserPresets.json`。

当前启动任务依赖本机 Qt 开发环境。T07 干净机部署、T08 协议核对及后续业务尚未完成。

