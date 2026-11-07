/*********************************************************************************************************
* Exp 16 : ADC - live voltage on PA1 (ADC1 channel 1, DMA stream to queue).
*           Big millivolt readout plus a 128 point history strip.
*           KEY2 short: telemetry stream on/off.  KEY2 long: freeze display.
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "OLED.h"
#include "ADC.h"
#include "hostif.h"

static u16 s_arrHist[128];          /* ring history for the strip graph */
static u8  s_ucHistHead = 0;
static u16 s_usLatest   = 0;
static u8  s_ucFreeze   = 0;
static u8  s_ucTelemEn  = 0;
static u8  s_arrTx5[5];
static u8  s_ucTxIdx    = 0;

static void Enter(void)
{
  u8 i;

  for(i = 0; i < 128; i++)
  {
    s_arrHist[i] = 0;
  }
  s_ucHistHead = 0;
  s_usLatest   = 0;
  s_ucFreeze   = 0;
  s_ucTelemEn  = 0;
  s_ucTxIdx    = 0;

  InitADC();
  NavSetLogSilent(1);               /* binary protocol active, silence logs */
  printf("[E16] ADC on PA1, telem with K2 (log silenced)\r\n");
}

static void Exit(void)
{
  GPIO_InitTypeDef GPIO_InitStructure;

  NavSetLogSilent(0);

  ADC_Cmd(ADC1, DISABLE);
  RCC_APB2PeriphClockCmd(RCC_APB2Periph_ADC1, DISABLE);
  TIM_DeInit(TIM3);
  RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM3, DISABLE);

  GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_1;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;
  GPIO_Init(GPIOA, &GPIO_InitStructure);

  GPIO_WriteBit(GPIOC, GPIO_Pin_5, Bit_RESET);
}

static void Draw(void)
{
  char buf[24];
  u8   i;
  u8   x;
  u8   y;
  u16  v;
  u32  mv;

  mv = ((u32)s_usLatest * 3300) / 4095;

  NavCanvasClear();
  OLEDShowString12(4, 16, (const u8*)"ADC PA1", 1);
  sprintf(buf, "%lumV", mv);
  OLEDShowString(32, 26, (const u8*)buf);

  OLEDFillRect(0, 46, 127, 60, 0);
  for(i = 0; i < 128; i++)
  {
    v = s_arrHist[(u8)((s_ucHistHead + i) & 127)];
    x = i;
    y = (u8)(58 - ((v * 12UL) / 4095UL));
    OLEDDrawPointEx(x, y, 1);
  }

  OLEDShowString12(4, 38, (const u8*)(s_ucTelemEn ? "TELEM:ON " : "TELEM:OFF"), 1);
  OLEDShowString12(70, 38, (const u8*)(s_ucFreeze ? "FRZ" : ""), 1);
  OLEDRefreshGRAM();
}

static void Proc2ms(void)
{
  u16 sample;
  u8  draw;
  static u8 s_ucDiv = 0;

  /* drain everything the DMA pushed into the queue */
  while(ReadADCBuf(&sample))
  {
    s_usLatest = sample;
    s_arrHist[s_ucHistHead] = sample;
    s_ucHistHead = (u8)((s_ucHistHead + 1) & 127);

    if(s_ucTelemEn)
    {
      /* stream every 5th sample as a wave packet (binary, 7-bit payload) */
      s_arrTx5[s_ucTxIdx++] = (u8)((sample * 127UL) / 4095UL);
      if(s_ucTxIdx >= 5)
      {
        s_ucTxIdx = 0;
        HostIfSendWave5(s_arrTx5);
      }
    }
  }

  draw = 0;
  if(s_ucTelemEn)
  {
    GPIO_WriteBit(GPIOC, GPIO_Pin_5,
      GPIO_ReadOutputDataBit(GPIOC, GPIO_Pin_5) ? Bit_RESET : Bit_SET);
  }

  s_ucDiv++;
  if(s_ucDiv >= 20 && !s_ucFreeze)
  {
    s_ucDiv = 0;
    draw = 1;
  }

  if(draw)
  {
    Draw();
  }
}

static void Proc1Sec(void)
{
  u32 mv;

  if(!s_ucTelemEn)
  {
    return;
  }

  mv = ((u32)s_usLatest * 3300) / 4095;
  HostIfSendInfo((u8)(mv & 0x7F), (u8)((mv >> 7) & 0x7F));   /* 7-bit split */
}

static void OnKeyShort(void)
{
  s_ucTelemEn = (u8)!s_ucTelemEn;
  s_ucTxIdx   = 0;
  Draw();
}

static void OnKeyLong(void)
{
  s_ucFreeze = (u8)!s_ucFreeze;
  Draw();
}

const ExpIf Exp16_If = { "16 ADC", Enter, Exit, Proc2ms, Proc1Sec, OnKeyShort, OnKeyLong };
