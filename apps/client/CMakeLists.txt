qt_add_executable(RM27_Client WIN32
    main.cpp
    ClientApplication.cpp
    ClientApplication.h
    client.qrc
)
target_link_libraries(RM27_Client PRIVATE
    rm27_config rm27_diagnostics rm27_transport rm27_presentation rm27_protocol
    Qt6::Gui Qt6::Qml Qt6::Quick Qt6::QuickControls2
)
target_compile_definitions(RM27_Client PRIVATE
    RM27_VERSION="${PROJECT_VERSION}"
)
set_target_properties(RM27_Client PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

if(BUILD_TESTING)
    find_package(Qt6 REQUIRED COMPONENTS Test)
    add_executable(RM27_SessionCheck ../../tests/BasicSessionCheck.cpp)
    target_link_libraries(RM27_SessionCheck PRIVATE rm27_application rm27_config)
    set_target_properties(RM27_SessionCheck PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
    add_test(NAME basic_session COMMAND RM27_SessionCheck)

    qt_add_executable(RM27_MqttCheck ../../tests/MqttReceiveCheck.cpp client.qrc)
    target_link_libraries(RM27_MqttCheck PRIVATE rm27_transport rm27_presentation rm27_config
        Qt6::Gui Qt6::Qml Qt6::Quick Qt6::QuickControls2 Qt6::Test)
    set_target_properties(RM27_MqttCheck PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
endif()
