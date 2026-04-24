#ifndef PLATFORM_H
#define PLATFORM_H

#include <stdint.h>
#include <stdio.h>
#include <time.h>

#if defined(__aarch64__)
static inline uint64_t _rpi5_cntfrq_el0(void) {
    uint64_t freq = 0;
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(freq));
    return freq;
}

static inline uint64_t _rpi5_cntvct_el0(void) {
    uint64_t count = 0;
    __asm__ volatile("isb" ::: "memory");
    __asm__ volatile("mrs %0, cntvct_el0" : "=r"(count));
    return count;
}
#endif

static inline void platform_puts(const char *str) {
    if (!str) {
        return;
    }
    fputs(str, stdout);
    fflush(stdout);
}

static inline uint64_t platform_cycle_count(void) {
#if defined(__aarch64__)
    return _rpi5_cntvct_el0();
#else
    struct timespec ts = {0};
    (void)timespec_get(&ts, TIME_UTC);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
#endif
}

static inline void platform_init(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
}

static inline void platform_trigger_high(void) {
    /* Optional GPIO trigger support can be added later via libgpiod. */
}

static inline void platform_trigger_low(void) {
    /* Optional GPIO trigger support can be added later via libgpiod. */
}

static inline void platform_frame_trigger_high(void) {
    /* Optional GPIO trigger support can be added later via libgpiod. */
}

static inline void platform_frame_trigger_low(void) {
    /* Optional GPIO trigger support can be added later via libgpiod. */
}

static inline uint32_t platform_freq_hz(void) {
#if defined(__aarch64__)
    return (uint32_t)_rpi5_cntfrq_el0();
#else
    return 1000000000UL;
#endif
}

static inline int platform_stdio_ready(void) {
    return 1;
}

static inline void platform_delay_ms(uint32_t ms) {
    uint64_t start = platform_cycle_count();
    uint64_t wait_ticks = ((uint64_t)platform_freq_hz() * (uint64_t)ms) / 1000ULL;

    while ((platform_cycle_count() - start) < wait_ticks) {
    }
}

#endif /* PLATFORM_H */
