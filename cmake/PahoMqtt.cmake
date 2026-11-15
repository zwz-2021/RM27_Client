# MQTT transport uses the asynchronous C API, compiled with the client toolchain.
# Source and licenses: https://github.com/eclipse-paho/paho.mqtt.c/tree/v1.3.15
include(FetchContent)
if(POLICY CMP0135)
    cmake_policy(SET CMP0135 NEW)
endif()
set(_rm27_paho_automoc "${CMAKE_AUTOMOC}")
set(_rm27_paho_autorcc "${CMAKE_AUTORCC}")
set(CMAKE_AUTOMOC OFF)
set(CMAKE_AUTORCC OFF)
set(PAHO_BUILD_SHARED OFF CACHE BOOL "" FORCE)
set(PAHO_BUILD_STATIC ON CACHE BOOL "" FORCE)
set(PAHO_WITH_SSL OFF CACHE BOOL "" FORCE)
set(PAHO_BUILD_SAMPLES OFF CACHE BOOL "" FORCE)
set(PAHO_BUILD_DOCUMENTATION OFF CACHE BOOL "" FORCE)
set(PAHO_ENABLE_TESTING OFF CACHE BOOL "" FORCE)
set(PAHO_ENABLE_CPACK OFF CACHE BOOL "" FORCE)
set(PAHO_HIGH_PERFORMANCE ON CACHE BOOL "" FORCE)
FetchContent_Declare(paho_mqtt_c
    URL https://github.com/eclipse-paho/paho.mqtt.c/archive/refs/tags/v1.3.15.tar.gz
    URL_HASH SHA256=60ce2cfdc146fcb81c621cb8b45874d2eb1d4693105d048f60e31b8f3468be90
    DOWNLOAD_DIR "${RM27_DEPENDENCY_DOWNLOAD_DIR}"
    DOWNLOAD_NAME paho-mqtt-c-v1.3.15.tar.gz
)
# Offline builds may set FETCHCONTENT_SOURCE_DIR_PAHO_MQTT_C to this exact source.
FetchContent_MakeAvailable(paho_mqtt_c)
set_property(DIRECTORY "${paho_mqtt_c_SOURCE_DIR}" PROPERTY EXCLUDE_FROM_ALL TRUE)
set(CMAKE_AUTOMOC "${_rm27_paho_automoc}")
set(CMAKE_AUTORCC "${_rm27_paho_autorcc}")
unset(_rm27_paho_automoc)
unset(_rm27_paho_autorcc)
