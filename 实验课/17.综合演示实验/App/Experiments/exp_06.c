/*********************************************************************************************************
* Exp 06 : TIMER - stopwatch on the 1ms system tick (TIM2).
*           KEY2 short: start/stop.  KEY2 long: reset.
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "Timer.h"
#include "OLED.h"

static u8  s_ucRun   = 0;
static u32 s_ulBase  = 0;          /* accumulated ms when stopped */
static u32 s_ulStart = 0;          /* tick at last start */

static u32 Elapsed(void)
{
  if(s_ucRun)
  {
    return s_ulBase + (GetMsTick() - s_ulStart);
  }
  return s_ulBase;
}

static void Enter(void)
{
  s_ucRun   = 0;
  s_ulBase  = 0;
  s_ulStart = 0;
}

static void Exit(void)
{
}

static void Draw(void)
{
  char buf[24];
  u32  ms;

  ms = Elapsed();

  NavCanvasClear();
  OLEDShowString12(4, 18, (const u8*)"STOPWATCH (TIM2 1ms)", 1);
  sprintf(buf, "%02lu:%02lu.%03lu", ms / 60000, (ms / 1000) % 60, ms % 1000);
  OLEDShowString(24, 32, (const u8*)buf);
  OLEDShowString12(4, 48, (const u8*)(s_ucRun ? "STATE: RUNNING" : "STATE: STOPPED"), 1);
  OLEDRefreshGRAM();
}

static void Proc2ms(void)
{
  static u8 s_ucDrawDiv = 0;
  static u8 s_ucBlink   = 0;
  static u8 s_ucBlinkC  = 0;

  if(s_ucRun)
  {
    s_ucBlinkC++;
    if(s_ucBlinkC >= 250)            /* 500ms */
    {
      s_ucBlinkC = 0;
      s_ucBlink  = (u8)!s_ucBlink;
      GPIO_WriteBit(GPIOC, GPIO_Pin_5, s_ucBlink ? Bit_SET : Bit_RESET);
    }
  }

  s_ucDrawDiv++;
  if(s_ucDrawDiv >= 25)
  {
    s_ucDrawDiv = 0;
    Draw();
  }
}

static void OnKeyShort(void)
{
  if(s_ucRun)
  {
    s_ulBase = Elapsed();
    s_ucRun  = 0;
    GPIO_WriteBit(GPIOC, GPIO_Pin_5, Bit_RESET);
  }
  else
  {
    s_ulStart = GetMsTick();
    s_ucRun   = 1;
  }
  Draw();
}

static void OnKeyLong(void)
{
  s_ulBase = 0;
  s_ulStart = GetMsTick();
  printf("[E06] reset\r\n");
  Draw();
}

const ExpIf Exp06_If = { "06 TIMER", Enter, Exit, Proc2ms, 0, OnKeyShort, OnKeyLong };
