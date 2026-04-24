if(NOT DEFINED ALGO_SELECTED OR ALGO_SELECTED STREQUAL "")
    set(ALGO_SELECTED "ascon_aead128")
endif()

get_filename_component(ORBIT_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
set(ALGO_DIR "${ORBIT_ROOT}/algorithms/${ALGO_SELECTED}")

if(NOT EXISTS "${ALGO_DIR}")
    message(FATAL_ERROR "Algorithm folder not found: ${ALGO_DIR}")
endif()

file(GLOB ALGO_SOURCES "${ALGO_DIR}/*.c")

idf_component_register(
    SRCS
        "orbit_app_main.c"
        "${ORBIT_ROOT}/bench/main.c"
        "${ORBIT_ROOT}/bench/util.c"
        ${ALGO_SOURCES}
    INCLUDE_DIRS
        "${ORBIT_ROOT}/include"
        "${ORBIT_ROOT}/bench"
        "${ALGO_DIR}"
        "${ORBIT_ROOT}/platforms/esp32c61"
    REQUIRES
        driver
        freertos
        esp_system
)

target_compile_definitions(${COMPONENT_LIB} PRIVATE
    main=orbit_main
    ALGO_NAME=${ALGO_SELECTED}
    BOARD_NAME="esp32c61"
    VERSION_STR="0.1.0"
    COMPILER_ID="${CMAKE_C_COMPILER_ID}"
    COMPILER_VERSION="${CMAKE_C_COMPILER_VERSION}"
    COMPILER_FLAGS="-O2"
    TARGET_ARCH="riscv32"
    PLATFORM_BOOT_DELAY_MS=5000
    PLATFORM_EXIT_AFTER_BENCHMARK=1
)

if(ALGO_SELECTED STREQUAL "aes_128_gcm")
    target_compile_definitions(${COMPONENT_LIB} PRIVATE SLOW_ALGO=1)
endif()

if(ALGO_SELECTED STREQUAL "ml_kem_512")
    target_compile_definitions(${COMPONENT_LIB} PRIVATE IS_KEM=1 SLOW_ALGO=1)
endif()

if(DEFINED ORBIT_ENERGY_RUNS)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE ORBIT_ENERGY_RUNS=${ORBIT_ENERGY_RUNS})
endif()

if(ORBIT_NO_STDIO_WAIT)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE ORBIT_NO_STDIO_WAIT=1)
endif()

target_compile_options(${COMPONENT_LIB} PRIVATE -O2 -Wall -Wextra)
