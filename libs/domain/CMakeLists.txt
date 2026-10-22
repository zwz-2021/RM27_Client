add_library(rm27_domain STATIC RunMode.cpp RunMode.h)
set_target_properties(rm27_domain PROPERTIES AUTOMOC OFF)
target_include_directories(rm27_domain PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/..")

