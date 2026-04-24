# ===============================================================
# board_pico.cmake - Raspberry Pi Pico (RP2040, Cortex-M0+)
# Included by top-level CMakeLists.txt when BOARD=pico is selected
# ===============================================================

pico_sdk_init()

set(TARGET_NAME "ORBIT_${ALGO_SELECTED}_pico")

file(GLOB ALGO_SOURCES CONFIGURE_DEPENDS "${ALGO_DIR}/*.c")

add_executable(${TARGET_NAME}
    bench/main.c
    bench/util.c
    ${ALGO_SOURCES}
)

target_include_directories(${TARGET_NAME} PRIVATE
    include
    bench
    "${ALGO_DIR}"
    "platforms/pico"
)

target_compile_definitions(${TARGET_NAME} PRIVATE
    ALGO_NAME=${ALGO_SELECTED}
    BOARD_NAME="pico"
    VERSION_STR="0.1.0"
    COMPILER_ID="${CMAKE_C_COMPILER_ID}"
    COMPILER_VERSION="${CMAKE_C_COMPILER_VERSION}"
    COMPILER_FLAGS="-O2"
    TARGET_ARCH="armv6-m"
)

if(ALGO_SELECTED STREQUAL "aes_128_gcm")
    target_compile_definitions(${TARGET_NAME} PRIVATE SLOW_ALGO=1)
endif()

if(ALGO_SELECTED STREQUAL "ml_kem_512")
    target_compile_definitions(${TARGET_NAME} PRIVATE IS_KEM=1 SLOW_ALGO=1)
endif()

if(DEFINED ORBIT_ENERGY_RUNS)
    target_compile_definitions(${TARGET_NAME} PRIVATE ORBIT_ENERGY_RUNS=${ORBIT_ENERGY_RUNS})
endif()

if(ORBIT_NO_STDIO_WAIT)
    target_compile_definitions(${TARGET_NAME} PRIVATE ORBIT_NO_STDIO_WAIT=1)
endif()

target_compile_options(${TARGET_NAME} PRIVATE -O2 -Wall -Wextra)

target_link_libraries(${TARGET_NAME}
    pico_stdlib
    hardware_gpio
)

pico_enable_stdio_usb(${TARGET_NAME} 1)
pico_enable_stdio_uart(${TARGET_NAME} 0)
pico_add_extra_outputs(${TARGET_NAME})
