#ifndef PLATFORM_H
#define PLATFORM_H

#include <stdint.h>
#include <stdio.h>

#include "driver/gpio.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define PLATFORM_FREQ_HZ 160000000UL

#ifndef TRIGGER_PIN
#define TRIGGER_PIN GPIO_NUM_2
#endif

#ifndef FRAME_TRIGGER_PIN
#define FRAME_TRIGGER_PIN GPIO_NUM_3
#endif

static inline uint64_t platform_cycle_count(void) {
    uint32_t hi;
    uint32_t lo;
    uint32_t hi2;

    do {
        __asm__ volatile("rdcycleh %0" : "=r"(hi));
        __asm__ volatile("rdcycle %0" : "=r"(lo));
        __asm__ volatile("rdcycleh %0" : "=r"(hi2));
    } while (hi != hi2);

    return ((uint64_t)hi << 32) | (uint64_t)lo;
}

static inline void platform_puts(const char *str) {
    if (!str) {
        return;
    }

    fputs(str, stdout);
    fflush(stdout);
}

static inline void platform_init(void) {
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << TRIGGER_PIN) | (1ULL << FRAME_TRIGGER_PIN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };

    gpio_config(&io_conf);
    gpio_set_level(TRIGGER_PIN, 0);
    gpio_set_level(FRAME_TRIGGER_PIN, 0);
}

static inline void platform_trigger_high(void) {
    gpio_set_level(TRIGGER_PIN, 1);
}

static inline void platform_trigger_low(void) {
    gpio_set_level(TRIGGER_PIN, 0);
}

static inline void platform_frame_trigger_high(void) {
    gpio_set_level(FRAME_TRIGGER_PIN, 1);
}

static inline void platform_frame_trigger_low(void) {
    gpio_set_level(FRAME_TRIGGER_PIN, 0);
}

static inline uint32_t platform_freq_hz(void) {
    return PLATFORM_FREQ_HZ;
}

static inline int platform_stdio_ready(void) {
    return 1;
}

static inline void platform_delay_ms(uint32_t ms) {
    if (ms == 0) {
        return;
    }

    vTaskDelay(pdMS_TO_TICKS(ms));
}

#endif /* PLATFORM_H */
