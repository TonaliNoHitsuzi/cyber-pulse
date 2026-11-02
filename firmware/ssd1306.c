/* SSD1306 I2C OLED 驱动实现 */
#include "ssd1306.h"
#include "font8x8_basic.h"
#include <string.h>
#include "esp_log.h"

static const char *TAG = "ssd1306";

#define CMD   0x00
#define DATA  0x40

static int wr(ssd1306_t *s, const unsigned char *buf, int len)
{
    return i2c_master_transmit(s->dev, buf, len, 100) == ESP_OK ? 0 : -1;
}

int ssd1306_init(ssd1306_t *s, i2c_master_dev_handle_t dev, int height)
{
    memset(s, 0, sizeof(*s));
    s->dev = dev;
    s->height = (height == 32) ? 32 : 64;

    unsigned char init_seq[] = {
        0xAE,                   // display off
        0xD5, 0x80,             // clock div
        0xA8, (height == 32) ? 0x1F : 0x3F,  // multiplex
        0xD3, 0x00,             // display offset
        0x40,                   // start line 0
        0x8D, 0x14,             // charge pump on
        0x20, 0x00,             // 水平寻址模式
        0xA1, 0xC8,             // segment/remap 反相(安装方向)
        0xDA, (height == 32) ? 0x02 : 0x12,  // COM pins
        0x81, 0xCF,             // contrast
        0xD9, 0xF1,             // pre-charge
        0xDB, 0x40,             // VCOM
        0xA4, 0xA6,             // 正常显示
        0xAF,                   // display on
    };
    unsigned char buf[32];
    buf[0] = CMD;
    memcpy(buf + 1, init_seq, sizeof(init_seq));
    if (wr(s, buf, sizeof(init_seq) + 1) != 0) {
        ESP_LOGE(TAG, "I2C写入失败");
        return -1;
    }
    ssd1306_clear(s);
    ssd1306_flush(s);
    return 0;
}

void ssd1306_clear(ssd1306_t *s)
{
    memset(s->fb, 0, sizeof(s->fb));
}

void ssd1306_px(ssd1306_t *s, int x, int y, int on)
{
    if (x < 0 || x >= 128 || y < 0 || y >= s->height) return;
    int page = y / 8;
    if (on) s->fb[page * 128 + x] |= (1 << (y % 8));
    else    s->fb[page * 128 + x] &= ~(1 << (y % 8));
}

int ssd1306_text(ssd1306_t *s, const char *str, int x, int row)
{
    int cx = x;
    for (; *str; str++) {
        unsigned char c = (unsigned char)*str;
        if (c < 32 || c > 127) c = '?';
        const unsigned char *glyph = font8x8_basic[c - 32];
        for (int col = 0; col < 8; col++) {
            unsigned char bits = glyph[col];
            if (cx + col >= 128) break;
            s->fb[row * 128 + cx + col] = bits;
        }
        cx += 8;
    }
    return cx - x;
}

void ssd1306_bar(ssd1306_t *s, int x, int y, int w, int h, float ratio)
{
    if (ratio < 0) ratio = 0;
    if (ratio > 1) ratio = 1;
    int fill = (int)(w * ratio);
    for (int yy = 0; yy < h; yy++)
        for (int xx = 0; xx < w; xx++)
            ssd1306_px(s, x + xx, y + yy, (xx < fill) ? 1 : ((xx == fill || yy == 0 || yy == h - 1 || xx == w - 1) ? 1 : 0));
}

/* 3x5点阵数字×8放大 = 24x40 */
static const char bigdigits[10][5] = {
    {0x07,0x05,0x05,0x05,0x07}, // 0
    {0x02,0x06,0x02,0x02,0x07}, // 1
    {0x07,0x01,0x07,0x04,0x07}, // 2
    {0x07,0x01,0x07,0x01,0x07}, // 3
    {0x05,0x05,0x07,0x01,0x01}, // 4
    {0x07,0x04,0x07,0x01,0x07}, // 5
    {0x07,0x04,0x07,0x05,0x07}, // 6
    {0x07,0x01,0x01,0x01,0x01}, // 7
    {0x07,0x05,0x07,0x05,0x07}, // 8
    {0x07,0x05,0x07,0x01,0x07}, // 9
};

void ssd1306_bignum_scaled(ssd1306_t *s, int digit, int x, int y, int scale)
{
    if (digit < 0 || digit > 9) return;
    for (int r = 0; r < 5; r++)
        for (int c = 0; c < 3; c++)
            if (bigdigits[digit][r] & (4 >> c))
                for (int a = 0; a < scale; a++)
                    for (int b = 0; b < scale; b++)
                        ssd1306_px(s, x + c * scale + b, y + r * scale + a, 1);
}

int ssd1306_flush(ssd1306_t *s)
{
    int pages = s->height / 8;
    unsigned char buf[130];
    for (int page = 0; page < pages; page++) {
        buf[0] = CMD; buf[1] = 0xB0 | page;    // 页地址
        buf[2] = CMD; buf[3] = 0x00;           // 列低
        buf[4] = CMD; buf[5] = 0x10;           // 列高
        if (wr(s, buf, 6) != 0) return -1;
        buf[0] = DATA;
        memcpy(buf + 1, s->fb + page * 128, 128);
        if (wr(s, buf, 129) != 0) return -1;
    }
    return 0;
}
