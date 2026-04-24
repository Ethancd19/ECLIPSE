# ===============================================================
# board_nrf52.cmake - Nordic nRF52832 DK (PCA10040, Cortex-M4)
# Included by top-level CMakeLists.txt when BOARD=nrf52 is selected
#
# Requires Nordic nRF5 SDK at NRF5_SDK_PATH (default: ~/nRF5_SDK)
# Set via: cmake -DNRF5_SDK_PATH=/path/to/nRF5_SDK ...
#       or: export NRF5_SDK_PATH=~/nRF5_SDK
# ===============================================================

if(NOT CMAKE_C_COMPILER)
    set(CMAKE_C_COMPILER "arm-none-eabi-gcc")
endif()

if(DEFINED NRF5_SDK_PATH)
    set(NRF5_PATH "${NRF5_SDK_PATH}")
elseif(DEFINED ENV{NRF5_SDK_PATH})
    set(NRF5_PATH "$ENV{NRF5_SDK_PATH}")
else()
    set(NRF5_PATH "$ENV{HOME}/nRF5_SDK")
endif()

if(NOT EXISTS "${NRF5_PATH}/modules/nrfx/mdk/nrf.h")
    message(FATAL_ERROR
        "nRF5 SDK not found at: ${NRF5_PATH}\n"
        "Download or clone Nordic's nRF5 SDK and set NRF5_SDK_PATH to its root.\n"
        "Expected file: ${NRF5_PATH}/modules/nrfx/mdk/nrf.h"
    )
endif()

message(STATUS "nRF5 SDK found at: ${NRF5_PATH}")

set(NRF_MDK_DIR      "${NRF5_PATH}/modules/nrfx/mdk")
set(NRF_CMSIS_INC    "${NRF5_PATH}/components/toolchain/cmsis/include")
set(LINKER_SCRIPT    "${NRF_MDK_DIR}/nrf52832_xxaa.ld")
set(STARTUP_FILE     "${NRF_MDK_DIR}/gcc_startup_nrf52.S")
set(SYSTEM_FILE      "${NRF_MDK_DIR}/system_nrf52.c")
set(TARGET_NAME      "ORBIT_${ALGO_SELECTED}_nrf52")

foreach(required_file
        "${LINKER_SCRIPT}"
        "${STARTUP_FILE}"
        "${SYSTEM_FILE}")
    if(NOT EXISTS "${required_file}")
        message(FATAL_ERROR "Required nRF52 SDK file not found: ${required_file}")
    endif()
endforeach()

file(GLOB ALGO_SOURCES CONFIGURE_DEPENDS "${ALGO_DIR}/*.c")

add_executable(${TARGET_NAME}
    bench/main.c
    bench/util.c
    ${ALGO_SOURCES}
    ${STARTUP_FILE}
    ${SYSTEM_FILE}
)

target_include_directories(${TARGET_NAME} PRIVATE
    include
    bench
    "${ALGO_DIR}"
    "platforms/nrf52"
    "${NRF_MDK_DIR}"
    "${NRF_CMSIS_INC}"
)

target_compile_definitions(${TARGET_NAME} PRIVATE
    NRF52832_XXAA
    ALGO_NAME=${ALGO_SELECTED}
    BOARD_NAME="nrf52"
    VERSION_STR="0.1.0"
    COMPILER_ID="${CMAKE_C_COMPILER_ID}"
    COMPILER_VERSION="${CMAKE_C_COMPILER_VERSION}"
    COMPILER_FLAGS="-O2"
    PLATFORM_BOOT_DELAY_MS=0
    TARGET_ARCH="armv7e-m"
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

target_compile_options(${TARGET_NAME} PRIVATE
    -O2
    -Wall
    -Wextra
    -mcpu=cortex-m4
    -mthumb
    -mfloat-abi=soft
    -fdata-sections
    -ffunction-sections
)

target_link_options(${TARGET_NAME} PRIVATE
    -mcpu=cortex-m4
    -mthumb
    -mfloat-abi=soft
    -specs=nano.specs
    -specs=nosys.specs
    -L${NRF_MDK_DIR}
    -Wl,--gc-sections
    -Wl,-Map=${TARGET_NAME}.map
    -Wl,-T,${LINKER_SCRIPT}
)

target_link_libraries(${TARGET_NAME} c m)

add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
    COMMAND arm-none-eabi-objcopy -O binary
        $<TARGET_FILE:${TARGET_NAME}>
        ${TARGET_NAME}.bin
    COMMAND arm-none-eabi-objcopy -O ihex
        $<TARGET_FILE:${TARGET_NAME}>
        ${TARGET_NAME}.hex
    COMMENT "Generating nRF52 binary and hex images"
)
