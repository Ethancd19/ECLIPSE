#include <stdio.h>
#include <string.h>
#include <stdint.h>

#include "util.h"
#include "platform.h"

#define XSTR(x) STR(x)
#define STR(x) #x

#ifndef ALGO_NAME
#define ALGO_NAME "unknown-algo"
#endif
#ifndef BOARD_NAME
#define BOARD_NAME "pico"
#endif
#ifndef VERSION_STR
#define VERSION_STR "unknown-version"
#endif
#ifndef COMPILER_VERSION
#define COMPILER_VERSION "unknown-version"
#endif
#ifndef COMPILER_ID
#define COMPILER_ID "unknown-compiler"
#endif
#ifndef COMPILER_FLAGS
#define COMPILER_FLAGS "unknown-cflags"
#endif
#ifndef TARGET_ARCH
#define TARGET_ARCH "unknown-arch"
#endif
#ifndef PLATFORM_BOOT_DELAY_MS
#define PLATFORM_BOOT_DELAY_MS 2000
#endif
#ifndef ORBIT_ENERGY_RUNS
#define ORBIT_ENERGY_RUNS 1
#endif
#ifndef ORBIT_INTER_RUN_DELAY_MS
#define ORBIT_INTER_RUN_DELAY_MS 500
#endif

/* AEAD Mode */
#ifndef IS_KEM

#ifndef ORBIT_MAX_MSG_LEN
#define ORBIT_MAX_MSG_LEN    16384
#endif

#if ORBIT_MAX_MSG_LEN >= 16384
#define NUM_MSG_SIZES        6
static const size_t MSG_SIZES[NUM_MSG_SIZES] = {16, 64, 256, 1024, 4096, 16384};
#ifdef SLOW_ALGO
static const uint32_t BENCH_ITERS[NUM_MSG_SIZES]  = {50, 20, 10, 5, 3, 2};
static const uint32_t WARMUP_ITERS[NUM_MSG_SIZES] = {10, 10,  5, 3, 2, 1};
#else
static const uint32_t BENCH_ITERS[NUM_MSG_SIZES]  = {1000, 1000, 1000, 500, 200, 100};
static const uint32_t WARMUP_ITERS[NUM_MSG_SIZES] = {1000, 1000, 1000, 500, 200, 100};
#endif
#elif ORBIT_MAX_MSG_LEN >= 4096
#define NUM_MSG_SIZES        5
static const size_t MSG_SIZES[NUM_MSG_SIZES] = {16, 64, 256, 1024, 4096};
#ifdef SLOW_ALGO
static const uint32_t BENCH_ITERS[NUM_MSG_SIZES]  = {50, 20, 10, 5, 3};
static const uint32_t WARMUP_ITERS[NUM_MSG_SIZES] = {10, 10,  5, 3, 2};
#else
static const uint32_t BENCH_ITERS[NUM_MSG_SIZES]  = {1000, 1000, 1000, 500, 200};
static const uint32_t WARMUP_ITERS[NUM_MSG_SIZES] = {1000, 1000, 1000, 500, 200};
#endif
#elif ORBIT_MAX_MSG_LEN >= 1024
#define NUM_MSG_SIZES        4
static const size_t MSG_SIZES[NUM_MSG_SIZES] = {16, 64, 256, 1024};
#ifdef SLOW_ALGO
static const uint32_t BENCH_ITERS[NUM_MSG_SIZES]  = {50, 20, 10, 5};
static const uint32_t WARMUP_ITERS[NUM_MSG_SIZES] = {10, 10,  5, 3};
#else
static const uint32_t BENCH_ITERS[NUM_MSG_SIZES]  = {1000, 1000, 1000, 500};
static const uint32_t WARMUP_ITERS[NUM_MSG_SIZES] = {1000, 1000, 1000, 500};
#endif
#else
#error "ORBIT_MAX_MSG_LEN must be at least 1024 bytes"
#endif

#define MAX_MSG_LEN          ORBIT_MAX_MSG_LEN
#define MAX_CT_LEN           (MAX_MSG_LEN + 64)
#define BENCH_AD_LEN         32

#include "crypto_aead.h"
#include "api.h"

static uint8_t g_m[MAX_MSG_LEN];
static uint8_t g_ad[BENCH_AD_LEN];
static uint8_t g_c[MAX_CT_LEN];
static uint8_t g_m_dec[MAX_MSG_LEN];

