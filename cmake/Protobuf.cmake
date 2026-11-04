# Build the codec with the same compiler as the client. Do not link a prebuilt
# MSVC Protobuf package into the Qt MinGW executable.
include(FetchContent)
if(POLICY CMP0135)
    cmake_policy(SET CMP0135 NEW)
endif()
set(_rm27_saved_automoc "${CMAKE_AUTOMOC}")
set(_rm27_saved_autorcc "${CMAKE_AUTORCC}")
set(CMAKE_AUTOMOC OFF)
set(CMAKE_AUTORCC OFF)

# The archives are shared by Debug/Release builds; sources and binaries remain
# isolated in each build tree. CMake verifies the hash before reusing an archive.
set(RM27_DEPENDENCY_DOWNLOAD_DIR "${CMAKE_SOURCE_DIR}/build/dependency-downloads"
    CACHE PATH "Cache directory for verified dependency source archives")

set(ABSL_BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(ABSL_ENABLE_INSTALL OFF CACHE BOOL "" FORCE)
set(ABSL_PROPAGATE_CXX_STD ON CACHE BOOL "" FORCE)
set(protobuf_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(protobuf_BUILD_CONFORMANCE OFF CACHE BOOL "" FORCE)
set(protobuf_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(protobuf_BUILD_PROTOBUF_BINARIES ON CACHE BOOL "" FORCE)
set(protobuf_BUILD_PROTOC_BINARIES ON CACHE BOOL "" FORCE)
set(protobuf_BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(protobuf_BUILD_LIBUPB OFF CACHE BOOL "" FORCE)
set(protobuf_WITH_ZLIB OFF CACHE BOOL "" FORCE)
set(protobuf_INSTALL OFF CACHE BOOL "" FORCE)

# Fixed releases, including hashes, also make clean builds reproducible. For an
# offline build CMake's FETCHCONTENT_SOURCE_DIR_ABSEIL / _PROTOBUF overrides may
# point at unpacked copies of these exact releases.
FetchContent_Declare(abseil
    URL https://github.com/abseil/abseil-cpp/archive/refs/tags/20240722.0.tar.gz
    URL_HASH SHA256=f50e5ac311a81382da7fa75b97310e4b9006474f9560ac46f54a9967f07d4ae3
    DOWNLOAD_DIR "${RM27_DEPENDENCY_DOWNLOAD_DIR}"
    DOWNLOAD_NAME abseil-20240722.0.tar.gz
)
FetchContent_MakeAvailable(abseil)

FetchContent_Declare(protobuf
    URL https://github.com/protocolbuffers/protobuf/archive/refs/tags/v29.3.tar.gz
    URL_HASH SHA256=008a11cc56f9b96679b4c285fd05f46d317d685be3ab524b2a310be0fbad987e
    DOWNLOAD_DIR "${RM27_DEPENDENCY_DOWNLOAD_DIR}"
    DOWNLOAD_NAME protobuf-v29.3.tar.gz
)
FetchContent_MakeAvailable(protobuf)
set_property(DIRECTORY "${abseil_SOURCE_DIR}" PROPERTY EXCLUDE_FROM_ALL TRUE)
set_property(DIRECTORY "${protobuf_SOURCE_DIR}" PROPERTY EXCLUDE_FROM_ALL TRUE)

# The client targets created after this include keep their Qt processing.
set(CMAKE_AUTOMOC "${_rm27_saved_automoc}")
set(CMAKE_AUTORCC "${_rm27_saved_autorcc}")
unset(_rm27_saved_automoc)
unset(_rm27_saved_autorcc)
