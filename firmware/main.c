/* v11：嵌入式脉搏检测（峰普查法 + OLED 赛博把脉 UI + BLE）
 * 接线: OLED SDA=GPIO8, SCL=GPIO10 | 传感器 GPIO0 | 按钮GPIO4 | 灯环DIN GPIO5
 * 左列: GPIO5,6,7,8,9,10,20,21 | 右列: 5V,G,3V3,GPIO4,3,2,1,0
 */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "driver/usb_serial_jtag.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_adc/adc_continuous.h"
#include "ssd1306.h"
#include "led_fx.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "host/ble_gap.h"
#include "host/ble_gatt.h"
#include "host/util/util.h"
#include "services/gap/ble_svc_gap.h"
#include "os/os_mbuf.h"
#include <string.h>
#include <stdlib.h>
#include <math.h>

static const char *TAG = "pulse";

/* ---------- BLE: GATT服务 + 持续广播 ---------- */
/* UUID: 服务 FFE0, 通知特征 FFE1 (兼容常见BLE串口模块习惯) */
static const ble_uuid128_t gatt_svc_uuid =
    BLE_UUID128_INIT(0xFB,0x34,0x9B,0x5F,0x80,0x00,0x00,0x80,0x00,0x10,0x00,0x00,0xE0,0xFF,0x00,0x00);
static const ble_uuid128_t gatt_chr_uuid =
    BLE_UUID128_INIT(0xFB,0x34,0x9B,0x5F,0x80,0x00,0x00,0x80,0x00,0x10,0x00,0x00,0xE1,0xFF,0x00,0x00);
/* FFE2: 波形流（int16 LE x10 每 100ms） */
static const ble_uuid128_t gatt_wave_uuid =
    BLE_UUID128_INIT(0xFB,0x34,0x9B,0x5F,0x80,0x00,0x00,0x80,0x00,0x10,0x00,0x00,0xE2,0xFF,0x00,0x00);

static uint16_t conn_handle = BLE_HS_CONN_HANDLE_NONE;
static uint16_t chr_val_handle;
static uint16_t wave_val_handle;
/* FFE3: 断线补发（含时间戳头） */
static const ble_uuid128_t gatt_replay_uuid =
    BLE_UUID128_INIT(0xFB,0x34,0x9B,0x5F,0x80,0x00,0x00,0x80,0x00,0x10,0x00,0x00,0xE3,0xFF,0x00,0x00);
static uint16_t replay_val_handle;
/* FFE4: 补发请求（可写 4 字节 LE：起始板载毫秒，0=整个缓存） */
static const ble_uuid128_t gatt_replay_cmd_uuid =
    BLE_UUID128_INIT(0xFB,0x34,0x9B,0x5F,0x80,0x00,0x00,0x80,0x00,0x10,0x00,0x00,0xE4,0xFF,0x00,0x00);
static int ble_ready = 0;  /* GATT 注册完成 */
/* ============ 运行时可调参数（出厂默认=已验证配置） ============ */
static int   cfg_peak_thr     = 40;
static int   cfg_peak_gap_ms  = 350;
static float cfg_p50_gate     = 18.0f;
static float cfg_p95_gate     = 45.0f;
static int   cfg_dbg_ui       = 1;
static int   cfg_dbg_trk      = 1;
static int   cfg_dbg_dump     = 1;
static int   cfg_tracker_mode = 2;   /* 0=关 1=接管 2=影子 */
static int   cfg_wave_tx      = 1;
static int   cfg_raw_print   = 1;
static int   cfg_led_level   = 12;
static int   cfg_led_mode    = 1;
static int   cfg_rot_idle    = 10;    /* x1000 */
static int   cfg_rot_max     = 540;   /* x1000 */
static int   cfg_hue_idle    = 580;   /* x1000 */
static int   cfg_hue_span    = 580;   /* x1000 */
static int   cfg_p_base      = 300;   /* x1000 */
static int   cfg_p_peak      = 1500;  /* x1000 */
static int   cfg_b_gate      = 700;   /* x1000 */
static int   cfg_decay       = 350;   /* x1000 秒 */
static int   cfg_cons        = 40;    /* 0~100，越大越保守 */
/* cons 派生门限 */
static float g_cv_max   = 0.114f;
static int   g_n_iv_min = 6;
static int   g_warm_min = 5;

static void apply_cons(void)
{
    if (cfg_cons < 0) cfg_cons = 0;
    if (cfg_cons > 100) cfg_cons = 100;
    g_cv_max   = 0.150f - 0.00090f * cfg_cons;   /* 0.150 -> 0.060 */
    g_n_iv_min = 5 + cfg_cons / 25;              /* 5 -> 9 */
    g_warm_min = 4 + cfg_cons / 30;              /* 4 -> 7 */
}   /* 灯效: 0关 1心跳 2彩虹旋转 3呼吸 4水位 5彩虹呼吸 */  /* 灯带亮度 %（AAA 电池，默认 20） */

static nvs_handle_t cfg_nvs;
static int cfg_nvs_ok = 0;

static void cfg_load(void)
{
    if (!cfg_nvs_ok) return;
    int32_t v;
    if (nvs_get_i32(cfg_nvs, "peak_thr", &v) == ESP_OK) cfg_peak_thr = v;
    if (nvs_get_i32(cfg_nvs, "peak_gap", &v) == ESP_OK) cfg_peak_gap_ms = v;
    if (nvs_get_i32(cfg_nvs, "p50x100", &v) == ESP_OK) cfg_p50_gate = v / 100.0f;
    if (nvs_get_i32(cfg_nvs, "p95x100", &v) == ESP_OK) cfg_p95_gate = v / 100.0f;
    if (nvs_get_i32(cfg_nvs, "dbg_ui", &v) == ESP_OK) cfg_dbg_ui = v;
    if (nvs_get_i32(cfg_nvs, "dbg_trk", &v) == ESP_OK) cfg_dbg_trk = v;
    if (nvs_get_i32(cfg_nvs, "dbg_dump", &v) == ESP_OK) cfg_dbg_dump = v;
    if (nvs_get_i32(cfg_nvs, "trk_mode", &v) == ESP_OK) cfg_tracker_mode = v;
    if (nvs_get_i32(cfg_nvs, "led_lvl", &v) == ESP_OK) cfg_led_level = v;
    if (nvs_get_i32(cfg_nvs, "led_mode", &v) == ESP_OK) cfg_led_mode = v;
    if (nvs_get_i32(cfg_nvs, "rot_idle", &v) == ESP_OK) cfg_rot_idle = v;
    if (nvs_get_i32(cfg_nvs, "rot_max", &v) == ESP_OK) cfg_rot_max = v;
    if (nvs_get_i32(cfg_nvs, "hue_idle", &v) == ESP_OK) cfg_hue_idle = v;
    if (nvs_get_i32(cfg_nvs, "hue_span", &v) == ESP_OK) cfg_hue_span = v;
    if (nvs_get_i32(cfg_nvs, "p_base", &v) == ESP_OK) cfg_p_base = v;
    if (nvs_get_i32(cfg_nvs, "p_peak", &v) == ESP_OK) cfg_p_peak = v;
    if (nvs_get_i32(cfg_nvs, "b_gate", &v) == ESP_OK) cfg_b_gate = v;
    if (nvs_get_i32(cfg_nvs, "decay", &v) == ESP_OK) cfg_decay = v;
    if (nvs_get_i32(cfg_nvs, "cons", &v) == ESP_OK) cfg_cons = v;
    ESP_LOGI(TAG, "配置加载: thr=%d gap=%d p50=%.0f p95=%.0f dbg=%d/%d/%d mode=%d",
             cfg_peak_thr, cfg_peak_gap_ms, cfg_p50_gate, cfg_p95_gate,
             cfg_dbg_ui, cfg_dbg_trk, cfg_dbg_dump, cfg_tracker_mode);
}

