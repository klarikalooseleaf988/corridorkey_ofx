cmake_minimum_required(VERSION 3.20)
project(CorridorKeyForResolve LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# OFX SDK paths
set(OFX_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/openfx/include")
set(OFX_SUPPORT_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/openfx/Support/include")
set(OFX_SUPPORT_LIB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/openfx/Support/Library")

# OFX Support Library sources
set(OFX_SUPPORT_SOURCES
    ${OFX_SUPPORT_LIB_DIR}/ofxsCore.cpp
    ${OFX_SUPPORT_LIB_DIR}/ofxsImageEffect.cpp
    ${OFX_SUPPORT_LIB_DIR}/ofxsInteract.cpp
    ${OFX_SUPPORT_LIB_DIR}/ofxsLog.cpp
    ${OFX_SUPPORT_LIB_DIR}/ofxsMultiThread.cpp
    ${OFX_SUPPORT_LIB_DIR}/ofxsParams.cpp
    ${OFX_SUPPORT_LIB_DIR}/ofxsProperty.cpp
    ${OFX_SUPPORT_LIB_DIR}/ofxsPropertyValidation.cpp
)

# Plugin sources
set(PLUGIN_SOURCES
    src/PluginRegistration.cpp
    src/CorridorKeyPlugin.cpp
    src/CorridorKeyProcessor.cpp
    src/IPCClient.cpp
)

# Build as shared library (.ofx is a renamed DLL)
add_library(CorridorKeyForResolve SHARED
    ${PLUGIN_SOURCES}
    ${OFX_SUPPORT_SOURCES}
)

target_include_directories(CorridorKeyForResolve PRIVATE
    ${OFX_INCLUDE_DIR}
    ${OFX_SUPPORT_INCLUDE_DIR}
    ${OFX_SUPPORT_LIB_DIR}
    src
)

# Windows-specific settings
if(WIN32)
    target_compile_definitions(CorridorKeyForResolve PRIVATE
        _WINDOWS
        WIN32
        NOMINMAX
        WIN32_LEAN_AND_MEAN
    )
    # OFX plugins are .ofx files (renamed DLLs)
    set_target_properties(CorridorKeyForResolve PROPERTIES
        SUFFIX ".ofx"
        PREFIX ""
    )
endif()

# Install to OFX bundle structure
set(OFX_BUNDLE_DIR "${CMAKE_BINARY_DIR}/CorridorKeyForResolve.ofx.bundle/Contents")
add_custom_command(TARGET CorridorKeyForResolve POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory "${OFX_BUNDLE_DIR}/Win64"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${OFX_BUNDLE_DIR}/Resources"
    COMMAND ${CMAKE_COMMAND} -E copy "$<TARGET_FILE:CorridorKeyForResolve>" "${OFX_BUNDLE_DIR}/Win64/"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_CURRENT_SOURCE_DIR}/resources/com.corridordigital.corridorkey.png"
        "${OFX_BUNDLE_DIR}/Resources/"
    COMMENT "Assembling OFX bundle"
)
