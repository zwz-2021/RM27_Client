add_library(rm27_video STATIC
    HevcFileDecoder.cpp
    HevcFileDecoder.h
    VideoFrameAssembler.cpp
    VideoFrameAssembler.h
    UdpVideoStatus.h
)
target_include_directories(rm27_video PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/..")
target_link_libraries(rm27_video PUBLIC Qt6::Core PRIVATE Qt6::Network)

if(BUILD_TESTING)
    find_package(Qt6 REQUIRED COMPONENTS Test)
    add_executable(RM27_VideoFrameAssemblerCheck ../../tests/VideoFrameAssemblerCheck.cpp)
    target_link_libraries(RM27_VideoFrameAssemblerCheck PRIVATE rm27_video Qt6::Test)
    set_target_properties(RM27_VideoFrameAssemblerCheck PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
    add_test(NAME video_frame_assembler COMMAND RM27_VideoFrameAssemblerCheck)

    find_program(RM27_FFMPEG_EXECUTABLE ffmpeg)
    if(RM27_FFMPEG_EXECUTABLE)
        add_executable(RM27_HevcFileDecoderLifecycleCheck ../../tests/HevcFileDecoderLifecycleCheck.cpp)
        target_link_libraries(RM27_HevcFileDecoderLifecycleCheck PRIVATE rm27_video Qt6::Test)
        set_target_properties(RM27_HevcFileDecoderLifecycleCheck PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
        add_test(NAME hevc_file_decoder_lifecycle COMMAND RM27_HevcFileDecoderLifecycleCheck)
        get_filename_component(ffmpeg_dir "${RM27_FFMPEG_EXECUTABLE}" DIRECTORY)
        set_tests_properties(hevc_file_decoder_lifecycle PROPERTIES
            TIMEOUT 30 ENVIRONMENT "RM27_TEST_FFMPEG_DIR=${ffmpeg_dir}")
    endif()
endif()