static void cfg_save(void)
{
    if (!cfg_nvs_ok) return;
    nvs_set_i32(cfg_nvs, "peak_thr", cfg_peak_thr);
    nvs_set_i32(cfg_nvs, "peak_gap", cfg_peak_gap_ms);
    nvs_set_i32(cfg_nvs, "p50x100", (int32_t)(cfg_p50_gate * 100));
    nvs_set_i32(cfg_nvs, "p95x100", (int32_t)(cfg_p95_gate * 100));
    nvs_set_i32(cfg_nvs, "dbg_ui", cfg_dbg_ui);
    nvs_set_i32(cfg_nvs, "dbg_trk", cfg_dbg_trk);
    nvs_set_i32(cfg_nvs, "dbg_dump", cfg_dbg_dump);
    nvs_set_i32(cfg_nvs, "trk_mode", cfg_tracker_mode);
    nvs_set_i32(cfg_nvs, "led_lvl", cfg_led_level);
    nvs_set_i32(cfg_nvs, "led_mode", cfg_led_mode);
    nvs_set_i32(cfg_nvs, "rot_idle", cfg_rot_idle);
    nvs_set_i32(cfg_nvs, "rot_max", cfg_rot_max);
    nvs_set_i32(cfg_nvs, "hue_idle", cfg_hue_idle);
    nvs_set_i32(cfg_nvs, "hue_span", cfg_hue_span);
    nvs_set_i32(cfg_nvs, "p_base", cfg_p_base);
    nvs_set_i32(cfg_nvs, "p_peak", cfg_p_peak);
    nvs_set_i32(cfg_nvs, "b_gate", cfg_b_gate);
    nvs_set_i32(cfg_nvs, "decay", cfg_decay);
    nvs_set_i32(cfg_nvs, "cons", cfg_cons);
    nvs_commit(cfg_nvs);
    ESP_LOGI(TAG, "配置已保存到 NVS");
}

static void cfg_print(void)
{
    ESP_LOGI(TAG, "CFG|thr=%d gap=%d p50=%.0f p95=%.0f|dbg_ui=%d dbg_trk=%d dbg_dump=%d|mode=%d wave=%d",
             cfg_peak_thr, cfg_peak_gap_ms, cfg_p50_gate, cfg_p95_gate,
             cfg_dbg_ui, cfg_dbg_trk, cfg_dbg_dump, cfg_tracker_mode, cfg_wave_tx);
    ESP_LOGI(TAG, "FX|mode=%d led=%d%% rot=%.3f/%.3f hue=%.2f/%.2f pulse=%.2f/%.2f gate=%.2f decay=%.2f",
             cfg_led_mode, cfg_led_level, cfg_rot_idle / 1000.0f, cfg_rot_max / 1000.0f,
             cfg_hue_idle / 1000.0f, cfg_hue_span / 1000.0f,
             cfg_p_base / 1000.0f, cfg_p_peak / 1000.0f, cfg_b_gate / 1000.0f,
             cfg_decay / 1000.0f);
    ESP_LOGI(TAG, "CONS|%d cv_max=%.3f n_iv=%d warm=%d", cfg_cons, g_cv_max, g_n_iv_min, g_warm_min);
}


/* ---- 蜂鸣器标定：GPIO6 方波驱动，频率/时长可配 ---- */
static void buzz_play(int hz, int secs)
{
    if (hz < 1) hz = 1;
    if (hz > 200) hz = 200;
    if (secs < 1) secs = 1;
    if (secs > 30) secs = 30;
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << 6,
        .mode = GPIO_MODE_OUTPUT,
    };
    gpio_config(&io);
    int half_us = 500000 / hz;
    int64_t n = (int64_t)hz * secs * 2;   /* 半周期数 */
    for (int64_t i = 0; i < n; i++) {
        gpio_set_level(6, i & 1);
        esp_rom_delay_us(half_us);
    }
    gpio_set_level(6, 0);
    ESP_LOGI(TAG, "buzz 完成: %dHz %ds", hz, secs);
}

/* 命令解析：thr 40 / gap 350 / q 18 45 / dbg 0 / trk 0 / dump 0 / mode 2 / save / ? */
static void cfg_cmd(const char *cmd)
{
    char buf[96];
    strncpy(buf, cmd, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = 0;
    char *save = NULL;
    char *tok = strtok_r(buf, " ", &save);
    if (!tok) return;
    if (!strcmp(tok, "?")) { cfg_print(); return; }
    if (!strcmp(tok, "save")) { cfg_save(); return; }
    char *a1 = strtok_r(NULL, " ", &save);
    if (!a1) { cfg_print(); return; }
    if (!strcmp(tok, "thr"))   { cfg_peak_thr = atoi(a1); }
    else if (!strcmp(tok, "gap")) { cfg_peak_gap_ms = atoi(a1); }
    else if (!strcmp(tok, "q")) {
        cfg_p50_gate = atof(a1);
        char *a2 = strtok_r(NULL, " ", &save);
        if (a2) cfg_p95_gate = atof(a2);
    }
    else if (!strcmp(tok, "dbg")) { cfg_dbg_ui = cfg_dbg_trk = atoi(a1); }
    else if (!strcmp(tok, "dump")) { cfg_dbg_dump = atoi(a1); }
    else if (!strcmp(tok, "mode")) { cfg_tracker_mode = atoi(a1); }
    else if (!strcmp(tok, "wave")) { cfg_wave_tx = atoi(a1); }
    else if (!strcmp(tok, "raw")) { cfg_raw_print = atoi(a1); }
    else if (!strcmp(tok, "led")) { led_fx_set_level(atoi(a1)); cfg_led_level = led_fx_level(); }
    else if (!strcmp(tok, "fx"))  { led_fx_set_mode(atoi(a1)); cfg_led_mode = led_fx_mode(); }
    else if (!strcmp(tok, "rot")) { cfg_rot_idle = (int)(atof(a1) * 1000); char *a2 = strtok_r(NULL, " ", &save); if (a2) cfg_rot_max = (int)(atof(a2) * 1000); }
    else if (!strcmp(tok, "hue")) { cfg_hue_idle = (int)(atof(a1) * 1000); char *a2 = strtok_r(NULL, " ", &save); if (a2) cfg_hue_span = (int)(atof(a2) * 1000); }
    else if (!strcmp(tok, "pulse")) { cfg_p_base = (int)(atof(a1) * 1000); char *a2 = strtok_r(NULL, " ", &save); if (a2) cfg_p_peak = (int)(atof(a2) * 1000); }
    else if (!strcmp(tok, "gate")) { cfg_b_gate = (int)(atof(a1) * 1000); }
    else if (!strcmp(tok, "decay")) { cfg_decay = (int)(atof(a1) * 1000); }
    else if (!strcmp(tok, "cons")) { cfg_cons = atoi(a1); apply_cons(); }
    else if (!strcmp(tok, "buzz")) {
        char *a2 = strtok_r(NULL, " ", &save);
        int secs = a2 ? atoi(a2) : 3;
        buzz_play(atoi(a1), secs);
        return;
    }
    else { ESP_LOGW(TAG, "未知命令: %s", tok); return; }
    led_fx_set_params(cfg_rot_idle / 1000.0f, cfg_rot_max / 1000.0f,
                      cfg_hue_idle / 1000.0f, cfg_hue_span / 1000.0f,
                      cfg_p_base / 1000.0f, cfg_p_peak / 1000.0f,
                      cfg_b_gate / 1000.0f, cfg_decay / 1000.0f);
    ESP_LOGI(TAG, "命令生效: %s %s", tok, a1);
    cfg_print();
}



/* 断线补发缓存：60 秒 @100Hz（12KB） */
#define WAVE_CACHE_N        6000
static int16_t wave_cache[WAVE_CACHE_N];
static int wave_cache_head = 0, wave_cache_cnt = 0;
static int64_t wave_cache_last_us = 0;
static volatile int replay_pending = 0;
static int replay_pos = 0;          /* 0..cnt, 0=最旧 */



static int gap_event(struct ble_gap_event *event, void *arg);
static void start_advertising(void)
{
    struct ble_gap_adv_params adv_params = { 0 };
    struct ble_hs_adv_fields fields = { 0 };
    adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;
    adv_params.disc_mode = BLE_GAP_DISC_MODE_GEN;
    adv_params.itvl_min = 32;
    adv_params.itvl_max = 64;
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.name = (const uint8_t *)"CYBER-PULSE";
    fields.name_len = strlen("CYBER-PULSE");
    fields.name_is_complete = 1;
    /* 注意: 主广播包上限31字节(flags 3 + 名字 13 = 16)，128位UUID放scan response */
    int rc = ble_gap_adv_set_fields(&fields);
    if (rc != 0) ESP_LOGE(TAG, "adv_set_fields 失败 rc=%d", rc);

    struct ble_hs_adv_fields rsp = { 0 };
    rsp.uuids128 = (const ble_uuid128_t *)&gatt_svc_uuid;
    rsp.uuids128_is_complete = 1;
    rsp.num_uuids128 = 1;
    rc = ble_gap_adv_rsp_set_fields(&rsp);
    if (rc != 0) ESP_LOGW(TAG, "adv_rsp_set_fields 失败 rc=%d", rc);

    rc = ble_gap_adv_start(BLE_OWN_ADDR_PUBLIC, NULL, BLE_HS_FOREVER, &adv_params, gap_event, NULL);
    if (rc != 0) ESP_LOGE(TAG, "adv_start 失败 rc=%d", rc);
}

static int gap_event(struct ble_gap_event *event, void *arg)
{
    switch (event->type) {
    case BLE_GAP_EVENT_CONNECT:
        conn_handle = event->connect.conn_handle;
        replay_pending = 1;
        replay_pos = 0;
        ESP_LOGI(TAG, "BLE已连接 handle=%d", conn_handle);
        break;
    case BLE_GAP_EVENT_DISCONNECT:
        ESP_LOGW(TAG, "BLE断开 reason=%d conn_handle was %d", event->disconnect.reason, conn_handle);
        conn_handle = BLE_HS_CONN_HANDLE_NONE;
        start_advertising();
        break;
    case BLE_GAP_EVENT_ADV_COMPLETE:
        start_advertising();
        break;
    default: break;
    }
    return 0;
}

static int chr_access(uint16_t conn, uint16_t attr, struct ble_gatt_access_ctxt *ctxt, void *arg)
{
    return 0; /* 只用通知，不需要读写 */
}

/* GATT 服务表：必须文件级 static const（NimBLE 只保存指针，栈上临时数组会失效） */
static int chr_access(uint16_t conn, uint16_t attr, struct ble_gatt_access_ctxt *ctxt, void *arg);
static int replay_cmd_write(uint16_t conn, uint16_t attr, struct ble_gatt_access_ctxt *ctxt, void *arg);

static const struct ble_gatt_chr_def gatt_chrs[] = {
    {
        .uuid = (ble_uuid_t *)&gatt_chr_uuid,
        .access_cb = chr_access,
        .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY,
        .val_handle = &chr_val_handle,
    },
    {
        .uuid = (ble_uuid_t *)&gatt_wave_uuid,
        .access_cb = chr_access,
        .flags = BLE_GATT_CHR_F_NOTIFY,
        .val_handle = &wave_val_handle,
    },
    {
        .uuid = (ble_uuid_t *)&gatt_replay_uuid,
        .access_cb = chr_access,
        .flags = BLE_GATT_CHR_F_NOTIFY,
        .val_handle = &replay_val_handle,
    },
    {
        .uuid = (ble_uuid_t *)&gatt_replay_cmd_uuid,
        .access_cb = replay_cmd_write,
        .flags = BLE_GATT_CHR_F_WRITE,
        .val_handle = NULL,
    },
    { 0 },
};

static const struct ble_gatt_svc_def gatt_svcs[] = {
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = (ble_uuid_t *)&gatt_svc_uuid,
        .characteristics = gatt_chrs,
    },
    { 0 },
};

