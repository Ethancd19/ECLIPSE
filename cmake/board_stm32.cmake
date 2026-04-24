# ===============================================================
# board_stm32.cmake - STM32 Nucleo F446RE (STM32F446RE, Cortex-M4F)
# Included by top-level CMakeLists.txt when BOARD=stm32 is selected
#
# Requires STM32CubeF4 at STM32CUBE_F4_PATH (default: ~/stm32cubeF4)
# Set via: cmake -DSTM32CUBE_F4_PATH=/path/to/STM32CubeF4 ...
#       or: export STM32CUBE_F4_PATH=~/stm32cubeF4
# ===============================================================

# Check toolchain
if(NOT CMAKE_C_COMPILER)
    set(CMAKE_C_COMPILER "arm-none-eabi-gcc")
endif()

# set STM32CubeF4 path
if(DEFINED STM32CUBE_F4_PATH)
    set(CUBE_PATH "${STM32CUBE_F4_PATH}")
elseif(DEFINED ENV{STM32CUBE_F4_PATH})
    set(CUBE_PATH "$ENV{STM32CUBE_F4_PATH}")
else()
    set(CUBE_PATH "$ENV{HOME}/stm32cubeF4")
endif()

if(NOT EXISTS "${CUBE_PATH}/Drivers/CMSIS/Device/ST/STM32F4xx/Include/stm32f4xx.h")
    message(FATAL_ERROR
        "STM32CubeF4 not found at: ${CUBE_PATH}\n"
        "Clone it with: git clone https://github.com/STMicroelectronics/STM32CubeF4.git ~/stm32cubeF4 --depth 1\n"
        "Then: cd ~/stm32cubeF4 && git submodule update --init --recursive\n"
        "Or set STM32CUBE_F4_PATH to the correct location."
    )
endif()

message(STATUS "STM32CubeF4 found at: ${CUBE_PATH}")

# Paths
set(CMSIS_CORE_INC    "${CUBE_PATH}/Drivers/CMSIS/Include")
set(CMSIS_DEVICE_INC  "${CUBE_PATH}/Drivers/CMSIS/Device/ST/STM32F4xx/Include")
set(CMSIS_DEVICE_SRC  "${CUBE_PATH}/Drivers/CMSIS/Device/ST/STM32F4xx/Source/Templates/gcc")
set(HAL_INC           "${CUBE_PATH}/Drivers/STM32F4xx_HAL_Driver/Inc")
set(HAL_SRC           "${CUBE_PATH}/Drivers/STM32F4xx_HAL_Driver/Src")
set(TARGET_NAME "ORBIT_${ALGO_SELECTED}_stm32")

set(HAL_SOURCES
    "${HAL_SRC}/stm32f4xx_hal.c"
    "${HAL_SRC}/stm32f4xx_hal_rcc.c"
    "${HAL_SRC}/stm32f4xx_hal_rcc_ex.c"
    "${HAL_SRC}/stm32f4xx_hal_gpio.c"
    "${HAL_SRC}/stm32f4xx_hal_uart.c"
    "${HAL_SRC}/stm32f4xx_hal_cortex.c"
    "${HAL_SRC}/stm32f4xx_hal_pwr.c"
    "${HAL_SRC}/stm32f4xx_hal_pwr_ex.c"
    "${HAL_SRC}/stm32f4xx_hal_dma.c"
    "${HAL_SRC}/stm32f4xx_hal_flash.c"
    "${HAL_SRC}/stm32f4xx_hal_flash_ex.c"
)

set(STARTUP_FILE "${CMSIS_DEVICE_SRC}/startup_stm32f446xx.s")
set(SYSTEM_FILE  "${CUBE_PATH}/Drivers/CMSIS/Device/ST/STM32F4xx/Source/Templates/system_stm32f4xx.c")

# Linker script
set(LINKER_SCRIPT "${CMAKE_SOURCE_DIR}/platforms/stm32/STM32F446RETx_FLASH.ld")
if(NOT EXISTS "${LINKER_SCRIPT}")
    message(FATAL_ERROR
        "Linker script not found: ${LINKER_SCRIPT}\n"
        "Copy it from: ${CUBE_PATH}/Projects/NUCLEO-F446RE/Templates/STM32CubeIDE/STM32F446RETx_FLASH.ld\n"
        "Or from the platforms/stm32/ folder in this repository."
    )
endif()

if(NOT EXISTS "${CMAKE_SOURCE_DIR}/platforms/stm32/stm32f4xx_hal_conf.h")
    message(FATAL_ERROR
        "HAL config header not found: platforms/stm32/stm32f4xx_hal_conf.h\n"
        "Copy the template from: ${HAL_INC}/stm32f4xx_hal_conf_template.h\n"
        "  cp ${HAL_INC}/stm32f4xx_hal_conf_template.h platforms/stm32/stm32f4xx_hal_conf.h"
    )
endif()

# Algorithm sources
file(GLOB ALGO_SOURCES CONFIGURE_DEPENDS "${ALGO_DIR}/*.c")

# Target setup
set(TARGET_NAME "ORBIT_${ALGO_SELECTED}_stm32")

add_executable(${TARGET_NAME}
    bench/main.c
    bench/util.c
    platforms/stm32/syscalls.c
    platforms/stm32/sysmem.c
    platforms/stm32/stm32_uart.c
    platforms/stm32/stm32_it.c
    ${ALGO_SOURCES}
    ${HAL_SOURCES}
    ${STARTUP_FILE}
    ${SYSTEM_FILE}
)

target_include_directories(${TARGET_NAME} PRIVATE
    include
    bench
    "${ALGO_DIR}"
    "platforms/stm32"
    "${CMSIS_CORE_INC}"
    "${CMSIS_DEVICE_INC}"
    "${HAL_INC}"
    "${HAL_INC}/Legacy"
)

target_compile_definitions(${TARGET_NAME} PRIVATE
    STM32F446xx
    USE_HAL_DRIVER
    ALGO_NAME=${ALGO_SELECTED}
    BOARD_NAME="stm32"
    VERSION_STR="0.1.0"
    COMPILER_ID="${CMAKE_C_COMPILER_ID}"
    COMPILER_VERSION="${CMAKE_C_COMPILER_VERSION}"
    COMPILER_FLAGS="-O2"
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
    -mfpu=fpv4-sp-d16 
    -mfloat-abi=hard 
    -fdata-sections 
    -ffunction-sections)

target_link_options(${TARGET_NAME} PRIVATE
    -mcpu=cortex-m4
    -mthumb
    -mfpu=fpv4-sp-d16
    -mfloat-abi=hard
    -specs=nano.specs
    -specs=nosys.specs
    -Wl,--gc-sections
    -Wl,-Map=${TARGET_NAME}.map
    -Wl,-T,${LINKER_SCRIPT}
)

target_link_libraries(${TARGET_NAME} c m)

add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
    COMMAND arm-none-eabi-objcopy -O binary 
        $<TARGET_FILE:${TARGET_NAME}>
        ${TARGET_NAME}.bin
    COMMENT "Generating binary file: ${TARGET_NAME}.bin"
)
