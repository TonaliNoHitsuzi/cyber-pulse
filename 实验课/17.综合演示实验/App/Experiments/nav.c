/*********************************************************************************************************
* Module Name : nav.c
* Abstract    : Navigation system implementation.
*               Keys: KEY1=PC1(prev) KEY2=PC2(interact) KEY3=PA0(next), all
*               pull-up inputs, pressed = low, 8x2ms shift debounce.
*               Top bar: 12px title at (0,2), right aligned "nn/16", line y=15.
*               Canvas: y 16..63 belongs to the active experiment.
*               Switch animation: both LEDs alternate for 200ms.
*               IWDG latch: once experiment 11 started IWDG it can never be
*               stopped, so after leaving exp 11 the nav feeds it every second.
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "nav.h"
#include "experiments.h"
#include "Timer.h"
#include "OLED.h"
#include "IWDG.h"

#define KEY1_READ()  GPIO_ReadInputDataBit(GPIOC, GPIO_Pin_1)
#define KEY2_READ()  GPIO_ReadInputDataBit(GPIOC, GPIO_Pin_2)
#define KEY3_READ()  GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_0)

#define KEY_LONG_THD   250          /* 250 x 2ms = 500ms long press threshold */
#define SWITCH_ANIM_MS 200

static u8  s_ucCurIdx     = 0;
static u8  s_ucSilent     = 0;
static u8  s_ucIwdgLatch  = 0;
static u8  s_ucKeysOwned  = 0;      /* 1 = experiment owns KEY1/KEY3 (snake game) */
static u32 s_ulAnimStart  = 0xFFFFFFFF;

static u8  s_arrShift[3]  = {0xFF, 0xFF, 0xFF};   /* KEY1 KEY2 KEY3 shift registers    */
static u8  s_arrStable[3] = {1, 1, 1};            /* debounced levels, 1 = released    */
static u16 s_arrHold[3]   = {0, 0, 0};            /* held sample counter (x2ms)        */
static u8  s_arrLongFired[3] = {0, 0, 0};

/*********************************************************************************************************
*                                              internal helpers
*********************************************************************************************************/
static void DrawTopBar(void)
{
  char buf[8];
  u8   x;

  OLEDFillRect(0, 0, 127, 14, 0);
  OLEDShowString12(0, 1, (const u8*)g_arrExp[s_ucCurIdx]->name, 1);

  /* right aligned "nn/nn" : 5 chars x 6px = 30px */
  sprintf(buf, "%02d/%02d", s_ucCurIdx + 1, EXP_NUM);
  x = 127 - 30;
  OLEDShowString12(x, 1, (const u8*)buf, 1);

  OLEDDrawHLine(15, 0, 127, 1);
}

static void LedAllOff(void)
{
  GPIO_WriteBit(GPIOC, GPIO_Pin_4, Bit_SET);
  GPIO_WriteBit(GPIOC, GPIO_Pin_5, Bit_RESET);
}

static void ConfigKeyGPIO(void)
{
  GPIO_InitTypeDef GPIO_InitStructure;

  RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);
  RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOC, ENABLE);

  GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_1 | GPIO_Pin_2;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPU;
  GPIO_Init(GPIOC, &GPIO_InitStructure);

  GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_0;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPU;
  GPIO_Init(GPIOA, &GPIO_InitStructure);
}

static void EnterExp(u8 idx)
{
  s_ucCurIdx = idx;

  OLEDClear();                    /* full clear, experiment redraws its canvas */
  DrawTopBar();

  if(g_arrExp[idx]->Enter != 0)
  {
    g_arrExp[idx]->Enter();
  }

  OLEDRefreshGRAM();

  printf("[NAV] ENTER %02d %s\r\n", idx + 1, g_arrExp[idx]->name);
}

static void SwitchTo(u8 idx)
{
  printf("[NAV] EXIT %02d\r\n", s_ucCurIdx + 1);

  if(g_arrExp[s_ucCurIdx]->Exit != 0)
  {
    g_arrExp[s_ucCurIdx]->Exit();
  }

  LedAllOff();
  s_ucSilent = 0;                 /* reset log silence on every switch */

  EnterExp(idx);

  s_ulAnimStart = GetMsTick();    /* 200ms LED switch animation */
}

static void SwitchExp(u8 dir)     /* dir: 0 = prev (KEY1), 1 = next (KEY3) */
{
  u8 idx;

  if(dir)
  {
    idx = (u8)((s_ucCurIdx + 1) % EXP_NUM);
  }
  else
  {
    idx = (u8)((s_ucCurIdx + EXP_NUM - 1) % EXP_NUM);
  }

  SwitchTo(idx);
}

