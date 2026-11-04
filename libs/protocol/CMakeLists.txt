set(base_schema "${CMAKE_CURRENT_SOURCE_DIR}/proto/rm27_base.proto")
set(base_generated "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY "${base_generated}")
add_custom_command(
    OUTPUT "${base_generated}/rm27_base.pb.cc" "${base_generated}/rm27_base.pb.h"
    COMMAND $<TARGET_FILE:protobuf::protoc>
        "--proto_path=${CMAKE_CURRENT_SOURCE_DIR}/proto"
        "--cpp_out=${base_generated}" "${base_schema}"
    DEPENDS "${base_schema}" protobuf::protoc
    VERBATIM
)
add_library(rm27_protocol STATIC BasicCodec.cpp BasicCodec.h
    "${base_generated}/rm27_base.pb.cc" "${base_generated}/rm27_base.pb.h")
target_include_directories(rm27_protocol PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/.."
    PRIVATE "${base_generated}")
target_link_libraries(rm27_protocol PUBLIC rm27_domain Qt6::Core PRIVATE protobuf::libprotobuf)

if(BUILD_TESTING)
    add_executable(RM27_ProtocolCheck tests/BasicCodecCheck.cpp)
    target_link_libraries(RM27_ProtocolCheck PRIVATE rm27_protocol)
    set_target_properties(RM27_ProtocolCheck PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
    add_test(NAME protocol_basic COMMAND RM27_ProtocolCheck)
endif()
