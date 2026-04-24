#ifndef PLATFORM_H
#define PLATFORM_H

#include <stdint.h>
#include "nrf.h"

#define PLATFORM_FREQ_HZ 64000000UL

/*
 * Defaults target the nRF52832 DK (PCA10040) virtual COM port pins.
 * Adjust these if you use a different nRF52 board wiring layout.
 */
#define UART_TX_PIN 6u
#define UART_RX_PIN 8u
#define TRIGGER_PIN 13u
#define FRAME_TRIGGER_PIN 14u
#define TIMER_TICK_HZ 16000000UL

static inline void _gpio_cfg_output(uint32_t pin) {
    NRF_P0->PIN_CNF[pin] =
        (GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos) |
        (GPIO_PIN_CNF_INPUT_Disconnect << GPIO_PIN_CNF_INPUT_Pos) |
        (GPIO_PIN_CNF_PULL_Disabled << GPIO_PIN_CNF_PULL_Pos) |
        (GPIO_PIN_CNF_DRIVE_S0S1 << GPIO_PIN_CNF_DRIVE_Pos) |
        (GPIO_PIN_CNF_SENSE_Disabled << GPIO_PIN_CNF_SENSE_Pos);
}

static inline void _gpio_cfg_input(uint32_t pin) {
    NRF_P0->PIN_CNF[pin] =
        (GPIO_PIN_CNF_DIR_Input << GPIO_PIN_CNF_DIR_Pos) |
        (GPIO_PIN_CNF_INPUT_Connect << GPIO_PIN_CNF_INPUT_Pos) |
        (GPIO_PIN_CNF_PULL_Disabled << GPIO_PIN_CNF_PULL_Pos) |
        (GPIO_PIN_CNF_DRIVE_S0S1 << GPIO_PIN_CNF_DRIVE_Pos) |
        (GPIO_PIN_CNF_SENSE_Disabled << GPIO_PIN_CNF_SENSE_Pos);
}

static inline void _timer_init(void) {
    NRF_TIMER1->TASKS_STOP = 1;
    NRF_TIMER1->TASKS_CLEAR = 1;
    NRF_TIMER1->MODE = TIMER_MODE_MODE_Timer;
    NRF_TIMER1->BITMODE = TIMER_BITMODE_BITMODE_32Bit;
    NRF_TIMER1->PRESCALER = 0;
    NRF_TIMER1->TASKS_START = 1;
}

static inline void _hfclk_init(void) {
    NRF_CLOCK->EVENTS_HFCLKSTARTED = 0;
    NRF_CLOCK->TASKS_HFCLKSTART = 1;
    while (NRF_CLOCK->EVENTS_HFCLKSTARTED == 0) {
    }
}

static inline void _uart_init(void) {
    NRF_UART0->ENABLE = 0;
    NRF_UART0->PSELTXD = UART_TX_PIN;
    NRF_UART0->PSELRXD = UART_RX_PIN;
    NRF_UART0->PSELRTS = 0xFFFFFFFFUL;
    NRF_UART0->PSELCTS = 0xFFFFFFFFUL;
    NRF_UART0->CONFIG = 0;
    NRF_UART0->BAUDRATE = UART_BAUDRATE_BAUDRATE_Baud115200;
    NRF_UART0->ENABLE = UART_ENABLE_ENABLE_Enabled << UART_ENABLE_ENABLE_Pos;
    NRF_UART0->TASKS_STARTTX = 1;
}

static inline void platform_puts(const char *str) {
    if (!str) {
        return;
    }

    while (*str) {
        NRF_UART0->EVENTS_TXDRDY = 0;
        NRF_UART0->TXD = (uint8_t)(*str++);
        while (NRF_UART0->EVENTS_TXDRDY == 0) {
        }
    }
}

static inline void platform_init(void) {
    _hfclk_init();
    _gpio_cfg_output(TRIGGER_PIN);
    NRF_P0->OUTCLR = (1UL << TRIGGER_PIN);
    _gpio_cfg_output(FRAME_TRIGGER_PIN);
    NRF_P0->OUTCLR = (1UL << FRAME_TRIGGER_PIN);
    _gpio_cfg_output(UART_TX_PIN);
    _gpio_cfg_input(UART_RX_PIN);
    _uart_init();
    _timer_init();
}

static inline uint64_t platform_cycle_count(void) {
    /*
     * TIMER1 runs from the 16 MHz peripheral clock. Scale captured ticks by 4
     * so reported counts track the 64 MHz CPU clock used by the benchmark.
     */
    NRF_TIMER1->TASKS_CAPTURE[0] = 1;
    return (uint64_t)NRF_TIMER1->CC[0] * (PLATFORM_FREQ_HZ / TIMER_TICK_HZ);
}

static inline void platform_trigger_high(void) {
    NRF_P0->OUTSET = (1UL << TRIGGER_PIN);
}

static inline void platform_trigger_low(void) {
    NRF_P0->OUTCLR = (1UL << TRIGGER_PIN);
}

static inline void platform_frame_trigger_high(void) {
    NRF_P0->OUTSET = (1UL << FRAME_TRIGGER_PIN);
}

static inline void platform_frame_trigger_low(void) {
    NRF_P0->OUTCLR = (1UL << FRAME_TRIGGER_PIN);
}

static inline uint32_t platform_freq_hz(void) {
    return PLATFORM_FREQ_HZ;
}

static inline int platform_stdio_ready(void) {
    return 1;
}

static inline void platform_delay_ms(uint32_t ms) {
    uint64_t start = platform_cycle_count();
    uint64_t wait_ticks = ((uint64_t)PLATFORM_FREQ_HZ * (uint64_t)ms) / 1000ULL;

    while ((platform_cycle_count() - start) < wait_ticks) {
    }
}

#endif /* PLATFORM_H */
