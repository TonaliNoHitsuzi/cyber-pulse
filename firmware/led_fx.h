#pragma once
#ifdef __cplusplus
extern "C" {
#endif

/* 灯带效果引擎（独立任务，20ms 刷新，与采样主循环解耦）
 * mode: 0=关 1=心跳脉冲 2=彩虹旋转(心率控速) 3=呼吸单色 4=BPM水位 5=彩虹呼吸
 */
void led_fx_init(int gpio, int n);
void led_fx_set_level(int pct);     /* 0~100 */
int  led_fx_level(void);
void led_fx_set_mode(int mode);
int  led_fx_mode(void);
void led_fx_beat(void);             /* 检测到一次搏动时调用 */
void led_fx_set_bpm(float bpm);     /* 原始心率，内部做平滑 */
void led_fx_status(int *mode, int *level, float *bpm_smooth);

/* 核心参数（全部可经串口/BLE 调整）
 * rot_idle  无信号时转速(圈/秒)
 * rot_max   180BPM 时额外转速
 * hue_idle  静息基色(0~1)
 * hue_span  心率引起的色相跨度
 * pbase     静息亮度占比
 * ppeak     搏动峰值亮度占比
 * gate      搏动速率闸门(心动周期比例)
 */
void led_fx_set_params(float rot_idle, float rot_max, float hue_idle,
                       float hue_span, float pbase, float ppeak, float gate, float decay);
void led_fx_get_params(float *rot_idle, float *rot_max, float *hue_idle,
                       float *hue_span, float *pbase, float *ppeak, float *gate, float *decay);

#ifdef __cplusplus
}
#endif
