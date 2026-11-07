/*********************************************************************************************************
* Exp 14 : CAPT - input capture on PA1 (TIM5_CH2) wired to the external button
*           module. Measures how long the button is pressed (low pulse width,
*           100us resolution, 6.5s range). Records LAST / BEST(shortest) / AVG.
*           KEY2 short: cycle view.  KEY2 long: clear records.
*           Self contained driver: the original Capture.c uses TIM5_CH1/PA0
*           which collides with the framework 1s tick, so this module owns
*           TIM5 exclusively (framework only uses TIM2).
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "OLED.h"
#include "hostif.h"

static volatile u16 s_usLastTicks = 0;
static volatile u8  s_ucNewCap    = 0;
static volatile u16 s_usStartT    = 0;
static volatile u8  s_ucCapActive = 0;

static u16 s_usLastMs = 0;
static u16 s_usBestMs = 0xFFFF;
static u32 s_ulSumMs  = 0;
static u16 s_usCnt    = 0;
static u8  s_ucView   = 0;          /* 0 last 1 best 2 avg */

static void ConfigCapture(void)
{
  GPIO_InitTypeDef        GPIO_InitStructure;
  TIM_TimeBaseInitTypeDef TIM_TimeBaseStructure;
  TIM_ICInitTypeDef       TIM_ICInitStructure;
  NVIC_InitTypeDef        NVIC_InitStructure;

  RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM5, ENABLE);
  RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);

  /* PA1 as TIM5_CH2 input, pull-up because the button pulls to GND */
  GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_1;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPU;
  GPIO_Init(GPIOA, &GPIO_InitStructure);

  /* 72MHz/720 = 100kHz -> 10us resolution, 655ms per wrap */
  TIM_TimeBaseStructure.TIM_Period        = 65535;
  TIM_TimeBaseStructure.TIM_Prescaler     = 719;
  TIM_TimeBaseStructure.TIM_ClockDivision = 0;
  TIM_TimeBaseStructure.TIM_CounterMode   = TIM_CounterMode_Up;
  TIM_TimeBaseInit(TIM5, &TIM_TimeBaseStructure);

  TIM_ICInitStructure.TIM_Channel     = TIM_Channel_2;
  TIM_ICInitStructure.TIM_ICPolarity  = TIM_ICPolarity_Falling;   /* low pulse start */
  TIM_ICInitStructure.TIM_ICSelection = TIM_ICSelection_DirectTI;
  TIM_ICInitStructure.TIM_ICPrescaler = TIM_ICPSC_DIV1;
  TIM_ICInitStructure.TIM_ICFilter    = 0x0;
  TIM_ICInit(TIM5, &TIM_ICInitStructure);

  NVIC_InitStructure.NVIC_IRQChannel                   = TIM5_IRQn;
  NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 2;
  NVIC_InitStructure.NVIC_IRQChannelSubPriority        = 0;
  NVIC_InitStructure.NVIC_IRQChannelCmd                = ENABLE;
  NVIC_Init(&NVIC_InitStructure);

  TIM_ITConfig(TIM5, TIM_IT_CC2, ENABLE);
  TIM_Cmd(TIM5, ENABLE);
}

void TIM5_IRQHandler(void)
{
  u16 val;

  if(TIM_GetITStatus(TIM5, TIM_IT_CC2) != RESET)
  {
    TIM_ClearITPendingBit(TIM5, TIM_IT_CC2);
    val = (u16)TIM_GetCapture2(TIM5);

    if(!s_ucCapActive)                 /* falling edge: press started */
    {
      s_usStartT    = val;
      s_ucCapActive = 1;

      /* watch for the release edge now */
      TIM_OC2PolarityConfig(TIM5, TIM_ICPolarity_Rising);
    }
    else                              /* rising edge: released */
    {
      s_usLastTicks = (u16)(val - s_usStartT);
      s_ucNewCap    = 1;
      s_ucCapActive = 0;

      TIM_OC2PolarityConfig(TIM5, TIM_ICPolarity_Falling);
    }
  }
}

