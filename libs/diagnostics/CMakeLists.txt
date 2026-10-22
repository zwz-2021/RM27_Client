add_library(rm27_diagnostics STATIC JsonlLogger.cpp JsonlLogger.h)
target_include_directories(rm27_diagnostics PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/..")
target_link_libraries(rm27_diagnostics PUBLIC Qt6::Core)

