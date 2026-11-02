/* SSD1306 I2C OLED 驱动 (128x64 / 128x32) — 手写版，仅依赖 i2c_master API */
#ifndef SSD1306_H
#define SSD1306_H
#include "driver/i2c_master.h"

typedef struct {
    i2c_master_dev_handle_t dev;
    unsigned char fb[128 * 8];    /* 页式帧缓冲：128列×8页(64行)。128x32用前4页 */
    int height;                   /* 64 或 32 */
} ssd1306_t;

/* 初始化（先自行 i2c_master_bus_add_device 得到 dev）*/
int ssd1306_init(ssd1306_t *s, i2c_master_dev_handle_t dev, int height);

void ssd1306_clear(ssd1306_t *s);
/* (x,y)画像素 on=1亮0灭 */
void ssd1306_px(ssd1306_t *s, int x, int y, int on);
/* 8x8文本: x列 y行(行高8px)，返回推进列数 */
int ssd1306_text(ssd1306_t *s, const char *str, int x, int row);
/* 水平条形图: x,y,w,h, ratio 0~1 */
void ssd1306_bar(ssd1306_t *s, int x, int y, int w, int h, float ratio);
/* 大号数字 3x5放大scale倍，仅'0'-'9' */
void ssd1306_bignum_scaled(ssd1306_t *s, int digit, int x, int y, int scale);
/* 帧缓冲推屏 */
int ssd1306_flush(ssd1306_t *s);

#endif
