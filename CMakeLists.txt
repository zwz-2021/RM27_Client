cmake_minimum_required(VERSION 3.21)
project(RM27Client VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# 源码与 QML 使用 UTF-8；MSVC 不依赖开发机器的系统代码页。
if(MSVC)
    add_compile_options(/utf-8)
endif()

find_package(Qt6 6.8 REQUIRED COMPONENTS Core Gui Qml Quick QuickControls2)

# 依赖方向由各模块 target_link_libraries 明确声明。
add_subdirectory(libs/domain)
add_subdirectory(libs/config)
add_subdirectory(libs/diagnostics)
add_subdirectory(libs/application)
add_subdirectory(libs/transport)
add_subdirectory(libs/presentation)
add_subdirectory(apps/client)
