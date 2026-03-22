cmake_minimum_required(VERSION 3.20)
project(BankAnalyzerQt LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_TOOLCHAIN_FILE "C:/path/to/vcpkg/scripts/buildsystems/vcpkg.cmake")  # Replace this

# Qt6 modules
find_package(Qt6 REQUIRED COMPONENTS Core Gui Quick Charts)

# Tesseract
find_package(Tesseract REQUIRED)

# ONNX Runtime (headers are in include, .lib in lib)
include_directories("C:/path/to/vcpkg/installed/x64-windows/include")
link_directories("C:/path/to/vcpkg/installed/x64-windows/lib")

file(GLOB_RECURSE SOURCES CONFIGURE_DEPENDS
    main.cpp
    src/**/*.cpp
    src/**/*.h
)

add_executable(${PROJECT_NAME} ${SOURCES})

target_link_libraries(${PROJECT_NAME}
    Qt6::Core
    Qt6::Gui
    Qt6::Quick
    Qt6::Charts
    tesseract
    onnxruntime
)
