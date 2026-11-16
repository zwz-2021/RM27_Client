add_executable(RM27_HevcDecodeProbe main.cpp)
target_link_libraries(RM27_HevcDecodeProbe PRIVATE Qt6::Core)
set_target_properties(RM27_HevcDecodeProbe PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")

if(BUILD_TESTING)
    find_package(Python3 QUIET COMPONENTS Interpreter)
    find_program(RM27_FFMPEG_EXECUTABLE ffmpeg)
    find_program(RM27_FFPROBE_EXECUTABLE ffprobe)
    if(Python3_Interpreter_FOUND AND RM27_FFMPEG_EXECUTABLE AND RM27_FFPROBE_EXECUTABLE)
        add_test(NAME hevc_file_decode COMMAND "${Python3_EXECUTABLE}"
            "${PROJECT_SOURCE_DIR}/tests/check_hevc_decode.py" --probe $<TARGET_FILE:RM27_HevcDecodeProbe>
            --ffmpeg "${RM27_FFMPEG_EXECUTABLE}" --ffprobe "${RM27_FFPROBE_EXECUTABLE}")
    endif()
endif()
