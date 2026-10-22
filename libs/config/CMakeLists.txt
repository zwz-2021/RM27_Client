add_library(rm27_config STATIC AppConfig.cpp AppConfig.h)
target_include_directories(rm27_config PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/..")
target_link_libraries(rm27_config PUBLIC rm27_domain Qt6::Core)

