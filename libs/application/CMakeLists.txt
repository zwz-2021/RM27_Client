add_library(rm27_application STATIC
    IDataSource.h
    ClientSession.cpp
    ClientSession.h
)
target_include_directories(rm27_application PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/..")
target_link_libraries(rm27_application PUBLIC rm27_domain Qt6::Core)
