#include "ws2812.h"
#include "driver/rmt_tx.h"
#include "driver/rmt_encoder.h"
#include "esp_log.h"
#include <string.h>

#define WS2812_MAX_LEDS 64
static const char *TAG = "ws2812";

static rmt_channel_handle_t s_chan = NULL;
static rmt_encoder_handle_t s_enc  = NULL;
static uint8_t s_buf[WS2812_MAX_LEDS * 3];
static int s_n = 0;

int ws2812_init(int gpio_num, int count)
{
    if (count <= 0 || count > WS2812_MAX_LEDS) {
        ESP_LOGE(TAG, "LED 数量非法: %d", count);
        return -1;
    }
    s_n = count;
    memset(s_buf, 0, sizeof(s_buf));

    /* C3 无 RMT DMA，用 4 个内存块拼成 ping-pong（96 symbol 一块，约 125us 余量） */
    rmt_tx_channel_config_t tc = {
        .gpio_num            = gpio_num,
        .clk_src             = RMT_CLK_SRC_DEFAULT,
        .resolution_hz        = 10000000,          /* 10MHz -> 1 tick = 100ns */
        .mem_block_symbols   = 192,
        .trans_queue_depth   = 2,
    };
    esp_err_t err = rmt_new_tx_channel(&tc, &s_chan);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "rmt_new_tx_channel: %s", esp_err_to_name(err));
        s_chan = NULL;
        return -1;
    }
    err = rmt_enable(s_chan);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "rmt_enable: %s", esp_err_to_name(err));
        return -1;
    }

    rmt_bytes_encoder_config_t bc = {
        /* WS2812B: T0H 0.4us / T0L 0.85us，T1H 0.8us / T1L 0.45us */
        .bit0 = { .level0 = 1, .duration0 = 4, .level1 = 0, .duration1 = 9 },
        .bit1 = { .level0 = 1, .duration0 = 8, .level1 = 0, .duration1 = 5 },
        .flags = { .msb_first = 1 },
    };
    err = rmt_new_bytes_encoder(&bc, &s_enc);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "rmt_new_bytes_encoder: %s", esp_err_to_name(err));
        return -1;
    }

    ESP_LOGI(TAG, "就绪: GPIO%d, %d 颗", gpio_num, count);
    return 0;
}

void ws2812_set(int idx, uint8_t r, uint8_t g, uint8_t b)
{
    if (idx < 0 || idx >= s_n) return;
    /* WS2812 数据顺序: G R B */
    s_buf[idx * 3 + 0] = g;
    s_buf[idx * 3 + 1] = r;
    s_buf[idx * 3 + 2] = b;
}

void ws2812_fill(uint8_t r, uint8_t g, uint8_t b)
{
    for (int i = 0; i < s_n; i++) ws2812_set(i, r, g, b);
}

int ws2812_show(void)
{
    if (!s_chan || !s_enc) return -1;
    rmt_transmit_config_t tc = { .loop_count = 0 };
    esp_err_t err = rmt_transmit(s_chan, s_enc, s_buf, (size_t)s_n * 3, &tc);
    if (err != ESP_OK) return -1;
    return (rmt_tx_wait_all_done(s_chan, 50) == ESP_OK) ? 0 : -1;
}