/* 收到"补发请求"：从指定板载时刻开始补发（0 = 整个缓存） */
static int replay_cmd_write(uint16_t conn, uint16_t attr, struct ble_gatt_access_ctxt *ctxt, void *arg)
{
    if (ctxt->op != BLE_GATT_ACCESS_OP_WRITE_CHR) return BLE_ATT_ERR_UNLIKELY;
    uint16_t len = OS_MBUF_PKTLEN(ctxt->om);
    /* 文本命令：以 "C:" 开头 */
    if (len >= 2 && len < 96) {
        char tmp[96];
        os_mbuf_copydata(ctxt->om, 0, len, tmp);
        tmp[len] = 0;
        if (tmp[0] == 'C' && tmp[1] == ':') {
            ESP_LOGI(TAG, "收到命令: %s", tmp + 2);
            cfg_cmd(tmp + 2);
            return 0;
        }
    }
    uint32_t since_ms = 0;
    if (len >= 4) os_mbuf_copydata(ctxt->om, 0, 4, &since_ms);
    int skip = 0;
    if (since_ms != 0 && wave_cache_cnt > 0) {
        int64_t now_ms = wave_cache_last_us / 1000;
        int64_t age = now_ms - (int64_t)since_ms;
        if (age < 0) age = 0;
        skip = (int)(age / 10);
        if (skip > wave_cache_cnt) skip = wave_cache_cnt;
    }
    replay_pos = skip;
    replay_pending = 1;
    ESP_LOGI(TAG, "补发请求 since=%u -> skip=%d", (unsigned)since_ms, skip);
    return 0;
}

static void on_sync(void)
{
    int rc = ble_gatts_count_cfg(gatt_svcs);
    ESP_LOGI(TAG, "gatts_count_cfg rc=%d", rc);
    rc = ble_gatts_add_svcs(gatt_svcs);
    ESP_LOGI(TAG, "gatts_add_svcs rc=%d  chr_val_handle=%d wave_val_handle=%d",
             rc, chr_val_handle, wave_val_handle);
    rc = ble_gatts_start();
    ESP_LOGI(TAG, "gatts_start rc=%d", rc);
    ble_ready = 1;
    start_advertising();
}

static void host_task(void *param) { nimble_port_run(); nimble_port_freertos_deinit(); }

/* 串口命令输入（USB Serial JTAG）：可直接在串口敲 thr/gap/q/dbg/mode/wave/save/? */
static void cfg_cmd(const char *cmd);
static void serial_cmd_task(void *arg)
{
    usb_serial_jtag_driver_config_t cfg = {
        .tx_buffer_size = 256,
        .rx_buffer_size = 256,
    };
    if (usb_serial_jtag_driver_install(&cfg) != ESP_OK) {
        ESP_LOGW(TAG, "USB JTAG 驱动安装失败");
        vTaskDelete(NULL);
        return;
    }
    char line[96];
    int n = 0;
    uint8_t ch;
    while (1) {
        int r = usb_serial_jtag_read_bytes(&ch, 1, pdMS_TO_TICKS(50));
        if (r <= 0) continue;
        if (ch == '\r' || ch == '\n') {
            if (n > 0) {
                line[n] = 0;
                ESP_LOGI(TAG, "串口命令: %s", line);
                cfg_cmd(line);
                n = 0;
            }
        } else if (n < (int)sizeof(line) - 1) {
            line[n++] = (char)ch;
        }
    }
}

static void ble_enqueue(int type, const void *data, int len);

static void ble_notify(const char *data)
{
    ble_enqueue(0, data, (int)strlen(data));
}

/* ---- BLE 发送队列：主循环只入队，发送在独立任务里做，避免阻塞 ADC/OLED ---- */
typedef struct {
    uint8_t type;      /* 0=JSON, 1=波形 */
    uint8_t len;
    uint8_t data[160];
} ble_msg_t;

static QueueHandle_t ble_q = NULL;

