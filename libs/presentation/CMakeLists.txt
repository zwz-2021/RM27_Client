add_library(rm27_presentation STATIC ClientViewModel.cpp ClientViewModel.h)
target_include_directories(rm27_presentation PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/..")
target_link_libraries(rm27_presentation PUBLIC rm27_application Qt6::Core)
