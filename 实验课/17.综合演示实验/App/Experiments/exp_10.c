/*********************************************************************************************************
* Exp 10 : OLED - display test pages.
*           Page 0: original demo text. Page 1: graphic pattern.
*           KEY2 short: next page.  KEY2 long: display on/off toggle.
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "OLED.h"

static u8 s_ucPage = 0;
static u8 s_ucOn   = 1;
static u8 s_ucStarted = 0;          /* idle until the first KEY2 press */

static void Enter(void)
{
  s_ucPage    = 0;
  s_ucOn      = 1;
  s_ucStarted = 0;
}

static void Exit(void)
{
  if(!s_ucOn)
  {
    OLEDDisplayOn();
  }
}

static void Draw(void)
{
  u8 x;
  u8 y;

  NavCanvasClear();

  if(!s_ucStarted)
  {
    OLEDShowString12(16, 28, (const u8*)"OLED TEST", 1);
    OLEDShowString12(16, 44, (const u8*)"K2: START", 1);
  }
  else if(s_ucPage == 0)
  {
    OLEDShowString12(16, 18, (const u8*)"STM32F103Board", 1);
    OLEDShowString12(32, 30, (const u8*)"00-06-00", 1);
    OLEDShowString12(24, 42, (const u8*)"2018-01-01", 1);
    OLEDShowString12(24, 52, (const u8*)"OLED IS OK!", 1);
  }
  else
  {
    for(y = 16; y < 62; y += 8)
    {
      for(x = 0; x < 128; x += 8)
      {
        if(((x / 8) & 1) ^ ((y / 8) & 1))
        {
          OLEDFillRect(x, y, (u8)(x + 5), (u8)(y + 5), 1);
        }
      }
    }
  }
  OLEDRefreshGRAM();
}

static void Proc2ms(void)
{
}

static void OnKeyShort(void)
{
  if(!s_ucStarted)
  {
    s_ucStarted = 1;               /* first press starts the demo */
  }
  else
  {
    s_ucPage = (u8)!s_ucPage;
  }
  Draw();
}

static void OnKeyLong(void)
{
  s_ucOn = (u8)!s_ucOn;
  if(s_ucOn)
  {
    OLEDDisplayOn();
  }
  else
  {
    OLEDDisplayOff();
  }
  printf("[E10] display %s\r\n", s_ucOn ? "on" : "off");
}

const ExpIf Exp10_If = { "10 OLED", Enter, Exit, Proc2ms, 0, OnKeyShort, OnKeyLong };
