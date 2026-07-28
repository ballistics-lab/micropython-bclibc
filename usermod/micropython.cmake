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

# ── Version header ────────────────────────────────────────────────────────────
set(_VERSION_H  "${_USERMOD_DIR}/generated/bclibc_mp/version.h")
set(_VERSION_IN "${_MOD_DIR}/version.h.in")

if(NOT EXISTS "${_VERSION_H}")
    file(MAKE_DIRECTORY "${_USERMOD_DIR}/generated/bclibc_mp")
    execute_process(
        COMMAND git describe --tags --always
        WORKING_DIRECTORY "${_MOD_DIR}"
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
    "${_MOD_DIR}/bclibc/tiny_bclibc/include"
    "${_USERMOD_DIR}"
)

target_compile_definitions(usermod_tiny_bclibc INTERFACE
    TINY_BCLIBC_NO_THREAD_LOCAL
    TINY_BCLIBC_NO_ERR_BUF
)

# ── Precision ──────────────────────────────────────────────────────────────────
# Same MP_BCLIBC_PRECISION flag as usermod/micropython.mk (Make-based ports)
# -- and now the same default: single, not double. This file is used by the
# CMake-based ports (rp2, esp32, ...), which in practice always means a real
# MCU -- most have no double-precision FPU at all (RP2040/RP2350 included),
# so single is the sensible out-of-the-box default, letting a casual user
# just point USER_C_MODULES at this file with no extra flags. Pass
# -DMP_BCLIBC_PRECISION=double explicitly if your board's FPU actually
# supports it and you want the extra precision.
if(NOT MP_BCLIBC_PRECISION STREQUAL "double")
    target_compile_definitions(usermod_tiny_bclibc INTERFACE
        TINY_BCLIBC_SINGLE_PRECISION
        TINY_BCLIBC_FAST_ZERO_FIND
    )
endif()

target_link_libraries(usermod INTERFACE usermod_tiny_bclibc)
