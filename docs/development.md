# 本地开发

项目使用 Qt Quick / C++17，只保留本地构建和运行流程，不要求 CI/CD、CTest 或 Qt Test。

## Windows / Qt MinGW：首次配置

需要 Qt 6.8 或以上（Core、Gui、Qml、Quick、QuickControls2）、与 Qt 套件匹配的 MinGW、CMake 3.21 或以上及 Ninja。两个脚本兼容 Windows PowerShell 5.1 和 PowerShell 7。

1. 将 `CMakeUserPresets.json.example` 复制为 `CMakeUserPresets.json`。
2. 修改其中 `local-debug`、`local-release` 的四个路径：

   | 变量 | 路径内容 | 本机示例 |
   | --- | --- | --- |
   | `RM27_QT_ROOT` | Qt MinGW 套件根目录 | `D:/Qt6/6.11.2/mingw_64` |
   | `RM27_MINGW_ROOT` | MinGW 根目录 | `D:/Qt6/Tools/mingw1310_64` |
   | `RM27_NINJA_ROOT` | 含 ninja.exe 的目录 | `D:/Qt6/Tools/Ninja` |
   | `RM27_CMAKE_ROOT` | CMake 根目录，内含 bin/cmake.exe | `D:/Qt6/Tools/CMake_64` |

3. 使用下方脚本或 VS Code 按钮。

这四项填写绝对路径，不需要另外设置系统环境变量。脚本从所选本地预设读取工具路径，CMake 负责继承公共预设。保持模板中的预设名称和继承关系即可；其他开发者只需修改自己的用户预设。

`CMakePresets.json` 保存共享构建规则；`CMakeUserPresets.json.example` 是可提交的模板；实际的 `CMakeUserPresets.json` 已被 Git 忽略，保存本机路径。本机已经配置完成，不必重新复制模板。

## 构建与运行脚本

以下命令在项目根目录执行。脚本自身通过所在目录定位项目，因此从其他工作目录传入脚本绝对路径也能使用。

```powershell
# 配置并构建；默认 Debug，最多使用 8 个并行编译任务
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1 -Configuration Release

# 先增量构建，再运行；默认 Debug / 正式模式
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -Mode simulation
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -Configuration Release -Mode simulation

# 已完成构建时跳过编译，并使用个人配置和日志目录
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -SkipBuild -ConfigFile configs/local.json -LogDirectory logs
```

`-ExecutionPolicy Bypass` 只作用于这次启动的 PowerShell 进程，不修改系统执行策略。允许直接执行脚本的终端，也可使用 `./scripts/build.ps1` 和 `./scripts/run.ps1`。

- 构建产物位于 `build/local-debug/bin/` 或 `build/local-release/bin/`。
- `build.ps1 -Jobs 4` 可调整编译并行数。配置或编译失败会返回非零退出码。
- `run.ps1` 从构建缓存读取实际使用的 Qt 和编译器位置，临时补齐运行时 PATH；关闭窗口后任务结束。不会永久修改系统 PATH。
- `-ConfigFile` 优先于 `-Mode`；脚本参数中的相对配置和日志路径以项目根目录为基准。
- 正式模式使用内嵌默认配置；模拟模式使用 `configs/simulation.example.json`。
- 构建前关闭同版本客户端，避免 Windows 锁定 exe 导致链接失败。
- 不要同时启动多个相同版本的构建任务。

若希望直接使用 CMake，先保证 cmake.exe 在 PATH 中，再执行 `cmake --preset local-debug` 和 `cmake --build --preset local-debug`。Qt Creator 也可以直接打开根 CMakeLists.txt 并选择匹配的 Kit。更换 Qt 或编译器时使用新的构建目录，避免复用旧缓存。

## VS Code 按钮

扩展 ID：`spencerwmiles.vscode-task-buttons`（Task Buttons）。本机已安装，项目的 `.vscode/extensions.json` 也为其他开发者提供安装推荐。

打开本项目文件夹后，状态栏有两个按钮：

- **构建**：选择 Debug 或 Release，调用 `scripts/build.ps1`。
- **运行**：选择 Debug/Release 与正式/模拟模式，调用 `scripts/run.ps1`，自动先构建。

`.vscode/settings.json` 定义按钮，`.vscode/tasks.json` 定义实际命令；它们不包含本机工具安装路径。`Ctrl+Shift+B` 默认构建 Debug，也可通过命令面板的 `Tasks: Run Task` 选择任务。若按钮未显示，确认扩展已启用，执行 `Developer: Reload Window`。

## 运行配置与日志

程序不传 `--config` 时读取编入资源的 `configs/defaults.json`。默认 `official` 模式目前只显示正式通信尚未接入；`simulation` 使用内部定时器生成演示心跳，不启动 Python 模拟器。

个人配置可以保存为 `configs/local.json`（已被 Git 忽略）：

```json
{
  "mode": "simulation",
  "window": { "title": "RM27 Client", "width": 1280, "height": 800 },
  "simulation": { "intervalMs": 500 },
  "logging": { "directory": "../logs" }
}
```

`mode` 必填，其他节可省略。窗口标题必须非空，宽度 640～7680、高度 480～4320；模拟间隔为 100～60000 毫秒的整数。未知字段或无效类型会显示错误。外部配置修改后重启生效；内嵌默认配置修改后需要重新编译。

日志目录省略或为空时，写入系统应用本地数据目录下的 `logs/`；文件名包含时间和进程 ID，界面的“运行信息”页显示路径。日志记录启动、会话变化和退出。

配置内 `logging.directory` 的相对路径以配置文件所在目录为基准。脚本的 `-LogDirectory` 优先于配置。直接启动 exe 时，`--config`、`--log-dir` 的相对路径以进程工作目录为基准。

## 其他平台与部署

当前公共预设针对 Windows MinGW。Linux/macOS 可以直接用 CMake 配置，无须使用 PowerShell 脚本：

```sh
cmake -S . -B build/local -G Ninja -DCMAKE_BUILD_TYPE=Debug -DCMAKE_PREFIX_PATH=/path/to/Qt
cmake --build build/local
./build/local/bin/RM27_Client
```

以上均为源码开发流程。将程序复制到其他机器前，还需使用 Qt 平台部署工具收集 DLL、插件和 QML 依赖；运行脚本不代替部署步骤。

客户端当前不需要 Paho MQTT、Protobuf、FFmpeg 或 Docker。仅运行独立 Python 模拟器入口时需要 Python 3.10 或以上，可用 `python -m simulator.server.main --check` 检查入口。

模块职责见 [项目架构](architecture.md)，独立模拟器现状见 [simulator/README.md](../simulator/README.md)。
