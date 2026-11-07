/*********************************************************************************************************
* Exp 04 : KEY - KEY2 self demonstration. Shows live level, press count, last
*           press duration and last press type. LED1 lights while pressed.
*           KEY2 short: (is the demo object, counts the press)
*           KEY2 long : clear counters.
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "Timer.h"
#include "OLED.h"

static u16 s_ucCount   = 0;
static u16 s_iLastDur  = 0;        /* ms of last press, self measured */
static u8  s_ucLastTyp = 0;        /* 0 short 1 long */
static u8  s_ucDown    = 0;
static u32 s_ulDownAt  = 0;

static void Enter(void)
{
  s_ucCount   = 0;
  s_iLastDur  = 0;
  s_ucLastTyp = 0;
  s_ucDown    = 0;
  GPIO_WriteBit(GPIOC, GPIO_Pin_4, Bit_SET);
}

static void Exit(void)
{
}

static void Draw(void)
{
  char buf[24];

  NavCanvasClear();
  OLEDShowString12(4, 18, (const u8*)"KEY2 DEMO", 1);

  sprintf(buf, "STATE : %s", s_ucDown ? "DOWN" : "UP");
  OLEDShowString12(4, 30, (const u8*)buf, 1);
  sprintf(buf, "COUNT : %d", s_ucCount);
  OLEDShowString12(4, 40, (const u8*)buf, 1);
  sprintf(buf, "LAST  : %dms %s", s_iLastDur, s_ucLastTyp ? "LONG" : "SHORT");
  OLEDShowString12(4, 50, (const u8*)buf, 1);
  OLEDRefreshGRAM();
}

static void Proc2ms(void)
{
  u8 raw = (u8)GPIO_ReadInputDataBit(GPIOC, GPIO_Pin_2);

  if(!raw && !s_ucDown)                 /* press edge, self timed */
  {
    s_ucDown   = 1;
    s_ulDownAt = GetMsTick();
    GPIO_WriteBit(GPIOC, GPIO_Pin_4, Bit_RESET);
    Draw();
  }
  else if(raw && s_ucDown)              /* release edge */
  {
    s_ucDown   = 0;
    s_iLastDur = (u16)(GetMsTick() - s_ulDownAt);
    GPIO_WriteBit(GPIOC, GPIO_Pin_4, Bit_SET);
    printf("[E04] press %dms\r\n", s_iLastDur);
    Draw();
  }
}

static void OnKeyShort(void)
{
  s_ucCount++;
  s_ucLastTyp = 0;
  Draw();
}

static void OnKeyLong(void)
{
  s_ucCount   = 0;
  s_iLastDur  = 0;
  s_ucLastTyp = 0;
  Draw();
}

const ExpIf Exp04_If = { "04 KEY", Enter, Exit, Proc2ms, 0, OnKeyShort, OnKeyLong };
