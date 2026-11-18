add_library(rm27_transport STATIC
    MockDataSource.cpp
    MockDataSource.h
    UnavailableDataSource.cpp
    UnavailableDataSource.h
    MqttDataSource.cpp
    MqttDataSource.h
    UdpPacketRateWindow.h
    UdpVideoReceiver.cpp
    UdpVideoReceiver.h
)
target_include_directories(rm27_transport PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/..")
target_link_libraries(rm27_transport PUBLIC rm27_application rm27_video
    PRIVATE rm27_protocol Qt6::Network paho-mqtt3a-static)
target_compile_definitions(rm27_transport PRIVATE PAHO_MQTT_STATIC=1)

if(BUILD_TESTING)
    find_package(Qt6 REQUIRED COMPONENTS Test)
    add_executable(RM27_UdpVideoCheck ../../tests/UdpVideoCheck.cpp)
    target_link_libraries(RM27_UdpVideoCheck PRIVATE rm27_transport Qt6::Network Qt6::Test)
    set_target_properties(RM27_UdpVideoCheck PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
    add_test(NAME udp_video_receiver COMMAND RM27_UdpVideoCheck)
endif()