static int correctness_and_tamper(size_t mlen, size_t adlen) {
    uint8_t *m = g_m;
    uint8_t *ad = g_ad;
    uint8_t *c = g_c;
    uint8_t *m_dec = g_m_dec;

    uint8_t key[CRYPTO_KEYBYTES];
    uint8_t nonce[CRYPTO_NPUBBYTES];

    fill_deterministic(key, sizeof(key), 0x12345678);
    fill_deterministic(nonce, sizeof(nonce), 0x87654321);
    fill_deterministic(m, mlen, 0xA5A5A5A5);
    fill_deterministic(ad, adlen, 0x5A5A5A5A);

    unsigned long long clen = 0;
    int enc_rc = crypto_aead_encrypt(c, &clen, m, (unsigned long long)mlen, ad, (unsigned long long)adlen, NULL, nonce, key);
    if (enc_rc != 0) {
        return 0;
    }

    unsigned long long mlen_dec = 0;
    int dec_rc = crypto_aead_decrypt(m_dec, &mlen_dec, NULL, c, clen, ad, (unsigned long long)adlen, nonce, key);

    int ok_roundtrip = (dec_rc == 0) && (mlen_dec == (unsigned long long)mlen) && bytes_equal(m, m_dec, mlen);

    // Tamper with ciphertext
    if (clen > 0) {
        c[0] ^= 0x01; // Flip a bit
    }
    unsigned long long mlen_tamper = 0;
    int dec_tamper_rc = crypto_aead_decrypt(m_dec, &mlen_tamper, NULL, c, clen, ad, (unsigned long long)adlen, nonce, key);

    int ok_tamper = (dec_tamper_rc != 0);

    return ok_roundtrip && ok_tamper;
}

static void bench_one(size_t mlen, size_t adlen, uint32_t iterations, csv_row_t *row) {
    uint32_t warmup_iters = 0;
    uint8_t *m = g_m;
    uint8_t *ad = g_ad;
    uint8_t *c = g_c;
    uint8_t *m_dec = g_m_dec;

    uint8_t key[CRYPTO_KEYBYTES];
    uint8_t nonce[CRYPTO_NPUBBYTES];

    unsigned long long clen = 0;
    unsigned long long mlen_dec = 0;

    fill_deterministic(key, sizeof(key), 0x12345678);
    fill_deterministic(nonce, sizeof(nonce), 0x87654321);
    fill_deterministic(ad, adlen, 0x5A5A5A5A);
    fill_deterministic(m, mlen, 0xA5A5A5A5);

    for (size_t s = 0; s < NUM_MSG_SIZES; s++) {
        if (MSG_SIZES[s] == mlen) {
            warmup_iters = WARMUP_ITERS[s];
            break;
        }
    }

    for (uint32_t i = 0; i < warmup_iters; i++) {
        fill_deterministic(m, mlen, (uint32_t)(0xA5A5A5A5 + i));
        (void)crypto_aead_encrypt(c, &clen, m, (unsigned long long)mlen, ad, (unsigned long long)adlen, NULL, nonce, key);
        (void)crypto_aead_decrypt(m_dec, &mlen_dec, NULL, c, clen, ad, (unsigned long long)adlen, nonce, key);
    }

    // Benchmark encryption
    platform_trigger_high();
    uint64_t start_enc_cycles = platform_cycle_count();

    for (uint32_t i = 0; i < iterations; i++) {
        fill_deterministic(m, mlen, (uint32_t)(0xA5A5A5A5 + i));
        int rc = crypto_aead_encrypt(c, &clen, m, (unsigned long long)mlen, ad, (unsigned long long)adlen, NULL, nonce, key);
        if (rc != 0) {
            platform_trigger_low();
            row->ok = 0;
            row->notes = "Encryption failed during benchmarking";
            return;
        }
    }

    uint64_t end_enc_cycles = platform_cycle_count();
    platform_trigger_low();

    for (uint32_t i = 0; i < iterations; i++) {
        (void)crypto_aead_decrypt(m_dec, &mlen_dec, NULL, c, clen, ad, (unsigned long long)adlen, nonce, key);
    }

    // Benchmark decryption
    platform_trigger_high();
    uint64_t start_dec_cycles = platform_cycle_count();

    for (uint64_t i = 0; i < iterations; i++) {
        int rc = crypto_aead_decrypt(m_dec, &mlen_dec, NULL, c, clen, ad, (unsigned long long)adlen, nonce, key);
        if (rc != 0) {
            platform_trigger_low();
            row->ok = 0;
            row->notes = "Decryption failed during benchmarking";
            return;
        }
    }
    uint64_t end_dec_cycles = platform_cycle_count();
    platform_trigger_low();

    uint64_t enc_cycles_total = end_enc_cycles - start_enc_cycles;
    uint64_t dec_cycles_total = end_dec_cycles - start_dec_cycles;

    // Correctness check
    fill_deterministic(m, mlen, (uint32_t)(0xA5A5A5A5 + iterations - 1));
    int ok_correctness = (mlen_dec == (unsigned long long)mlen) && bytes_equal(m, m_dec, mlen);


    row->msg_len = mlen;
    row->ad_len = adlen;
    row->key_len = CRYPTO_KEYBYTES;
    row->nonce_len = CRYPTO_NPUBBYTES;
    row->tag_len = CRYPTO_ABYTES;
    row->iterations = iterations;
    row->freq_hz = platform_freq_hz();

    row->enc_cycles_total = enc_cycles_total;
    row->dec_cycles_total = dec_cycles_total;
    row->enc_cycles_per_byte = (mlen > 0) ? (double)enc_cycles_total / (double)(mlen * iterations) : 0.0;
    row->dec_cycles_per_byte = (mlen > 0) ? (double)dec_cycles_total / (double)(mlen * iterations) : 0.0;

    row->enc_time_us_total  = (double)enc_cycles_total / ((double)platform_freq_hz() / 1e6);
    row->dec_time_us_total  = (double)dec_cycles_total / ((double)platform_freq_hz() / 1e6);
    row->enc_time_us_per_op = row->enc_time_us_total / iterations;
    row->dec_time_us_per_op = row->dec_time_us_total / iterations;

    row->ok = ok_correctness ? 1 : 0;
    row->notes = row->notes ? row->notes : "";
}

