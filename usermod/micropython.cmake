# usermod/micropython.cmake
# USER_C_MODULES integration for MicroPython ports that use CMake.
#
# RP2040 / Pico SDK:
#   cmake -B build -DUSER_C_MODULES=/abs/path/to/usermod/micropython.cmake
#
# Unix port (make):
#   make -C ports/unix VARIANT=standard \
#       USER_C_MODULES=/abs/path/to/usermod/micropython.cmake \
#       FROZEN_MANIFEST=/abs/path/to/usermod/manifest.py
#
# ESP32 (IDF CMake):
#   idf.py build -DUSER_C_MODULES=/abs/path/to/usermod/micropython.cmake
#
# Windows (MSVC + cmake):
#   cmake -B build -G "Visual Studio 17 2022" \
#       -DUSER_C_MODULES=/abs/path/to/usermod/micropython.cmake

cmake_minimum_required(VERSION 3.13)

get_filename_component(_USERMOD_DIR "${CMAKE_CURRENT_LIST_FILE}" DIRECTORY)
get_filename_component(_MOD_DIR     "${_USERMOD_DIR}/.."         ABSOLUTE)
get_filename_component(_ROOT_DIR    "${_MOD_DIR}/.."             ABSOLUTE)

# ── Version header ────────────────────────────────────────────────────────────
set(_VERSION_H  "${_USERMOD_DIR}/generated/bclibc_mp/version.h")
set(_VERSION_IN "${_MOD_DIR}/version.h.in")

if(NOT EXISTS "${_VERSION_H}")
    file(MAKE_DIRECTORY "${_USERMOD_DIR}/generated/bclibc_mp")
    execute_process(
        COMMAND git describe --tags --always
        WORKING_DIRECTORY "${_ROOT_DIR}"
        OUTPUT_VARIABLE _GIT_TAG
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
    )
    if(NOT _GIT_TAG)
        set(_GIT_TAG "v0.0.0")
    endif()
    string(REGEX REPLACE "^v?([0-9]+).*"              "\\1" _MAJ "${_GIT_TAG}")
    string(REGEX REPLACE "^v?[0-9]+\\.([0-9]+).*"    "\\1" _MIN "${_GIT_TAG}")
    string(REGEX REPLACE "^v?[0-9]+\\.[0-9]+\\.([0-9]+).*" "\\1" _PAT "${_GIT_TAG}")
    foreach(_V _MAJ _MIN _PAT)
        if(NOT "${${_V}}" MATCHES "^[0-9]+$")
            set(${_V} 0)
        endif()
    endforeach()
    set(MP_BCLIBC_VERSION_MAJOR ${_MAJ})
    set(MP_BCLIBC_VERSION_MINOR ${_MIN})
    set(MP_BCLIBC_VERSION_PATCH ${_PAT})
    set(MP_BCLIBC_VERSION "${_MAJ}.${_MIN}.${_PAT}")
    configure_file("${_VERSION_IN}" "${_VERSION_H}" @ONLY)
endif()

# ── Module library ────────────────────────────────────────────────────────────
add_library(usermod_tiny_bclibc INTERFACE)

target_sources(usermod_tiny_bclibc INTERFACE
    "${_MOD_DIR}/src/tiny_bclibc_mp.c"
)

target_include_directories(usermod_tiny_bclibc INTERFACE
    "${_ROOT_DIR}/tiny_bclibc/include"
    "${_USERMOD_DIR}"
)

target_compile_definitions(usermod_tiny_bclibc INTERFACE
    TINY_BCLIBC_NO_THREAD_LOCAL
    TINY_BCLIBC_NO_ERR_BUF
)

# Precision: single by default; set TINY_BCLIBC_DOUBLE_PRECISION=1 (cmake var or env)
# for double.  The usermod/Makefile handles this via CFLAGS_USERMOD for unix-family
# targets (which bypass cmake's flag injection), so cmake precision only applies to
# cmake-native ports (rp2040, esp32, Windows).
if(NOT TINY_BCLIBC_DOUBLE_PRECISION AND NOT "$ENV{TINY_BCLIBC_DOUBLE_PRECISION}" STREQUAL "1")
    target_compile_definitions(usermod_tiny_bclibc INTERFACE
        TINY_BCLIBC_SINGLE_PRECISION
        MP_BCLIBC_SINGLE_PRECISION
        TINY_BCLIBC_FAST_ZERO_FIND
    )
endif()

target_link_libraries(usermod INTERFACE usermod_tiny_bclibc)
