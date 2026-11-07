/*********************************************************************************************************
* Exp 08 : RCC - live clock tree readout (SYSCLK / HCLK / PCLK1 / PCLK2 and the
*           current system clock source). Read only by design: switching SYSCLK
*           at runtime would desynchronize the UART1 baud rate.
*           KEY2 short: refresh.  KEY2 long: dump to serial.
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "OLED.h"

static RCC_ClocksTypeDef s_rccClks;

static const char* ClkSrcName(void)
{
  u32 sws = (RCC->CFGR >> 2) & 0x3;

  switch(sws)
  {
    case 0: return "HSI";
    case 1: return "HSE";
    case 2: return "PLL";
    default: return "?";
  }
}

static void Refresh(void)
{
  RCC_GetClocksFreq(&s_rccClks);
}

static void Enter(void)
{
  Refresh();
  printf("[E08] SYSCLK=%lu HCLK=%lu PCLK1=%lu PCLK2=%lu src=%s\r\n",
         s_rccClks.SYSCLK_Frequency, s_rccClks.HCLK_Frequency,
         s_rccClks.PCLK1_Frequency, s_rccClks.PCLK2_Frequency, ClkSrcName());
}

static void Exit(void)
{
}

static void Draw(void)
{
  char buf[24];

  NavCanvasClear();
  OLEDShowString12(4, 16, (const u8*)"CLOCK TREE", 1);
  sprintf(buf, "SRC   : %s", ClkSrcName());
  OLEDShowString12(4, 28, (const u8*)buf, 1);
  sprintf(buf, "SYSCLK: %lu MHz", s_rccClks.SYSCLK_Frequency / 1000000);
  OLEDShowString12(4, 38, (const u8*)buf, 1);
  sprintf(buf, "P1 %lu  P2 %lu MHz",
          s_rccClks.PCLK1_Frequency / 1000000, s_rccClks.PCLK2_Frequency / 1000000);
  OLEDShowString12(4, 48, (const u8*)buf, 1);
  OLEDRefreshGRAM();
}

static void Proc2ms(void)
{
}

static void OnKeyShort(void)
{
  Refresh();
  Draw();
}

static void OnKeyLong(void)
{
  printf("[E08] SYSCLK=%lu HCLK=%lu PCLK1=%lu PCLK2=%lu src=%s\r\n",
         s_rccClks.SYSCLK_Frequency, s_rccClks.HCLK_Frequency,
         s_rccClks.PCLK1_Frequency, s_rccClks.PCLK2_Frequency, ClkSrcName());
}

const ExpIf Exp08_If = { "08 RCC", Enter, Exit, Proc2ms, 0, OnKeyShort, OnKeyLong };
