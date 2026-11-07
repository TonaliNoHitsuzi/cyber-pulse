#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* WS2812/WS2812B 驱动（ESP32-C3 RMT，非 DMA，无外部组件依赖） */
int  ws2812_init(int gpio_num, int count);
void ws2812_set(int idx, uint8_t r, uint8_t g, uint8_t b);
void ws2812_fill(uint8_t r, uint8_t g, uint8_t b);
int  ws2812_show(void);   /* 0 = 成功 */

#ifdef __cplusplus
}
#endif