/* 断线补发：每次 100 点（202 字节），约 20 批/秒 */
static int ble_send_replay_chunk(void)
{
    if (conn_handle == BLE_HS_CONN_HANDLE_NONE || wave_cache_cnt < 10) return 0;
    int n = wave_cache_cnt - replay_pos;
    if (n <= 0) return 0;
    if (n > 100) n = 100;
    uint8_t buf[206];
    int64_t last_offset_us = (int64_t)(wave_cache_cnt - 1 - replay_pos) * 10000LL;
    int32_t start_ms = (int32_t)((wave_cache_last_us - last_offset_us) / 1000);
    memcpy(buf, &start_ms, 4);
    uint16_t nn = (uint16_t)n;
    memcpy(buf + 4, &nn, 2);
    for (int k = 0; k < n; k++) {
        int idx = (wave_cache_head - wave_cache_cnt + replay_pos + k + WAVE_CACHE_N * 2) % WAVE_CACHE_N;
        int16_t v = wave_cache[idx];
        memcpy(buf + 6 + k * 2, &v, 2);
    }
    struct os_mbuf *om = ble_hs_mbuf_from_flat(buf, 6 + n * 2);
    if (om) ble_gattc_notify_custom(conn_handle, replay_val_handle, om);
    replay_pos += n;
    if (replay_pos >= wave_cache_cnt) return 0;   /* 补发完成 */
    return 1;
}

static void ble_tx_task(void *arg)
{
    ble_msg_t m;
    while (1) {
        if (replay_pending) {
            if (ble_send_replay_chunk()) {
                vTaskDelay(pdMS_TO_TICKS(50));    /* 20 批/秒 */
                continue;
            }
            replay_pending = 0;
        }
        if (xQueueReceive(ble_q, &m, pdMS_TO_TICKS(50)) != pdTRUE) continue;
        if (conn_handle == BLE_HS_CONN_HANDLE_NONE) continue;
        if (m.type == 1) {
            int n = m.len / 2;
            uint16_t mtu = ble_att_mtu(conn_handle);
            int max_n = (mtu > 3) ? (int)((mtu - 3) / 2) : 8;
            if (n > max_n) n = max_n;
            struct os_mbuf *om = ble_hs_mbuf_from_flat(m.data, n * 2);
            if (om) ble_gattc_notify_custom(conn_handle, wave_val_handle, om);
        } else {
            struct os_mbuf *om = ble_hs_mbuf_from_flat(m.data, m.len);
            if (om) ble_gattc_notify_custom(conn_handle, chr_val_handle, om);
        }
    }
}

static void ble_enqueue(int type, const void *data, int len)
{
    if (!ble_q) return;
    ble_msg_t m;
    m.type = (uint8_t)type;
    m.len = (uint8_t)len;
    if (len > 159) len = 159;
    memcpy(m.data, data, (size_t)len);
    xQueueSend(ble_q, &m, 0);   /* 满了就丢，绝不阻塞主循环 */
}

static void ble_notify_wave(const int16_t *v, int n)
{
    ble_enqueue(1, v, n * 2);
}

static void ble_init(void)
{
    nimble_port_init();
    ble_att_set_preferred_mtu(512);
    ble_hs_cfg.sync_cb = on_sync;
    ble_svc_gap_device_name_set("CYBER-PULSE");
    ble_q = xQueueCreate(12, sizeof(ble_msg_t));
    xTaskCreate(ble_tx_task, "ble_tx", 4096, NULL, 5, NULL);
    nimble_port_freertos_init(host_task);
    ESP_LOGI(TAG, "BLE GATT服务已启动");
}

/* ---------- 硬件配置 ---------- */
#define ADC_CHANNEL         ADC_CHANNEL_0
#define SAMPLE_FREQ_HZ      1000
#define WIN_SAMPLES         5
#define READ_BUF_SIZE       2048
#define FRAME_SIZE          512
#define STORE_BUF_SIZE      16384
#define I2C_SDA             8
#define I2C_SCL             10
#define OLED_HEIGHT         32
#define BTN_GPIO            4

/* ---------- 峰普查算法参数 ---------- */
#define PEAK_THRESH         40
#define PEAK_MIN_GAP_MS     350   /* 退回老方法：350ms 排除重搏波（跑步上限约170BPM） */
#define BASELINE_TAU_MS     4000.0f
#define IV_MIN_MS           300   /* 43~200 BPM */
#define IV_MAX_MS           1400
#define BPM_MED_N           9
#define P95_WIN_N           800          /* 4秒p95窗口 */
#define SNAP_THRESH         80
/* ---- 跑步模式: 卡尔曼跟踪 + 伪迹门 ---- */
#define PAIR_LO             0.55f
#define PAIR_HI             1.80f
#define KF_SIGMA_A          2.0f    /* BPM/s^2 过程噪声 */
#define KF_SIGMA_T          0.020f  /* 间隔计时误差 s */
#define KF_GATE             4.0f
#define V_MAX               8.0f
#define SLEW_MAX            300     /* counts/5ms 冲击陡度 */
#define AMP_RATIO           3.0f
#define USE_TRACKER         2   /* 0=关 1=新法接管 2=影子模式(老方法输出+新法并行记录) */
#define SNAP_CNT_N          20

/* ---------- 峰普查状态 ---------- */
static int q_cnt = 2;          /* 质量滞回计数 0..4 */
static int q_ok = 1;           /* 当前质量判定 */
static float p95_smooth = 0;   /* 状态判定用平滑 p95 */
static float baseline = 1860;
static int snap_cnt = 0;
static float d_prev2 = 0, d_prev = 0;
static int prev_slew = 0, prev_clip = 0, run_prev = 0;
static int64_t t_prev2_us = 0, t_prev_us = 0;
static int64_t last_peak_us = 0;
static int64_t peak_times[BPM_MED_N * 3]; /* 最近N个峰的时刻 */
static int n_peaks = 0;

/* 隔峰间隔缓冲 */
static int intervals[BPM_MED_N];
static int n_iv = 0;
static int reject_run = 0;

/* p95 窗口 */
static float p95_buf[P95_WIN_N];
static int p95_n = 0, p95_idx = 0;

/* 波形流: 1kHz 抽 10 得 100Hz, 10点/包 = 每100ms一包 */
#define WAVE_DEC        10
#define WAVE_PKT_N      10
static int16_t wave_pkt[WAVE_PKT_N];
static int wave_pkt_n = 0;
static int wave_dec = 0;

/* 心跳闪烁 */
static int beat_flash = 0;
static int64_t last_beat_flash_us = 0;

static int cmp_int(const void *a, const void *b) { return *(const int*)a - *(const int*)b; }
static float get_p95(void);  /* 前向声明 */
static float get_p50(void);

/* ================= 心率跟踪器（匀速卡尔曼 + 峰配对 + 伪迹门） ================= */
typedef struct {
    int init;
    float hr, v;
    float p00, p01, p11;
    int rejects;
    float amp[5]; int amp_n, amp_i;
    int art_cnt;
} hrtrk_t;
static hrtrk_t trk;
static int64_t last_beat_us = 0;
static int have_beat = 0;

static void kf_init(float hr)
{
    trk.init = 1;
    trk.hr = hr; trk.v = 0.0f;
    trk.p00 = 400.0f; trk.p01 = 0.0f; trk.p11 = 4.0f;
    trk.rejects = 0;
    trk.amp_n = 0; trk.amp_i = 0; trk.art_cnt = 0;
}

static void kf_predict(float dt)
{
    trk.hr += trk.v * dt;
    float p00 = trk.p00 + dt * (2.0f * trk.p01 + dt * trk.p11);
    float p01 = trk.p01 + dt * trk.p11;
    float p11 = trk.p11;
    float sa2 = KF_SIGMA_A * KF_SIGMA_A;
    trk.p00 = p00 + sa2 * dt * dt * dt * dt / 4.0f;
    trk.p01 = p01 + sa2 * dt * dt * dt / 2.0f;
    trk.p11 = p11 + sa2 * dt * dt;
}

