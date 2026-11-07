/*********************************************************************************************************
* Exp 02 : CLOCK - uart electronic clock demo. Starts at 23:59:50.
*           KEY2 short: pause/resume.  KEY2 long (hold): fast forward.
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "Timer.h"
#include "OLED.h"
#include "RunClock.h"

static u8 s_ucFfwd    = 0;
static u8 s_ucPaused = 0;

static void Enter(void)
{
  s_ucFfwd    = 0;
  s_ucPaused  = 0;
  InitRunClock();
  PauseClock(FALSE);
  SetTimeVal(TIME_VAL_HOUR, 23);
  SetTimeVal(TIME_VAL_MIN,  59);
  SetTimeVal(TIME_VAL_SEC,  50);
  GPIO_WriteBit(GPIOC, GPIO_Pin_4, Bit_SET);
  GPIO_WriteBit(GPIOC, GPIO_Pin_5, Bit_RESET);
  printf("[E02] clock start 23:59:50\r\n");
}

static void Exit(void)
{
}

static void Draw(void)
{
  char buf[16];

  NavCanvasClear();
  OLEDShowString12(4, 18, (const u8*)"UART CLOCK", 1);
  sprintf(buf, "%02d:%02d:%02d",
          GetTimeVal(TIME_VAL_HOUR), GetTimeVal(TIME_VAL_MIN), GetTimeVal(TIME_VAL_SEC));
  OLEDShowString(32, 32, (const u8*)buf);
  OLEDShowString12(4, 48, (const u8*)(s_ucFfwd ? "MODE: FAST FWD" : "MODE: RUNNING"), 1);
  OLEDRefreshGRAM();
}

static void Proc2ms(void)
{
  u8   i;
  static u8 s_ucDrawDiv = 0;

  if(s_ucFfwd)
  {
    for(i = 0; i < 50; i++)          /* 50 x 2ms = 100ms clock per tick */
    {
      RunClockPer2Ms();
    }
  }
  else
  {
    RunClockPer2Ms();
  }

  s_ucDrawDiv++;
  if(s_ucDrawDiv >= 25)              /* ~12Hz so the seconds tick smoothly */
  {
    s_ucDrawDiv = 0;
    Draw();
  }
}

static void Proc1Sec(void)
{
  printf("[E02] %02d:%02d:%02d\r\n",
         GetTimeVal(TIME_VAL_HOUR), GetTimeVal(TIME_VAL_MIN), GetTimeVal(TIME_VAL_SEC));
  GPIO_WriteBit(GPIOC, GPIO_Pin_5,
    GPIO_ReadOutputDataBit(GPIOC, GPIO_Pin_5) ? Bit_RESET : Bit_SET);
}

static void OnKeyShort(void)
{
  if(s_ucFfwd)
  {
    s_ucFfwd = 0;
  }
  else
  {
    s_ucPaused = (u8)!s_ucPaused;
    PauseClock(s_ucPaused);
  }
  Draw();
}

static void OnKeyLong(void)
{
  s_ucFfwd   = 1;
  s_ucPaused = 0;
  PauseClock(FALSE);
  Draw();
}

const ExpIf Exp02_If = { "02 CLOCK", Enter, Exit, Proc2ms, Proc1Sec, OnKeyShort, OnKeyLong };