void NavRemoteSwitch(u8 idx)      /* called by host protocol SET_EXP */
{
  if(idx >= EXP_NUM)
  {
    return;
  }
  SwitchTo(idx);
}

/*********************************************************************************************************
*                                              API implementation
*********************************************************************************************************/
void InitNav(void)
{
  ConfigKeyGPIO();
  LedAllOff();

  /* exp 11 may have latched the IWDG before a reset-free session */
  s_ucIwdgLatch = 0;
  EnterExp(0);
}

void NavCanvasClear(void)
{
  OLEDFillRect(0, 16, 127, 63, 0);
}

void NavSetLogSilent(u8 on)
{
  s_ucSilent = on;
}

u8 NavIsLogSilent(void)
{
  return s_ucSilent;
}

void NavExpPrintf(const char* p)
{
  if(!s_ucSilent)
  {
    printf("%s", p);
  }
}

static void OnKey2Short(void)
{
  if(!s_ucSilent)
  {
    printf("[KEY2] SHORT\r\n");
  }

  if(g_arrExp[s_ucCurIdx]->OnKeyShort != 0)
  {
    g_arrExp[s_ucCurIdx]->OnKeyShort();
  }
}

static void OnKey2Long(void)
{
  if(!s_ucSilent)
  {
    printf("[KEY2] LONG\r\n");
  }

  if(g_arrExp[s_ucCurIdx]->OnKeyLong != 0)
  {
    g_arrExp[s_ucCurIdx]->OnKeyLong();
  }
}

static void ScanKey(u8 i, u8 raw)
{
  u8 stable;

  s_arrShift[i] = (u8)((s_arrShift[i] << 1) | raw);

  if(s_arrShift[i] == 0x00)
  {
    stable = 0;
  }
  else if(s_arrShift[i] == 0xFF)
  {
    stable = 1;
  }
  else
  {
    return;
  }

  if(stable == s_arrStable[i])
  {
    /* still held: track duration for long press */
    if(stable == 0)
    {
      if(s_arrHold[i] < 0xFFFF)
      {
        s_arrHold[i]++;
      }

      if(i == 1 && s_arrHold[i] == KEY_LONG_THD && !s_arrLongFired[1])
      {
        s_arrLongFired[1] = 1;
        OnKey2Long();
      }
    }
    return;
  }

  /* edge */
  if(stable == 0)                            /* press edge */
  {
    s_arrHold[i]      = 0;
    s_arrLongFired[i] = 0;
  }
  else                                       /* release edge */
  {
    if(i == 0)                               /* KEY1 released -> previous */
    {
      if(!s_ucSilent)
      {
        printf("[KEY1] <\r\n");
      }
      if(!s_ucKeysOwned)
      {
        SwitchExp(0);
      }
    }
    else if(i == 2)                          /* KEY3 released -> next */
    {
      if(!s_ucSilent)
      {
        printf("[KEY3] >\r\n");
      }
      if(!s_ucKeysOwned)
      {
        SwitchExp(1);
      }
    }
    else                                     /* KEY2 released */
    {
      if(!s_arrLongFired[1])
      {
        OnKey2Short();
      }
    }
  }

  s_arrStable[i] = stable;
}

void NavProc2ms(void)
{
  u32 now;
  u32 t;

  ScanKey(0, (u8)KEY1_READ());
  ScanKey(1, (u8)KEY2_READ());
  ScanKey(2, (u8)KEY3_READ());

  /* switch animation: alternate PC4/PC5 for 200ms */
  now = GetMsTick();
  if((now - s_ulAnimStart) < SWITCH_ANIM_MS)
  {
    t = (now - s_ulAnimStart) / 50;
    if(t & 1)
    {
      GPIO_WriteBit(GPIOC, GPIO_Pin_4, Bit_SET);
      GPIO_WriteBit(GPIOC, GPIO_Pin_5, Bit_SET);
    }
    else
    {
      GPIO_WriteBit(GPIOC, GPIO_Pin_4, Bit_RESET);
      GPIO_WriteBit(GPIOC, GPIO_Pin_5, Bit_RESET);
    }
  }
}

void NavProc1Sec(void)
{
  /* IWDG latch: keep the (unstoppable) watchdog alive once exp 11 armed it */
  if(s_ucIwdgLatch)
  {
    FeedIWDG();
  }
}

void NavNotifyIwdgArmed(void)
{
  s_ucIwdgLatch = 1;
  printf("[NAV] IWDG latched, nav auto-feeds\r\n");
}

void NavSetKeysOwned(u8 on)
{
  s_ucKeysOwned = (u8)(on ? 1 : 0);
}

u8 GetCurExpIdx(void)
{
  return s_ucCurIdx;
}
