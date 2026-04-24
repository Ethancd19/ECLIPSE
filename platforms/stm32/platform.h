#ifndef PLATFORM_H
#define PLATFORM_H

#include <stdint.h>
#include <string.h>
#include "stm32f4xx_hal.h"

#define TRIGGER_PIN_PORT    GPIOA
#define TRIGGER_PIN         GPIO_PIN_8
#define FRAME_TRIGGER_PIN_PORT GPIOA
#define FRAME_TRIGGER_PIN      GPIO_PIN_9

extern UART_HandleTypeDef huart2;

static inline void platform_puts(const char *str) {
    while (*str) {
        /* Poll TXE directly - no HAL timeout dependency */
        while (!(USART2->SR & USART_SR_TXE)) {}
        USART2->DR = (uint8_t)(*str++);
    }
    /* Wait for transmission complete */
    while (!(USART2->SR & USART_SR_TC)) {}
}

static inline void _dwt_init(void) {
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL  |= DWT_CTRL_CYCCNTENA_Msk;
}

static inline void SystemClock_Config(void) {
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

    __HAL_RCC_PWR_CLK_ENABLE();
    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    RCC_OscInitStruct.HSIState = RCC_HSI_ON;
    RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
    RCC_OscInitStruct.PLL.PLLM = 16;
    RCC_OscInitStruct.PLL.PLLN = 360;
    RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
    RCC_OscInitStruct.PLL.PLLQ = 7;
    RCC_OscInitStruct.PLL.PLLR = 2;
    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {
        while (1) {}
    }

    if (HAL_PWREx_EnableOverDrive() != HAL_OK) {
        while (1) {}
    }

    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK
                                | RCC_CLOCKTYPE_SYSCLK
                                | RCC_CLOCKTYPE_PCLK1
                                | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_5) != HAL_OK) {
        while (1) {}
    }
}

static inline void platform_init(void) {
    /* Enable FPU - required for hard float ABI (-mfloat-abi=hard) */
    SCB->CPACR |= ((3UL << 10*2) | (3UL << 11*2));
    __DSB();
    __ISB();

    /* Route configurable faults to their own handlers instead of escalating. */
    SCB->SHCSR |= SCB_SHCSR_USGFAULTENA_Msk
               |  SCB_SHCSR_BUSFAULTENA_Msk
               |  SCB_SHCSR_MEMFAULTENA_Msk;

    HAL_Init();
    SystemClock_Config();

    __HAL_RCC_USART2_CLK_ENABLE();
    __HAL_RCC_GPIOA_CLK_ENABLE();

    GPIO_InitTypeDef gpio = {0};
    gpio.Pin       = GPIO_PIN_2 | GPIO_PIN_3;
    gpio.Mode      = GPIO_MODE_AF_PP;
    gpio.Pull      = GPIO_NOPULL;
    gpio.Speed     = GPIO_SPEED_FREQ_HIGH;
    gpio.Alternate = GPIO_AF7_USART2;
    HAL_GPIO_Init(GPIOA, &gpio);

    huart2.Instance          = USART2;
    huart2.Init.BaudRate     = 115200;
    huart2.Init.WordLength   = UART_WORDLENGTH_8B;
    huart2.Init.StopBits     = UART_STOPBITS_1;
    huart2.Init.Parity       = UART_PARITY_NONE;
    huart2.Init.Mode         = UART_MODE_TX_RX;
    huart2.Init.HwFlowCtl    = UART_HWCONTROL_NONE;
    huart2.Init.OverSampling = UART_OVERSAMPLING_16;
    HAL_UART_Init(&huart2);

    gpio.Pin       = TRIGGER_PIN | FRAME_TRIGGER_PIN;
    gpio.Mode      = GPIO_MODE_OUTPUT_PP;
    gpio.Pull      = GPIO_NOPULL;
    gpio.Speed     = GPIO_SPEED_FREQ_HIGH;
    gpio.Alternate = 0;
    HAL_GPIO_Init(TRIGGER_PIN_PORT, &gpio);
    HAL_GPIO_WritePin(TRIGGER_PIN_PORT, TRIGGER_PIN, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(FRAME_TRIGGER_PIN_PORT, FRAME_TRIGGER_PIN, GPIO_PIN_RESET);

    _dwt_init();
}

static inline uint64_t platform_cycle_count(void) {
    return (uint64_t)(DWT->CYCCNT);
}

static inline void platform_trigger_high(void) {
    HAL_GPIO_WritePin(TRIGGER_PIN_PORT, TRIGGER_PIN, GPIO_PIN_SET);
}

static inline void platform_trigger_low(void) {
    HAL_GPIO_WritePin(TRIGGER_PIN_PORT, TRIGGER_PIN, GPIO_PIN_RESET);
}

static inline void platform_frame_trigger_high(void) {
    HAL_GPIO_WritePin(FRAME_TRIGGER_PIN_PORT, FRAME_TRIGGER_PIN, GPIO_PIN_SET);
}

static inline void platform_frame_trigger_low(void) {
    HAL_GPIO_WritePin(FRAME_TRIGGER_PIN_PORT, FRAME_TRIGGER_PIN, GPIO_PIN_RESET);
}

static inline uint32_t platform_freq_hz(void) {
    return HAL_RCC_GetHCLKFreq();
}

static inline int platform_stdio_ready(void) { return 1; }
static inline void platform_delay_ms(uint32_t ms) { HAL_Delay(ms); }

#endif /* PLATFORM_H */
