/*********************************************************************************************************
* Exp 01 : BASE - benchmark project demo. Run timer, heartbeat LED, hello print.
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "Timer.h"
#include "OLED.h"

static u8  s_ucRun     = 1;
static u32 s_ulStart   = 0;
static u16 s_iBlinkCnt = 0;
static u8  s_ucLed2    = 0;

static void Enter(void)
{
  s_ucRun     = 1;
  s_ulStart   = GetMsTick();
  s_iBlinkCnt = 0;
  s_ucLed2    = 0;
  GPIO_WriteBit(GPIOC, GPIO_Pin_4, Bit_SET);
  GPIO_WriteBit(GPIOC, GPIO_Pin_5, Bit_RESET);
  printf("[E01] benchmark demo start\r\n");
}

static void Exit(void)
{
}

static void Draw(void)
{
  u32 ms;
  u8  min;
  u8  sec;
  char buf[16];

  NavCanvasClear();

  ms = GetMsTick() - s_ulStart;
  if(!s_ucRun)
  {
    /* freeze display when paused: keep last drawn numbers, just show state */
  }
  min = (u8)((ms / 1000) / 60);
  sec = (u8)((ms / 1000) % 60);

  OLEDShowString12(4, 18, (const u8*)"RUN TIME", 1);
  sprintf(buf, "%02d:%02d", min, sec);
  OLEDShowString(40, 32, (const u8*)buf);
  OLEDShowString12(4, 48, (const u8*)(s_ucRun ? "STATE: RUNNING" : "STATE: PAUSED"), 1);

  OLEDRefreshGRAM();
}

static void Proc2ms(void)
{
  static u8 s_ucDrawDiv = 0;

  if(s_ucRun)
  {
    s_iBlinkCnt++;
    if(s_iBlinkCnt >= 125)            /* 250ms */
    {
      s_iBlinkCnt = 0;
      s_ucLed2 = (u8)!s_ucLed2;
      GPIO_WriteBit(GPIOC, GPIO_Pin_5, s_ucLed2 ? Bit_SET : Bit_RESET);
    }
  }

  s_ucDrawDiv++;
  if(s_ucDrawDiv >= 100)              /* redraw ~5Hz */
  {
    s_ucDrawDiv = 0;
    Draw();
  }
}

static void Proc1Sec(void)
{
  if(s_ucRun)
  {
    GPIO_WriteBit(GPIOC, GPIO_Pin_4,
      GPIO_ReadOutputDataBit(GPIOC, GPIO_Pin_4) ? Bit_RESET : Bit_SET);
    printf("[E01] alive %lus\r\n", (GetMsTick() - s_ulStart) / 1000);
  }
}

static void OnKeyShort(void)
{
  s_ucRun = (u8)!s_ucRun;
  if(s_ucRun)
  {
    /* resume: rebase start so the timer continues */
  }
  Draw();
}

static void OnKeyLong(void)
{
  s_ulStart = GetMsTick();
  Draw();
}

const ExpIf Exp01_If = { "01 BASE", Enter, Exit, Proc2ms, Proc1Sec, OnKeyShort, OnKeyLong };
