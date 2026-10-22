qt_add_executable(test_startup unit/test_startup.cpp)
target_link_libraries(test_startup PRIVATE rm27_config rm27_diagnostics Qt6::Test)
add_test(NAME startup COMMAND test_startup)

qt_add_executable(test_client_ui unit/test_client_ui.cpp ../apps/client/client.qrc)
target_link_libraries(test_client_ui PRIVATE
    Qt6::Test Qt6::Gui Qt6::Qml Qt6::Quick Qt6::QuickControls2
)
add_test(NAME client_ui COMMAND test_client_ui)
set_tests_properties(client_ui PROPERTIES
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QUICK_BACKEND=software"
)

