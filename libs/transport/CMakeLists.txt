add_library(rm27_transport STATIC
    MockDataSource.cpp
    MockDataSource.h
    UnavailableDataSource.cpp
    UnavailableDataSource.h
)
target_include_directories(rm27_transport PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/..")
target_link_libraries(rm27_transport PUBLIC rm27_application)
