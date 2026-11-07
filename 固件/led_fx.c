#include "led_fx.h"
#include "ws2812.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"
#include "esp_log.h"
#include <math.h>
#include <string.h>

static const char *TAG = "ledfx";

#define LED_MAX_N 64
static int s_n = 0;
static int s_mode = 1;
static int s_level = 12;
static volatile int64_t s_beat_us = 0;
static volatile int s_beat_flag = 0;
static int64_t s_last_beat_upd_us = 0;
static float s_bpm_raw = 0.0f;
static float s_bpm_s = 0.0f;      /* 平滑后 */
static float s_hue = 0.0f;        /* 0~1 色相偏移 */
static float s_pulse = 0.0f;
static int s_ok = 0;
/* 可配置核心参数 */
static float s_rot_idle  = 0.010f;
static float s_rot_max   = 0.540f;
static float s_hue_idle  = 0.58f;
static float s_hue_span  = 0.58f;
static float s_pbase     = 0.15f;
static float s_ppeak     = 1.80f;
static float s_gate      = 0.70f;
static float s_decay     = 0.35f;   /* 衰减时间常数(秒) */
static TaskHandle_t s_task = NULL;

static void hsv2rgb(float h, float s, float v, uint8_t *r, uint8_t *g, uint8_t *b)
{
    h = h - floorf(h);
    float hh = h * 6.0f;
    int i = (int)hh;
    float f = hh - i;
    float p = v * (1.0f - s);
    float q = v * (1.0f - s * f);
    float t = v * (1.0f - s * (1.0f - f));
    float rr, gg, bb;
    switch (i % 6) {
        case 0: rr = v; gg = t; bb = p; break;
        case 1: rr = q; gg = v; bb = p; break;
        case 2: rr = p; gg = v; bb = t; break;
        case 3: rr = p; gg = q; bb = v; break;
        case 4: rr = t; gg = p; bb = v; break;
        default: rr = v; gg = p; bb = q; break;
    }
    *r = (uint8_t)(rr * 255.0f);
    *g = (uint8_t)(gg * 255.0f);
    *b = (uint8_t)(bb * 255.0f);
}


/* 按感知亮度补偿取色：让红/绿/蓝看起来一样亮，避免旋转时忽明忽暗 */
static void hsv_px(int idx, float h, float level, float extra)
{
    uint8_t r, g, b;
    hsv2rgb(h, 1.0f, 1.0f, &r, &g, &b);
    float luma = (0.299f * r + 0.587f * g + 0.114f * b) / 255.0f;
    if (luma < 0.08f) luma = 0.08f;
    float k = 0.42f / luma;          /* 目标等效亮度 */
    if (k > 1.8f) k = 1.8f;          /* 蓝最多提亮 1.8 倍，控制电流 */
    if (k < 0.65f) k = 0.65f;
    float v = level * k * extra;
    if (v > 1.0f) v = 1.0f;
    ws2812_set(idx, (uint8_t)(r * v), (uint8_t)(g * v), (uint8_t)(b * v));
}

/* 旋转速度（圈/秒）：无信号时极慢，随心率加快 */
static float rev_speed(void)
{
    float bpm = s_bpm_s;
    if (bpm < 40.0f) return s_rot_idle;
    if (bpm > 180.0f) bpm = 180.0f;
    return s_rot_idle + (bpm - 40.0f) / 140.0f * s_rot_max;
}

/* 基色随心率在蓝(静息)到红(高心率)之间移动 */
static float hue_base(void)
{
    float bpm = s_bpm_s;
    if (bpm < 40.0f) return s_hue_idle;
    if (bpm > 180.0f) bpm = 180.0f;
    return s_hue_idle - (bpm - 40.0f) / 140.0f * s_hue_span;
}

static void render(int64_t now_us, float dt)
{
    float lvl = s_level / 100.0f;
    if (lvl <= 0.0f || s_mode == 0) {
        ws2812_fill(0, 0, 0);
        ws2812_show();
        return;
    }

    int fresh = (now_us - s_beat_us) < 3000000LL;

    switch (s_mode) {
    case 1: {   /* 彩虹旋转，速度由平滑心率控制 */
        s_hue += rev_speed() * dt;
        float hb = hue_base();
        for (int i = 0; i < s_n; i++) {
            float h = hb + s_hue + (float)i / s_n;
            float pulse_lift = s_pbase + (s_ppeak - s_pbase) * s_pulse;
            hsv_px(i, h, lvl, pulse_lift);
        }
        break;
    }
    case 2: {   /* 心跳脉冲：红光跟随搏动 */
        if (fresh) {
            s_pulse *= expf(-dt / s_decay);
            float b = s_pulse;
            uint8_t v = (uint8_t)(255.0f * lvl * b);
            ws2812_fill(v, 0, 0);
        } else {
            uint8_t v = (uint8_t)(255.0f * lvl * 0.25f);
            ws2812_fill(0, 0, v);
        }
        break;
    }
    case 3: {   /* 单色呼吸（蓝） */
        float ph = fmodf((float)(now_us / 1000000.0), 2.0f) / 2.0f;
        float t = (ph < 0.5f) ? ph * 2.0f : (2.0f - ph * 2.0f);
        uint8_t v = (uint8_t)(255.0f * lvl * 0.5f * t);
        ws2812_fill(0, 0, v);
        break;
    }
    case 4: {   /* BPM 水位：亮几颗 */
        float bpm = s_bpm_s;
        if (bpm < 40.0f) bpm = 40.0f;
        if (bpm > 180.0f) bpm = 180.0f;
        int lit = (int)((bpm - 40.0f) / 140.0f * s_n + 0.5f);
        if (lit > s_n) lit = s_n;
        for (int i = 0; i < s_n; i++) {
            if (i < lit) {
                float h = 0.33f - 0.33f * ((float)i / s_n);   /* 绿 -> 红 */
                uint8_t r, g, b;
                hsv2rgb(h, 1.0f, lvl, &r, &g, &b);
                ws2812_set(i, r, g, b);
            } else ws2812_set(i, 0, 0, 0);
        }
        break;
    }
    case 5: {   /* 彩虹呼吸：整条同色，色相缓慢漂移 */
        s_hue += 0.05f * dt;
        float ph = fmodf((float)(now_us / 1000000.0), 3.0f) / 3.0f;
        float t = (ph < 0.5f) ? ph * 2.0f : (2.0f - ph * 2.0f);
        float tv = lvl * (0.3f + 0.7f * t);
        for (int i = 0; i < s_n; i++) hsv_px(i, s_hue, tv, 1.0f);
        break;
    }
    case 6: {   /* 诊断：静止纯红，无任何动画 */
        uint8_t v = (uint8_t)(255.0f * lvl);
        ws2812_fill(v, 0, 0);
        break;
    }
    case 7: {   /* 诊断：静止纯白 */
        uint8_t v = (uint8_t)(255.0f * lvl);
        ws2812_fill(v, v, v);
        break;
    }
    default:
        ws2812_fill(0, 0, 0);
        break;
    }
    ws2812_show();
}

