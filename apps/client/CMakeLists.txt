qt_add_executable(RM27_Client WIN32 main.cpp client.qrc)
target_link_libraries(RM27_Client PRIVATE
    rm27_config rm27_diagnostics Qt6::Gui Qt6::Qml Qt6::Quick Qt6::QuickControls2
)
target_compile_definitions(RM27_Client PRIVATE
    RM27_PROJECT_ROOT="${CMAKE_SOURCE_DIR}"
)
set_target_properties(RM27_Client PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

