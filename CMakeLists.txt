#规定CMake版本最低为3.21
cmake_minimum_required(VERSION 3.21)
#声明工程名、版本和语言
project(RM27Client VERSION 0.1.0 LANGUAGES CXX)

#C++语言设置
set(CMAKE_CXX_STANDARD 17) #语言标准为C++17
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

#普通c++编译器无法编译Qt在c++基础上实现的自己的moc
set(CMAKE_AUTOMOC ON) #开启Qt的自动moc，在遇到需要moc处理的Qt宏时自动调用moc生成代码
set(CMAKE_AUTORCC ON) #rcc配置qrc（一种xml文本），自动处理图片等资源，将资源嵌入.exe
set(CMAKE_EXPORT_COMPILE_COMMANDS ON) #生成compile_command.json给vscode读取分析

find_package(Qt6 6.8 REQUIRED COMPONENTS Core Gui Qml Quick QuickControls2) #查找Qt6 并确保模块可用
include(CTest) #加入CTest，使得BUILD_TESTING默认为ON

# 将指定子目录加入当前 CMake 项目的构建过程，让 CMake 继续读取该子目录中的 CMakeLists.txt 文件
add_subdirectory(libs/domain)
add_subdirectory(libs/config)
add_subdirectory(libs/diagnostics)
add_subdirectory(apps/client)

if(BUILD_TESTING)
    find_package(Qt6 REQUIRED COMPONENTS Test)
    add_subdirectory(tests)
endif()