static void led_task(void *arg)
{
    int64_t last = esp_timer_get_time();
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(20));
        int64_t now = esp_timer_get_time();
        float dt = (now - last) / 1000000.0f;
        last = now;
        if (dt > 0.2f) dt = 0.2f;

        /* 搏动事件 */
        if (s_beat_flag) {
            s_beat_flag = 0;
            s_pulse = 1.0f;
        } else {
            s_pulse *= expf(-dt / s_decay);
        }

        /* 心率平滑：时间常数 3.5s，且做变化率限幅 */
        if (s_bpm_raw > 0.0f) {
            if (s_bpm_s <= 0.0f) s_bpm_s = s_bpm_raw;
            float alpha = 1.0f - expf(-dt / 3.5f);
            float d = (s_bpm_raw - s_bpm_s) * alpha;
            float lim = 12.0f * dt;              /* 最多 12bpm/s */
            if (d > lim) d = lim;
            if (d < -lim) d = -lim;
            s_bpm_s += d;
        }

        render(now, dt);
    }
}

void led_fx_init(int gpio, int n)
{
    if (n <= 0 || n > LED_MAX_N) return;
    s_n = n;
    if (ws2812_init(gpio, n) != 0) {
        ESP_LOGE(TAG, "ws2812 初始化失败");
        return;
    }
    s_ok = 1;
    ws2812_fill(0, 0, 0);
    ws2812_show();
    xTaskCreate(led_task, "led_fx", 3072, NULL, 2, &s_task);
    ESP_LOGI(TAG, "就绪: GPIO%d %d颗 mode=%d level=%d%%", gpio, n, s_mode, s_level);
}

void led_fx_set_level(int pct)
{
    if (pct < 0) pct = 0;
    if (pct > 100) pct = 100;
    s_level = pct;
}

int led_fx_level(void) { return s_level; }

void led_fx_set_mode(int mode)
{
    if (mode < 0 || mode > 7) return;
    s_mode = mode;
    s_pulse = 0.0f;
}

int led_fx_mode(void) { return s_mode; }

void led_fx_beat(void)
{
    if (s_bpm_raw <= 0.0f) return;   /* 没出数时不响应 */
    float bpm = (s_bpm_s > 40.0f) ? s_bpm_s : s_bpm_raw;
    if (bpm < 30.0f) bpm = 30.0f;
    /* 一个心动周期内只承认一次搏动，挡掉噪声重复触发 */
    int64_t min_gap_us = (int64_t)(s_gate * 60.0e6f / bpm);
    int64_t now = esp_timer_get_time();
    if (s_last_beat_upd_us && now - s_last_beat_upd_us < min_gap_us) return;
    s_last_beat_upd_us = now;
    s_beat_flag = 1;
}

void led_fx_set_bpm(float bpm) { s_bpm_raw = bpm; }

void led_fx_set_params(float rot_idle, float rot_max, float hue_idle,
                       float hue_span, float pbase, float ppeak, float gate, float decay)
{
    s_rot_idle = rot_idle; s_rot_max = rot_max;
    s_hue_idle = hue_idle; s_hue_span = hue_span;
    s_pbase = pbase; s_ppeak = ppeak; s_gate = gate; s_decay = decay;
}

void led_fx_get_params(float *rot_idle, float *rot_max, float *hue_idle,
                       float *hue_span, float *pbase, float *ppeak, float *gate, float *decay)
{
    if (rot_idle) *rot_idle = s_rot_idle;
    if (rot_max)  *rot_max  = s_rot_max;
    if (hue_idle) *hue_idle = s_hue_idle;
    if (hue_span) *hue_span = s_hue_span;
    if (pbase)    *pbase    = s_pbase;
    if (ppeak)    *ppeak    = s_ppeak;
    if (gate)     *gate     = s_gate;
    if (decay)    *decay    = s_decay;
}

void led_fx_status(int *mode, int *level, float *bpm_smooth)
{
    if (mode) *mode = s_mode;
    if (level) *level = s_level;
    if (bpm_smooth) *bpm_smooth = s_bpm_s;
}
