qt_add_executable(RM27_Client WIN32
    main.cpp
    ClientApplication.cpp
    ClientApplication.h
    SimulationVideoDecode.cpp
    SimulationVideoDecode.h
    LinkDiagnostics.cpp
    LinkDiagnostics.h
    client.qrc
)
find_package(Qt6 REQUIRED COMPONENTS Concurrent)
target_link_libraries(RM27_Client PRIVATE
    rm27_config rm27_diagnostics rm27_transport rm27_presentation rm27_protocol
    Qt6::Gui Qt6::Qml Qt6::Quick Qt6::QuickControls2 Qt6::Multimedia Qt6::Concurrent
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

    add_executable(RM27_LinkDiagnosticsCheck ../../tests/LinkDiagnosticsCheck.cpp
        LinkDiagnostics.cpp LinkDiagnostics.h)
    target_include_directories(RM27_LinkDiagnosticsCheck PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    target_link_libraries(RM27_LinkDiagnosticsCheck PRIVATE rm27_presentation)
    set_target_properties(RM27_LinkDiagnosticsCheck PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
    add_test(NAME link_diagnostics COMMAND RM27_LinkDiagnosticsCheck)

    qt_add_executable(RM27_MqttCheck ../../tests/MqttReceiveCheck.cpp client.qrc)
    target_link_libraries(RM27_MqttCheck PRIVATE rm27_transport rm27_presentation rm27_config
        Qt6::Gui Qt6::Qml Qt6::Quick Qt6::QuickControls2 Qt6::Test)
    set_target_properties(RM27_MqttCheck PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")

    if(RM27_FFMPEG_EXECUTABLE)
        add_executable(RM27_SimulationFrameDeliveryCheck ../../tests/SimulationFrameDeliveryCheck.cpp
            SimulationVideoDecode.cpp SimulationVideoDecode.h)
        target_include_directories(RM27_SimulationFrameDeliveryCheck PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
        target_link_libraries(RM27_SimulationFrameDeliveryCheck PRIVATE rm27_transport Qt6::Multimedia Qt6::Test)
        set_target_properties(RM27_SimulationFrameDeliveryCheck PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
        add_test(NAME simulation_frame_delivery COMMAND RM27_SimulationFrameDeliveryCheck)
        get_filename_component(ffmpeg_dir "${RM27_FFMPEG_EXECUTABLE}" DIRECTORY)
        set_tests_properties(simulation_frame_delivery PROPERTIES TIMEOUT 30 ENVIRONMENT "RM27_TEST_FFMPEG_DIR=${ffmpeg_dir}")
    endif()
endif()