static void kf_update(float z, float r)
{
    float s = trk.p00 + r;
    if (s < 1e-6f) s = 1e-6f;
    float k0 = trk.p00 / s, k1 = trk.p01 / s;
    float innov = z - trk.hr;
    trk.hr += k0 * innov;
    trk.v  += k1 * innov;
    float p00 = (1.0f - k0) * trk.p00;
    float p01 = (1.0f - k0) * trk.p01;
    float p11 = trk.p11 - k1 * trk.p01;
    trk.p00 = p00; trk.p01 = p01; trk.p11 = p11;
    if (trk.v >  V_MAX) trk.v =  V_MAX;
    if (trk.v < -V_MAX) trk.v = -V_MAX;
    if (trk.hr > 210.0f) trk.hr = 210.0f;
    if (trk.hr <  35.0f) trk.hr =  35.0f;
}

static float amp_med(void)
{
    if (trk.amp_n == 0) return 0.0f;
    float t[5]; int n = trk.amp_n;
    for (int i = 0; i < n; i++) t[i] = trk.amp[i];
    for (int i = 0; i < n - 1; i++)
        for (int j = i + 1; j < n; j++)
            if (t[j] < t[i]) { float x = t[i]; t[i] = t[j]; t[j] = x; }
    return t[n / 2];
}

static void amp_push(float a)
{
    trk.amp[trk.amp_i] = a;
    trk.amp_i = (trk.amp_i + 1) % 5;
    if (trk.amp_n < 5) trk.amp_n++;
}

/* 候选峰 → 拍：L1饱和/L2陡度/L3窄冲激/L4幅度一致性 → 配对 → 卡尔曼 */
static void beat_candidate(int64_t t_us, float amp, int slew, int clip, int width)
{
    if (clip)                    { trk.art_cnt++; return; }
    if (slew > SLEW_MAX)         { trk.art_cnt++; return; }
    float med = amp_med();
    if (med > 1.0f && (amp > AMP_RATIO * med || amp * AMP_RATIO < med)) { trk.art_cnt++; return; }
    if (width <= 1 && med > 1.0f && amp > 1.5f * med) { trk.art_cnt++; return; }
    trk.art_cnt = 0;

    if (!have_beat) { have_beat = 1; last_beat_us = t_us; amp_push(amp); return; }

    float d = (float)(t_us - last_beat_us) / 1000.0f;
    if (!trk.init) {
        if (d >= IV_MIN_MS && d <= IV_MAX_MS) { kf_init(60000.0f / d); last_beat_us = t_us; amp_push(amp); }
        else if (d > IV_MAX_MS) last_beat_us = t_us;
        return;
    }
    float period = 60000.0f / trk.hr;
    if (d < PAIR_LO * period) return;                                  /* 重搏波：基准不动 */
    if (d > PAIR_HI * period) { last_beat_us = t_us; amp_push(amp); return; }  /* 漏拍 */
    float z = 60000.0f / d;
    if (z < 35.0f || z > 210.0f) return;
    float dt = d / 1000.0f;
    kf_predict(dt);
    float r = (trk.hr * KF_SIGMA_T / 60.0f);
    r = r * r + 1.0f;
    float S = trk.p00 + r;
    if (fabsf(z - trk.hr) > KF_GATE * sqrtf(S)) {
        trk.rejects++;
        if (trk.rejects >= 5) kf_init(z);               /* F1: 连续离群 → 重置 */
        last_beat_us = t_us;
        return;
    }
    trk.rejects = 0;
    kf_update(z, r);
    last_beat_us = t_us;
    amp_push(amp);
}

/* 每个窗口调用一次: t_us=当前时刻, dev=整流偏差 */
static void census_feed(int64_t t_us, float dev, int slew, int clip)
{
    /* p95 */
    p95_buf[p95_idx] = dev;
    p95_idx = (p95_idx + 1) % P95_WIN_N;
    if (p95_n < P95_WIN_N) p95_n++;

    int run_now = (dev > PEAK_THRESH) ? (run_prev + 1) : 0;

    /* 峰检测: 3点局部极大 → 交给跟踪器做配对与伪迹判定 */
    if (d_prev > cfg_peak_thr && d_prev >= dev && d_prev >= d_prev2) {
        if (t_prev_us - last_peak_us >= (int64_t)cfg_peak_gap_ms * 1000LL) {
            last_peak_us = t_prev_us;
#if USE_TRACKER == 1
            int64_t before = last_beat_us;
            beat_candidate(t_prev_us, d_prev, prev_slew, prev_clip, run_prev);
            if (last_beat_us != before) { beat_flash = 1; last_beat_flash_us = t_us; }
#else
            /* ---- 老方法（已验证）：记录峰 → 隔峰 i+2 → 合理性过滤 ---- */
            beat_flash = 1;
            last_beat_flash_us = t_us;
            if (q_ok) led_fx_beat();   /* 质量不合格的噪声峰不驱动灯带 */
            if (n_peaks < BPM_MED_N * 3) {
                peak_times[n_peaks++] = t_prev_us;
            } else {
                memmove(peak_times, peak_times + 1, (BPM_MED_N * 3 - 1) * sizeof(int64_t));
                peak_times[BPM_MED_N * 3 - 1] = t_prev_us;
            }
            if (n_peaks >= 3) {
                int iv_ms = (int)((peak_times[n_peaks-1] - peak_times[n_peaks-3]) / 1000);
                if (iv_ms >= IV_MIN_MS && iv_ms <= IV_MAX_MS) {
                    int accept = 1;
                    if (n_iv >= 3) {
                        int tmp2[BPM_MED_N];
                        memcpy(tmp2, intervals + (BPM_MED_N - n_iv), n_iv * sizeof(int));
                        qsort(tmp2, n_iv, sizeof(int), cmp_int);
                        int med = tmp2[n_iv / 2];
                        if (iv_ms > med * 13 / 10 || iv_ms * 13 / 10 < med) accept = 0;
                    }
                    if (accept) {
                        reject_run = 0;
                        if (n_iv < BPM_MED_N) n_iv++;
                        memmove(intervals, intervals + 1, (BPM_MED_N - 1) * sizeof(int));
                        intervals[BPM_MED_N - 1] = iv_ms;
                    } else if (++reject_run >= 4) {
                        n_iv = 0;
                        reject_run = 0;
                    }
                }
            }
#endif
        }
    }

    d_prev2 = d_prev;
    d_prev = dev;
    t_prev2_us = t_prev_us;
    t_prev_us = t_us;
    prev_slew = slew;
    prev_clip = clip;
    run_prev = run_now;
}

static int warm_cnt = 0;   /* 连续通过校验的帧数（冷启动保护） */

static float get_iv_cv(void)
{
    if (n_iv < 3) return 99.0f;
    float sum = 0.0f;
    for (int i = 0; i < n_iv; i++) sum += intervals[BPM_MED_N - n_iv + i];
    float mean = sum / n_iv;
    float var = 0.0f;
    for (int i = 0; i < n_iv; i++) {
        float d = intervals[BPM_MED_N - n_iv + i] - mean;
        var += d * d;
    }
    var /= n_iv;
    return (mean > 1.0f) ? sqrtf(var) / mean : 99.0f;
}

