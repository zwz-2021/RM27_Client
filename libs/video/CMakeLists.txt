add_library(rm27_video STATIC
    VideoFrameAssembler.cpp
    VideoFrameAssembler.h
    UdpVideoStatus.h
)
target_include_directories(rm27_video PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/..")
target_link_libraries(rm27_video PUBLIC Qt6::Core)

if(BUILD_TESTING)
    find_package(Qt6 REQUIRED COMPONENTS Test)
    add_executable(RM27_VideoFrameAssemblerCheck ../../tests/VideoFrameAssemblerCheck.cpp)
    target_link_libraries(RM27_VideoFrameAssemblerCheck PRIVATE rm27_video Qt6::Test)
    set_target_properties(RM27_VideoFrameAssemblerCheck PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
    add_test(NAME video_frame_assembler COMMAND RM27_VideoFrameAssemblerCheck)
endif()