#else /* IS_KEM */

/* KEM mode */
#include "api.h"

static uint8_t kem_pk[PQCLEAN_MLKEM512_CLEAN_CRYPTO_PUBLICKEYBYTES];
static uint8_t kem_sk[PQCLEAN_MLKEM512_CLEAN_CRYPTO_SECRETKEYBYTES];
static uint8_t kem_ct[PQCLEAN_MLKEM512_CLEAN_CRYPTO_CIPHERTEXTBYTES];
static uint8_t kem_ss_enc[PQCLEAN_MLKEM512_CLEAN_CRYPTO_BYTES];
static uint8_t kem_ss_dec[PQCLEAN_MLKEM512_CLEAN_CRYPTO_BYTES];

static void bench_kem_op(const char *op_name, uint32_t iterations, csv_row_t *row) {
    uint64_t start_cycles, end_cycles;

    for (uint32_t i = 0; i < iterations; i++) {
        if (op_name[0] == 'k') {
            PQCLEAN_MLKEM512_CLEAN_crypto_kem_keypair(kem_pk, kem_sk);
        } else if (op_name[0] == 'e') {
            PQCLEAN_MLKEM512_CLEAN_crypto_kem_enc(kem_ct, kem_ss_enc, kem_pk);
        } else {
            PQCLEAN_MLKEM512_CLEAN_crypto_kem_dec(kem_ss_dec, kem_ct, kem_sk);
        }
    }


    platform_trigger_high();
    start_cycles = platform_cycle_count();
    for (uint32_t i = 0; i < iterations; i++) {
        if (op_name[0] == 'k') {
            PQCLEAN_MLKEM512_CLEAN_crypto_kem_keypair(kem_pk, kem_sk);
        } else if (op_name[0] == 'e') {
            PQCLEAN_MLKEM512_CLEAN_crypto_kem_enc(kem_ct, kem_ss_enc, kem_pk);
        } else {
            PQCLEAN_MLKEM512_CLEAN_crypto_kem_dec(kem_ss_dec, kem_ct, kem_sk);
        }
    }
    end_cycles = platform_cycle_count();
    platform_trigger_low();

    uint64_t cycles_total = end_cycles - start_cycles;

    row->enc_cycles_total   = cycles_total;
    row->iterations         = iterations;
    row->freq_hz            = platform_freq_hz();
    row->enc_time_us_total  = (double)cycles_total / ((double)platform_freq_hz() / 1e6);
    row->enc_time_us_per_op = row->enc_time_us_total / iterations;
    row->ok                 = 1;
    row->notes              = op_name;
}