static int get_bpm(void)
{
    int64_t now = esp_timer_get_time();
#if USE_TRACKER == 1
    if (have_beat && now - last_beat_us > 2500000LL) { have_beat = 0; trk.init = 0; }
    if (!q_ok) return 0;
    if (!trk.init) return 0;
    if (trk.art_cnt >= 3) return 0;
    return (int)(trk.hr + 0.5f);
#else
    /* ---- 老方法（已验证）：双条件归零 + 质量门 + 隔峰中值 ---- */
    float p95 = get_p95();
    if ((p95 < 40 && now - last_peak_us > 1500000LL) ||
        (now - last_peak_us > 2500000LL)) {
        n_iv = 0; n_peaks = 0;
    }
    if (get_p50() < 15 && now - last_peak_us > 1000000LL) n_iv = 0;
    if (!q_ok) { warm_cnt = 0; return 0; }
    if (n_iv < g_n_iv_min) { warm_cnt = 0; return 0; }
    /* 间隔规律性校验（CV）：真实脉搏 CV<0.05，噪声触发 CV>0.15
       实测：★历史最佳=0.02，弱耦合噪声=0.17 */
    float sum = 0.0f;
    for (int i = 0; i < n_iv; i++) sum += intervals[BPM_MED_N - n_iv + i];
    float mean = sum / n_iv;
    float var = 0.0f;
    for (int i = 0; i < n_iv; i++) {
        float d = intervals[BPM_MED_N - n_iv + i] - mean;
        var += d * d;
    }
    var /= n_iv;
    float cv = (mean > 1.0f) ? sqrtf(var) / mean : 99.0f;
    if (cv > g_cv_max) { warm_cnt = 0; return 0; }   /* 间隔不规律 → 噪声触发 */
    /* 冷启动保护：连续 4 帧（2 秒）通过校验才出数，避免重启瞬态假值 */
    if (warm_cnt < g_warm_min) { warm_cnt++; return 0; }

    int tmp[BPM_MED_N];
    memcpy(tmp, intervals + (BPM_MED_N - n_iv), n_iv * sizeof(int));
    qsort(tmp, n_iv, sizeof(int), cmp_int);
    return 60000 / tmp[n_iv / 2];
#endif
}

static float get_p95(void)
{
    if (p95_n < 100) return 0;
    /* 采样法近似p95: 取200个样本排序 */
    float s[200];
    int step = p95_n / 200; if (step < 1) step = 1;
    int n = 0;
    for (int i = 0; i < p95_n && n < 200; i += step) {
        int idx = (p95_idx - 1 - i + P95_WIN_N * 2) % P95_WIN_N;
        s[n++] = p95_buf[idx];
    }
    /* 简单排序 */
    for (int i = 0; i < n - 1; i++)
        for (int j = i + 1; j < n; j++)
            if (s[j] < s[i]) { float t = s[i]; s[i] = s[j]; s[j] = t; }
    return s[(int)(n * 0.95)];
}

static float get_p50(void)
{
    if (p95_n < 100) return 0;
    int step = p95_n / 200; if (step < 1) step = 1;
    float s[200]; int n = 0;
    for (int i = 0; i < p95_n && n < 200; i += step) {
        int idx = (p95_idx - 1 - i + P95_WIN_N * 2) % P95_WIN_N;
        s[n++] = p95_buf[idx];
    }
    for (int i = 0; i < n - 1; i++)
        for (int j = i + 1; j < n; j++)
            if (s[j] < s[i]) { float t = s[i]; s[i] = s[j]; s[j] = t; }
    return s[n / 2];
}

/* 信号质量门：只有 p95>=45 且 p50>=20 才认为有真实脉动能量。
 * 依据: 悬空(噪声尖峰) p50~12/p95~35；贴肤好耦合 p50 42~62/p95 114~221。
 * 加入后悬空 120s 假 BPM 从 118s 降到 0s，好耦合 BPM 不变。 */
/* 质量判定（带滞回：合格计数 0~4，>=2 判好，约 ±1s 抗抖）
 * 只影响"输出"，不影响峰值检测——否则短暂掉线会打断间隔链，BPM 变空/算错。 */
static void quality_update(void)
{
    float p95 = get_p95(), p50 = get_p50();
    /* 补发突发期间射频密（20批/s），压电高阻节点被抬底 → 临时收紧 p50 门槛 */
    float p50_gate = cfg_p50_gate + (replay_pending ? 12.0f : 0.0f);
    int ok = (p95 >= cfg_p95_gate && p50 >= p50_gate);
    if (ok) { if (q_cnt < 4) q_cnt++; }
    else    { if (q_cnt > 0) q_cnt--; }
    q_ok = (q_cnt >= 2);
}

/* 状态判定用平滑 p95（τ≈2s @500ms 帧），避免在阈值附近反复跳 GOOD/WEAK */
static void p95_smooth_update(float p95)
{
    p95_smooth = (p95_smooth <= 0.0f) ? p95 : p95_smooth + 0.25f * (p95 - p95_smooth);
}

static const char* get_state(void)
{
    float p95 = (p95_smooth > 0.0f) ? p95_smooth : get_p95();
    float p50 = get_p50();
    /* 质量优先：q_ok 已经(带滞回)判定 p95>=45 且 p50>=18，
       幅度下降不再二次降级，避免稳定按压时 GOOD/WEAK 反复跳 */
    if (q_ok) {
        if (baseline >= 2600 && p95 < 55) return "OVER";
        if (get_bpm() == 0) return "SRCH";
        return "GOOD";
    }
    if (p50 < 15 && p95 >= 35) return "VIB";   /* 悬空振荡 */
    if (p95 < 38) return "IDLE";
    return "WEAK";                              /* 有信号但质量不足 */
}