static void Enter(void)
{
  s_usLastMs = 0;
  s_usBestMs = 0xFFFF;
  s_ulSumMs  = 0;
  s_usCnt    = 0;
  s_ucView   = 0;
  s_ucNewCap = 0;
  ConfigCapture();
  printf("[E14] capture on PA1 (external button), press it\r\n");
}

static void Exit(void)
{
  GPIO_InitTypeDef GPIO_InitStructure;

  TIM_DeInit(TIM5);
  RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM5, DISABLE);

  GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_1;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;
  GPIO_Init(GPIOA, &GPIO_InitStructure);
}

static void Draw(void)
{
  char buf[24];
  u16  ms;
  u8   buf5[5];

  NavCanvasClear();
  OLEDShowString12(4, 18, (const u8*)"CAPTURE PA1", 1);

  switch(s_ucView)
  {
    case 0:  OLEDShowString12(4, 32, (const u8*)"LAST:", 1); ms = s_usLastMs; break;
    case 1:  OLEDShowString12(4, 32, (const u8*)"BEST:", 1); ms = s_usBestMs; break;
    default: OLEDShowString12(4, 32, (const u8*)"AVG :", 1); ms = (u16)(s_usCnt ? (s_ulSumMs / s_usCnt) : 0); break;
  }

  if(ms == 0xFFFF)
  {
    OLEDShowString(40, 30, (const u8*)"--");
  }
  else
  {
    sprintf(buf, "%dms", ms);
    OLEDShowString(40, 30, (const u8*)buf);
  }

  sprintf(buf, "N=%d", s_usCnt);
  OLEDShowString12(4, 48, (const u8*)buf, 1);
  OLEDShowString12(60, 48, (const u8*)"K2:VIEW", 1);
  OLEDRefreshGRAM();

  /* telemetry: push last value if streaming (7-bit split of u16 fields) */
  if(HostIfTelemIsOn() && s_usCnt)
  {
    buf5[0] = (u8)(s_usLastMs & 0x7F);
    buf5[1] = (u8)((s_usLastMs >> 7) & 0x7F);
    buf5[2] = (u8)(s_usBestMs & 0x7F);
    buf5[3] = (u8)((s_usBestMs >> 7) & 0x7F);
    buf5[4] = (u8)(s_usCnt & 0x7F);
    HostIfSendWave5(buf5);
  }
}

static void Proc2ms(void)
{
  u16 ticks;
  u16 ms;

  if(s_ucNewCap)
  {
    s_ucNewCap = 0;
    ticks = s_usLastTicks;
    ms    = (u16)((ticks * 10UL) / 1000UL);   /* 100us ticks -> ms */

    s_usLastMs = ms;
    s_ulSumMs += ms;
    s_usCnt++;
    if(ms < s_usBestMs)
    {
      s_usBestMs = ms;
    }

    GPIO_WriteBit(GPIOC, GPIO_Pin_4, Bit_RESET);
    printf("[E14] press %dms (best %dms n=%d)\r\n", s_usLastMs, s_usBestMs, s_usCnt);
    Draw();
  }
  else
  {
    GPIO_WriteBit(GPIOC, GPIO_Pin_4, Bit_SET);
  }
}

static void OnKeyShort(void)
{
  s_ucView = (u8)((s_ucView + 1) % 3);
  Draw();
}

static void OnKeyLong(void)
{
  s_usLastMs = 0;
  s_usBestMs = 0xFFFF;
  s_ulSumMs  = 0;
  s_usCnt    = 0;
  printf("[E14] records cleared\r\n");
  Draw();
}

const ExpIf Exp14_If = { "14 CAPT", Enter, Exit, Proc2ms, 0, OnKeyShort, OnKeyLong };
