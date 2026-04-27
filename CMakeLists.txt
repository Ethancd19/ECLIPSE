cmake_minimum_required(VERSION 3.16)
# =====================================================================
# ORBIT - Open-source Research Benchmark for IoT Cryptography
# Top-level CMakeLists.txt: board-agnostic configuration
#
# Usage:
#   cmake -S . -B build -DBOARD=pico      -DALGO_SELECTED=ascon_aead128
#   cmake -S . -B build -DBOARD=stm32     -DALGO_SELECTED=ascon_aead128
#   cmake -S . -B build -DBOARD=nrf52     -DALGO_SELECTED=ascon_aead128
#
# Note: ESP32-C61 uses ESP-IDF and has its own build system.
#       See platforms/esp32c61/ for ESP32-C61 build instructions.
# =====================================================================

# Board selection
if(NOT DEFINED BOARD)
    set(BOARD "pico")
    message(STATUS "Board not defined. Defaulting to BOARD=pico")
endif()

# Algorithm selection
if(NOT DEFINED ALGO_SELECTED)
    set(ALGO_SELECTED "ascon_aead128")
    message(STATUS "Algorithm not defined. Defaulting to ALGO_SELECTED=ascon_aead128")
endif()

#validate algorithm folder exists
set(ALGO_DIR "${CMAKE_SOURCE_DIR}/algorithms/${ALGO_SELECTED}")
if(NOT EXISTS "${ALGO_DIR}")
    message(FATAL_ERROR 
        "Algorithm folder not found: ${ALGO_DIR}\n"
        "Check -DALGO_SELECTED matches your algorithm folder name in ${CMAKE_SOURCE_DIR}/algorithms/${ALGO_SELECTED}"
    )
endif()

# PICO SDK setup
if(BOARD STREQUAL "pico")
    if(NOT DEFINED ENV{PICO_SDK_PATH})
        message(FATAL_ERROR
            "PICO_SDK_PATH environment variable not set.\n"
            "Run: export PICO_SDK_PATH=~/pico-sdk\n"
            "Or add it to ~/.bashrc"
        )        
    endif()
    include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
endif()

# Project setup

project(ORBIT C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(BOARD STREQUAL "pico")
    include(${CMAKE_SOURCE_DIR}/cmake/board_pico.cmake)
elseif(BOARD STREQUAL "stm32")
    include(${CMAKE_SOURCE_DIR}/cmake/board_stm32.cmake)
elseif(BOARD STREQUAL "nrf52")
    include(${CMAKE_SOURCE_DIR}/cmake/board_nrf52.cmake)
elseif(BOARD STREQUAL "rpi5")
    include(${CMAKE_SOURCE_DIR}/cmake/board_rpi5.cmake)
else()
    message(FATAL_ERROR
        "Unknown BOARD: '${BOARD}'\n"
        "Available boards: pico, stm32, nrf52, rpi5\n"
        "Note: ESP32-C61 uses ESP-IDF and has its own build system. See platforms/esp32c61/ for ESP32-C61 build instructions."
        )
endif()