/* ---------- OLED 显存回读（调试）：每5秒打印 128x32 2x2降采样 + CRC ---------- */
static void dump_fb(const ssd1306_t *s)
{
    uint32_t crc = 0xFFFFFFFF;
    for (int i = 0; i < 128 * 4; i++) {
        crc ^= s->fb[i];
        for (int b = 0; b < 8; b++) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    printf("FB0|\n");
    char line[65];
    for (int y = 0; y < 32; y += 2) {
        for (int x = 0; x < 128; x += 2) {
            int on = 0;
            for (int dy = 0; dy < 2 && !on; dy++)
                for (int dx = 0; dx < 2; dx++)
                    if (s->fb[((y + dy) >> 3) * 128 + (x + dx)] & (1 << ((y + dy) & 7))) { on = 1; break; }
            line[x / 2] = on ? '#' : '.';
        }
        line[64] = 0;
        printf("%s\n", line);
    }
    printf("FB1|crc=%08x\n", (unsigned)crc);
}

/* BLE 状态灯：空心圆=未就绪 / 闪烁=等待连接 / 实心=已连接 */
static void draw_status_dot(ssd1306_t *s, int cx, int cy, int r, int fill)
{
    for (int dy = -r; dy <= r; dy++) {
        for (int dx = -r; dx <= r; dx++) {
            int d2 = dx * dx + dy * dy;
            if (d2 <= r * r) {
                if (fill || d2 > (r - 1) * (r - 1))
                    ssd1306_px(s, cx + dx, cy + dy, 1);
            }
        }
    }
}



/* ================= 模板匹配影子通道（性能考察 + 一致性对照） ================= */
#define TRK_N       256
#define TRK_BUF     1024
static float tmpl_base[TRK_N];
static float trk_buf[TRK_BUF];
static int   trk_head = 0, trk_cnt = 0;
static float trk_hr = 0, trk_v = 0, trk_p00 = 0, trk_p01 = 0, trk_p11 = 0;
static int   trk_init = 0;
static uint32_t trk_cost_us = 0;
static float trk_score = 0;
static float trk_r = 0, trk_sa = 0;
static int   trk_out = 0;

static void tmpl_init(void)
{
    float sum = 0.0f;
    for (int i = 0; i < TRK_N; i++) {
        float x = (float)i / TRK_N;
        float a = expf(-(x - 0.14f) * (x - 0.14f) / (2 * 0.055f * 0.055f));
        float b = 0.42f * expf(-(x - 0.42f) * (x - 0.42f) / (2 * 0.075f * 0.075f));
        float c = 0.10f * expf(-fmaxf(0.0f, x - 0.45f) / 0.22f);
        tmpl_base[i] = a + b + c;
        sum += tmpl_base[i];
    }
    float mean = sum / TRK_N, e = 0.0f;
    for (int i = 0; i < TRK_N; i++) { tmpl_base[i] -= mean; e += tmpl_base[i] * tmpl_base[i]; }
    e = sqrtf(e);
    for (int i = 0; i < TRK_N; i++) tmpl_base[i] /= e;
}

static void trk_push(float dev)
{
    trk_buf[trk_head] = dev;
    trk_head = (trk_head + 1) % TRK_BUF;
    if (trk_cnt < TRK_BUF) trk_cnt++;
}

/* 最近 m 个窗口与模板（重采样到 m）的归一化互相关 */
static float trk_ncc(int m)
{
    if (m < 32 || trk_cnt < m + 2) return -2.0f;
    float wsum = 0.0f;
    for (int k = 0; k < m; k++) {
        int idx = (trk_head - m + k + TRK_BUF * 2) % TRK_BUF;
        wsum += trk_buf[idx];
    }
    float wmean = wsum / m;
    float we = 0.0f, te = 0.0f, dot = 0.0f;
    for (int k = 0; k < m; k++) {
        int idx = (trk_head - m + k + TRK_BUF * 2) % TRK_BUF;
        float w = trk_buf[idx] - wmean;
        float t = tmpl_base[(int)((float)k * TRK_N / m) % TRK_N];
        we += w * w; te += t * t; dot += w * t;
    }
    if (we < 1e-6f || te < 1e-6f) return -2.0f;
    return dot / (sqrtf(we) * sqrtf(te));
}

static void trk_kf(float z, float r, float dt, float sa)
{
    trk_hr += trk_v * dt;
    float p00 = trk_p00 + dt * (2 * trk_p01 + dt * trk_p11);
    float p01 = trk_p01 + dt * trk_p11;
    float sa2 = sa * sa;                    /* 模式自适应过程噪声 */
    trk_p00 = p00 + sa2 * dt * dt * dt * dt / 4.0f;
    trk_p01 = p01 + sa2 * dt * dt * dt / 2.0f;
    trk_p11 = trk_p11 + sa2 * dt * dt;
    float S = trk_p00 + r;
    if (S < 1e-6f) S = 1e-6f;
    float k0 = trk_p00 / S, k1 = trk_p01 / S, inn = z - trk_hr;
    trk_hr += k0 * inn; trk_v += k1 * inn;
    float n00 = (1 - k0) * trk_p00, n01 = (1 - k0) * trk_p01;
    trk_p11 = trk_p11 - k1 * trk_p01;
    trk_p00 = n00; trk_p01 = n01;
    if (trk_v > 10.0f) trk_v = 10.0f;
    if (trk_v < -10.0f) trk_v = -10.0f;
    if (trk_hr > 210.0f) trk_hr = 210.0f;
    if (trk_hr < 35.0f) trk_hr = 35.0f;
}

/* 每 500ms 调一次：在中心心率 ±45% 内做模板搜索 */
static int trk_step(float center_hr)
{
    int64_t t0 = esp_timer_get_time();
    if (!trk_init) { tmpl_init(); trk_init = 1; }
    if (center_hr < 40.0f) center_hr = 80.0f;

    float best_hr = 0.0f, best_sc = -2.0f;
    const int N = 11;
    for (int i = 0; i < N; i++) {
        float hr = center_hr * (0.55f + 0.90f * i / (N - 1));
        if (hr < 35.0f || hr > 210.0f) continue;
        int m = (int)(60.0f / hr * 200.0f);
        float sc = trk_ncc(m);
        if (sc > best_sc) { best_sc = sc; best_hr = hr; }
    }
    trk_score = best_sc;

    if (best_sc > 0.55f) {
        if (trk_hr <= 0.0f) {
            trk_hr = best_hr; trk_v = 0.0f;
            trk_p00 = 400.0f; trk_p01 = 0.0f; trk_p11 = 4.0f;
        } else {
            /* R 随信号质量变化（SQI）：形态越差、耦合越弱，测量越不可信 */
            float q_p95 = get_p95() / 120.0f;              /* 归一化耦合强度 */
            if (q_p95 > 1.0f) q_p95 = 1.0f;
            float r_wave = (trk_hr * 0.02f / 60.0f);
            r_wave = r_wave * r_wave + 4.0f;
            trk_r = r_wave + 25.0f * (1.0f - best_sc) * (1.0f - best_sc)
                            + 12.0f * (1.0f - q_p95) * (1.0f - q_p95);
            /* Q 随速度变化（无 IMU 时用自身速度当模式代理）：
               静息 |v|→0 → sa=1.5；运动 |v|≥5 BPM/s → sa=4.0 */
            float vn = fabsf(trk_v) / 5.0f; if (vn > 1.0f) vn = 1.0f;
            trk_sa = 1.5f + 2.5f * vn;
            trk_kf(best_hr, trk_r, 0.5f, trk_sa);
        }
        trk_out = (int)(trk_hr + 0.5f);
    } else {
        trk_out = 0;                       /* 形态不匹配 → 本轮不出数 */
    }
    trk_cost_us = (uint32_t)(esp_timer_get_time() - t0);
    return trk_out;
}


/* ---- OLED 渲染任务（与采样主循环解耦） ---- */
static ssd1306_t g_oled;
static int       g_oled_ok = 0;
static volatile int g_oled_fail = 0;
static int64_t   g_t0_us = 0;
static int64_t   g_last_ui_us = 0;
static int64_t   g_last_dump_us = 0;

static void oled_task(void *arg)
{
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(500));
        if (!g_oled_ok) continue;
        int64_t now_us = esp_timer_get_time();
        char line[16];
        g_last_ui_us = now_us;
        float p95 = get_p95();
        p95_smooth_update(p95);
        quality_update();
        int bpm = get_bpm();
        if (bpm > 0) led_fx_set_bpm((float)bpm);
        const char *state = get_state();
        /* 闪烁衰减 */
        if (beat_flash && now_us - last_beat_flash_us > 300000) beat_flash = 0;

        ssd1306_clear(&g_oled);

        /* --- 左侧 88px: 状态信息 --- */
        /* Row0: 标题 + 心跳指示 */
        ssd1306_text(&g_oled, beat_flash ? ">> PULSE <<" : "   PULSE  ", 0, 0);

        /* Row1: 佩戴状态 */
        snprintf(line, sizeof(line), "%s", state);
        ssd1306_text(&g_oled, line, 0, 1);

        /* Row2: p95 + BPM原始 */
        snprintf(line, sizeof(line), "p95=%.0f", p95);
        ssd1306_text(&g_oled, line, 0, 2);

        /* BLE 状态灯 (cx=80,cy=11,r=4)：实心=已连接，闪=等待，空心=未就绪 */
        int dot_fill;
        if (!ble_ready) dot_fill = 0;
        else if (conn_handle == BLE_HS_CONN_HANDLE_NONE) dot_fill = (int)((now_us / 500000) & 1);
        else dot_fill = 1;
        draw_status_dot(&g_oled, 80, 11, 4, dot_fill);

        /* Row3: 信号条 (8px高度) */
        float bar_ratio = p95 / 200.0f; if (bar_ratio > 1) bar_ratio = 1;
        ssd1306_bar(&g_oled, 0, 24, 88, 8, bar_ratio);

        /* --- 右侧 40px: 大号BPM --- */
        if (bpm > 0) {
                int d1 = bpm / 100;
                int d2 = (bpm / 10) % 10;
                int d3 = bpm % 10;
                ssd1306_bignum_scaled(&g_oled, d1, 92, 0, 4);
                ssd1306_bignum_scaled(&g_oled, d2, 105, 0, 4);
                ssd1306_bignum_scaled(&g_oled, d3, 118, 0, 4);
                ssd1306_text(&g_oled, "BPM", 98, 3);
        } else {
                ssd1306_text(&g_oled, "---", 98, 1);
                ssd1306_text(&g_oled, "BPM", 98, 2);
        }

        int flush_rc = ssd1306_flush(&g_oled);
        if (flush_rc != 0) g_oled_fail++;

        #if USE_TRACKER == 2
        if (cfg_tracker_mode == 2) {
                int nb = trk_step((float)bpm);
                if (cfg_dbg_trk) printf("TRK|old=%d new=%d sc=%.2f R=%.0f sa=%.1f cost=%uus heap=%u\n",
                       bpm, nb, trk_score, trk_r, trk_sa,
                       (unsigned)trk_cost_us, (unsigned)esp_get_free_heap_size());
        }
        #endif

        if (cfg_dbg_ui) printf("UI|bpm=%d cv=%.3f conn=%d state=%s p95=%.0f p50=%.0f q=%d beat=%d flush=%d\n",
                   bpm, get_iv_cv(), (int)conn_handle, state, p95, get_p50(), q_ok, beat_flash, flush_rc);
        if (cfg_dbg_dump && now_us - g_last_dump_us > 5000000) {
                g_last_dump_us = now_us;
                dump_fb(&g_oled);
        }

        /* BLE推送JSON通知 */
        char json[160];
        snprintf(json, sizeof(json),
                     "{\"bpm\":%d,\"bpm2\":%d,\"sc\":%.2f,\"state\":\"%s\",\"p95\":%.0f,\"p50\":%.0f,\"q\":%d,\"beat\":%d,\"t\":%lld}",
                     bpm, trk_out, trk_score, state, p95, get_p50(), q_ok, beat_flash,
                     (long long)(esp_timer_get_time() / 1000));
        ble_notify(json);

    }
}

