/*********************************************************************************************************
* Exp 11 : IWDG - independent watchdog, 1s timeout. Feed with KEY2 short.
*           The bar shows the time since the last feed; if it fills up the
*           board resets. NOTE: once started the IWDG can never be stopped,
*           so on exit the navigation layer takes over auto feeding.
*           KEY2 short: feed.  KEY2 long: nothing (stop feeding to let it bite).
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "Timer.h"
#include "OLED.h"
#include "IWDG.h"

static u32 s_ulFeedTick = 0;
static u16 s_usFeedCnt  = 0;
static u8  s_ucStarving = 0;

static void Enter(void)
{
  s_usFeedCnt  = 0;
  s_ucStarving = 0;
  InitIWDG();                       /* starts the 1s watchdog, irreversible   */
  FeedIWDG();
  s_ulFeedTick = GetMsTick();
  printf("[E11] IWDG armed, 1s timeout, feed with K2\r\n");
}

static void Exit(void)
{
  /* the watchdog keeps running forever, nav auto-feeds it from now on */
  NavNotifyIwdgArmed();
}

static void Draw(void)
{
  char buf[24];
  u32  age;
  u8   w;

  age = GetMsTick() - s_ulFeedTick;
  if(age > 1000)
  {
    age = 1000;
  }

  NavCanvasClear();
  OLEDShowString12(4, 18, (const u8*)"IWDG 1s", 1);

  sprintf(buf, "FEEDS: %d", s_usFeedCnt);
  OLEDShowString12(4, 30, (const u8*)buf, 1);

  w = (u8)((120 * age) / 1000);
  OLEDFillRect(4, 38, 124, 46, 0);
  OLEDDrawVLine(4, 38, 46, 1);
  OLEDDrawVLine(124, 38, 46, 1);
  OLEDFillRect(4, 38, (u8)(4 + w), 46, 1);

  OLEDShowString12(4, 50, (const u8*)(s_ucStarving ? "STARVING..." : "K2: FEED"), 1);
  OLEDRefreshGRAM();
}

static void Proc2ms(void)
{
  static u8 s_ucDiv = 0;

  s_ucDiv++;
  if(s_ucDiv >= 10)                 /* 20ms, smooth bar */
  {
    s_ucDiv = 0;
    Draw();

    if((GetMsTick() - s_ulFeedTick) > 150)   /* feed ack LEDs off */
    {
      GPIO_WriteBit(GPIOC, GPIO_Pin_4, Bit_SET);
      GPIO_WriteBit(GPIOC, GPIO_Pin_5, Bit_RESET);
    }
  }
}

static void Proc1Sec(void)
{
  if(s_ucStarving)
  {
    printf("[E11] starving, reset imminent\r\n");
  }
}

static void OnKeyShort(void)
{
  FeedIWDG();
  s_ulFeedTick = GetMsTick();
  s_usFeedCnt++;
  s_ucStarving = 0;
  GPIO_WriteBit(GPIOC, GPIO_Pin_4, Bit_RESET);
  GPIO_WriteBit(GPIOC, GPIO_Pin_5, Bit_RESET);
  Draw();
}

static void OnKeyLong(void)
{
  s_ucStarving = 1;                 /* deliberately stop feeding */
  printf("[E11] starving mode, watchdog will bite\r\n");
  Draw();
}

const ExpIf Exp11_If = { "11 IWDG", Enter, Exit, Proc2ms, Proc1Sec, OnKeyShort, OnKeyLong };
