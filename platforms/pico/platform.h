#ifndef PLATFORM_H
#define PLATFORM_H

#include <stdint.h>
#include "pico/stdlib.h"
#include "hardware/gpio.h"
#include "hardware/structs/systick.h"

#define PLATFORM_FREQ_HZ 125000000UL
#define TRIGGER_PIN 15
#define FRAME_TRIGGER_PIN 14

static inline void _systick_init(void) {
    systick_hw->csr = 0;
    systick_hw->rvr = 0x00FFFFFF;
    systick_hw->cvr = 0;
    systick_hw->csr = 0x5;
}

static inline void platform_puts(const char *str) {
    while (*str) {
        putchar_raw(*str++);
    }
}

static inline uint64_t platform_cycle_count(void) {
    uint32_t cvr = systick_hw->cvr & 0x00FFFFFF;
    uint64_t us = time_us_64();

    uint32_t ticks_per_us = PLATFORM_FREQ_HZ / 1000000UL;
    uint32_t sub_us = (ticks_per_us -1u) - (cvr % ticks_per_us);

    return (us * (uint64_t)ticks_per_us) + (uint64_t)sub_us;
}

static inline void platform_init(void) {
    stdio_init_all();
    _systick_init();
    gpio_init(TRIGGER_PIN);
    gpio_set_dir(TRIGGER_PIN, GPIO_OUT);
    gpio_put(TRIGGER_PIN, 0);

    gpio_init(FRAME_TRIGGER_PIN);
    gpio_set_dir(FRAME_TRIGGER_PIN, GPIO_OUT);
    gpio_put(FRAME_TRIGGER_PIN, 0);
}

static inline void platform_trigger_high(void) {
    gpio_put(TRIGGER_PIN, 1);
}

static inline void platform_trigger_low(void) {
    gpio_put(TRIGGER_PIN, 0);
}

static inline void platform_frame_trigger_high(void) {
    gpio_put(FRAME_TRIGGER_PIN, 1);
}

static inline void platform_frame_trigger_low(void) {
    gpio_put(FRAME_TRIGGER_PIN, 0);
}

static inline uint32_t platform_freq_hz(void) {
    return PLATFORM_FREQ_HZ;
}

static inline int platform_stdio_ready(void) { return stdio_usb_connected(); }
static inline void platform_delay_ms(uint32_t ms) { sleep_ms(ms); }
#endif // PLATFORM_H