#endif /* IS_KEM */

static void run_benchmark_once(void) {
    print_csv_header();
#ifdef IS_KEM
    platform_delay_ms(100);

    PQCLEAN_MLKEM512_CLEAN_crypto_kem_keypair(kem_pk, kem_sk);
    PQCLEAN_MLKEM512_CLEAN_crypto_kem_enc(kem_ct, kem_ss_enc, kem_pk);

    const char *ops[] = {"keygen", "encap", "decap"};
    const uint32_t kem_iters = 10;

    for (int op = 0; op < 3; op++) {
        csv_row_t row = {0};
        char ts[32];
        char rid[256];

        make_timestamp_iso_utc(ts, sizeof(ts));
        make_run_id(rid, sizeof(rid), XSTR(ALGO_NAME), BOARD_NAME, BOARD_NAME, TARGET_ARCH);

        row.timestamp_iso = ts;
        row.run_id = rid;
        row.algorithm = XSTR(ALGO_NAME);
        row.implementation = "ref";
        row.version = VERSION_STR;
        row.board = BOARD_NAME;
        row.cflags = COMPILER_FLAGS;
        row.arch = TARGET_ARCH;
        row.compiler = COMPILER_ID;
        row.compiler_version = COMPILER_VERSION;
        row.key_len = PQCLEAN_MLKEM512_CLEAN_CRYPTO_SECRETKEYBYTES;
        row.tag_len = PQCLEAN_MLKEM512_CLEAN_CRYPTO_BYTES;

        bench_kem_op(ops[op], kem_iters, &row);
        print_csv_row(&row);
        platform_delay_ms(50);
    }

#else
    for (size_t s = 0; s < NUM_MSG_SIZES; s++) {
        size_t mlen = MSG_SIZES[s];
        size_t adlen = BENCH_AD_LEN;
        uint32_t iters = BENCH_ITERS[s];

        csv_row_t row = {0};
        char ts[32];
        char rid[256];

        make_timestamp_iso_utc(ts, sizeof(ts));
        make_run_id(rid, sizeof(rid), XSTR(ALGO_NAME), BOARD_NAME, BOARD_NAME, TARGET_ARCH);

        row.timestamp_iso = ts;
        row.run_id = rid;
        row.algorithm = XSTR(ALGO_NAME);
        row.implementation = "ref";
        row.version = VERSION_STR;
        row.board = BOARD_NAME;
        row.cflags = COMPILER_FLAGS;
        row.arch = TARGET_ARCH;
        row.compiler = COMPILER_ID;
        row.compiler_version = COMPILER_VERSION;

        if (!correctness_and_tamper(mlen, adlen)) {
            row.ok = 0;
            row.notes = "KAT failure or tamper check failed";
            print_csv_row(&row);
            continue;
        }

        bench_one(mlen, adlen, iters, &row);
        print_csv_row(&row);
    }
#endif

}

int main(void) {
    platform_init();
    platform_puts("ORBIT benchmark starting...\r\n");

#ifndef ORBIT_NO_STDIO_WAIT
    while (!platform_stdio_ready()) {
        platform_delay_ms(100);
    }
#endif
    platform_delay_ms(PLATFORM_BOOT_DELAY_MS);

    for (uint32_t orbit_run = 0; orbit_run < ORBIT_ENERGY_RUNS; orbit_run++) {
        if (orbit_run > 0) {
            platform_delay_ms(ORBIT_INTER_RUN_DELAY_MS);
        }

        platform_frame_trigger_high();
        platform_delay_ms(50);
        run_benchmark_once();
        platform_frame_trigger_low();
    }

    platform_puts("ORBIT benchmark completed.\r\n");

#ifdef PLATFORM_EXIT_AFTER_BENCHMARK
    return 0;
#else
    while (1) {}

    return 0;
#endif
}