void app_main(void)
{
    /* NVS：配置持久化 */
    esp_err_t nvs_rc = nvs_flash_init();
    if (nvs_rc == ESP_ERR_NVS_NO_FREE_PAGES || nvs_rc == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_rc = nvs_flash_init();
    }
    cfg_nvs_ok = (nvs_rc == ESP_OK && nvs_open("pulsecfg", NVS_READWRITE, &cfg_nvs) == ESP_OK);
    cfg_load();
    apply_cons();
    xTaskCreate(serial_cmd_task, "ser_cmd", 3072, NULL, 3, NULL);

    gpio_config_t io = { .pin_bit_mask = 1ULL << GPIO_NUM_0, .mode = GPIO_MODE_INPUT };
    gpio_config(&io);
    gpio_config_t btn = { .pin_bit_mask = 1ULL << BTN_GPIO, .mode = GPIO_MODE_INPUT, .pull_up_en = GPIO_PULLUP_ENABLE };
    gpio_config(&btn);
    ble_init();

    /* ---------- I2C + OLED ---------- */
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = 0, .sda_io_num = I2C_SDA, .scl_io_num = I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT, .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    i2c_master_bus_handle_t bus = NULL;
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &bus));
    i2c_device_config_t oled_cfg = { .dev_addr_length = I2C_ADDR_BIT_LEN_7,
                                     .device_address = 0x3C, .scl_speed_hz = 400000 };
    i2c_master_dev_handle_t oled_dev = NULL;
    ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &oled_cfg, &oled_dev));
    g_oled_ok = (ssd1306_init(&g_oled, oled_dev, OLED_HEIGHT) == 0);
    ESP_LOGI(TAG, "OLED: %s", g_oled_ok ? "OK" : "FAIL");

    xTaskCreate(oled_task, "oled", 4096, NULL, 2, NULL);
    led_fx_init(5, 16);
    led_fx_set_level(cfg_led_level);
    led_fx_set_mode(cfg_led_mode);
    led_fx_set_params(cfg_rot_idle / 1000.0f, cfg_rot_max / 1000.0f,
                      cfg_hue_idle / 1000.0f, cfg_hue_span / 1000.0f,
                      cfg_p_base / 1000.0f, cfg_p_peak / 1000.0f,
                      cfg_b_gate / 1000.0f, cfg_decay / 1000.0f);

    /* ---------- ADC DMA ---------- */
    adc_continuous_handle_t adc = NULL;
    adc_continuous_handle_cfg_t hdl_cfg = { .max_store_buf_size = STORE_BUF_SIZE, .conv_frame_size = FRAME_SIZE };
    ESP_ERROR_CHECK(adc_continuous_new_handle(&hdl_cfg, &adc));
    adc_digi_pattern_config_t pattern = { .atten = ADC_ATTEN_DB_12, .channel = ADC_CHANNEL,
                                          .unit = ADC_UNIT_1, .bit_width = 12 };
    adc_continuous_config_t dig_cfg = { .pattern_num = 1, .adc_pattern = &pattern,
                                        .sample_freq_hz = SAMPLE_FREQ_HZ,
                                        .conv_mode = ADC_CONV_SINGLE_UNIT_1,
                                        .format = ADC_DIGI_OUTPUT_FORMAT_TYPE2 };
    ESP_ERROR_CHECK(adc_continuous_config(adc, &dig_cfg));
    ESP_ERROR_CHECK(adc_continuous_start(adc));
    gpio_set_pull_mode(GPIO_NUM_0, GPIO_PULLUP_PULLDOWN);

    uint8_t *buf = malloc(READ_BUF_SIZE);
    int win_min = 4095, win_max = 0, win_n = 0;
    int win_slew = 0, win_clip = 0, prev_raw = -1;
    uint32_t seq = 0;
    g_t0_us = esp_timer_get_time();
    int64_t last_loop_us = esp_timer_get_time();
    int64_t max_lag_us = 0;
    int64_t last_lag_report_us = 0;

    while (1) {
        uint32_t out_length = 0;
        if (adc_continuous_read(adc, buf, READ_BUF_SIZE, &out_length, 10) != ESP_OK || !out_length)
            out_length = 0;
        for (uint32_t i = 0; i + SOC_ADC_DIGI_RESULT_BYTES <= out_length;
             i += SOC_ADC_DIGI_RESULT_BYTES) {
            adc_digi_output_data_t *p = (adc_digi_output_data_t *)&buf[i];
            int raw = p->type2.data;
            if (prev_raw >= 0) {
                int dsl = raw - prev_raw; if (dsl < 0) dsl = -dsl;
                if (dsl > win_slew) win_slew = dsl;
            }
            prev_raw = raw;
            if (raw <= 4 || raw >= 4091) win_clip = 1;
            if (++wave_dec >= WAVE_DEC) {
                wave_dec = 0;
                wave_cache[wave_cache_head] = (int16_t)raw;
                wave_cache_head = (wave_cache_head + 1) % WAVE_CACHE_N;
                if (wave_cache_cnt < WAVE_CACHE_N) wave_cache_cnt++;
                wave_cache_last_us = esp_timer_get_time();
                wave_pkt[wave_pkt_n++] = (int16_t)raw;
                if (wave_pkt_n >= WAVE_PKT_N) {
                    if (cfg_wave_tx) ble_notify_wave(wave_pkt, wave_pkt_n);
                    wave_pkt_n = 0;
                }
            }
            if (raw < win_min) win_min = raw;
            if (raw > win_max) win_max = raw;
            if (++win_n >= WIN_SAMPLES) {
                if (cfg_raw_print)
                    printf("R,%lu,%d,%d\n", (unsigned long)seq, win_min, win_max);
                seq++;   /* 序号始终递增，作为时基 */
                /* ---- 嵌入式峰普查 ---- */
                /* 时基用采样序号（5ms/窗口），不受主循环卡顿影响 */
                int64_t now_us = (int64_t)seq * 5000LL;
                float mid = (win_min + win_max) / 2.0f;
                baseline += 0.005 / BASELINE_TAU_MS * 1000.0f * (mid - baseline);
                if (fabsf(mid - baseline) > SNAP_THRESH) {
                    if (++snap_cnt >= SNAP_CNT_N) { baseline = mid; snap_cnt = 0; }
                } else snap_cnt = 0;
                float dev = fmaxf(fabsf(win_max - baseline), fabsf(win_min - baseline));
                census_feed(now_us, dev, win_slew, win_clip);
#if USE_TRACKER == 2
                trk_push(dev);
#endif
                win_min = 4095; win_max = 0; win_n = 0;
                win_slew = 0; win_clip = 0;
            }
        }

        /* ---- 主循环滞后监测 ---- */
        int64_t now_us = esp_timer_get_time();
        int64_t lag = now_us - last_loop_us;
        last_loop_us = now_us;
        if (lag > max_lag_us) max_lag_us = lag;
        if (now_us - last_lag_report_us > 5000000) {
            ESP_LOGI(TAG, "loop lag max=%.1fms oled_fail=%d heap=%u",
                     max_lag_us / 1000.0, g_oled_fail, (unsigned)esp_get_free_heap_size());
            max_lag_us = 0;
            last_lag_report_us = now_us;
        }
    }
}
