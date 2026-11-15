add_library(rm27_transport STATIC
    MockDataSource.cpp
    MockDataSource.h
    UnavailableDataSource.cpp
    UnavailableDataSource.h
    MqttDataSource.cpp
    MqttDataSource.h
)
target_include_directories(rm27_transport PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/..")
target_link_libraries(rm27_transport PUBLIC rm27_application
    PRIVATE rm27_protocol Qt6::Network paho-mqtt3a-static)
target_compile_definitions(rm27_transport PRIVATE PAHO_MQTT_STATIC=1)
