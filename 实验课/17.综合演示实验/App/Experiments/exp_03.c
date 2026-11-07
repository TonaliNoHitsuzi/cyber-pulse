/*********************************************************************************************************
* Exp 03 : MARQUEE - running light. 8 virtual LEDs on the OLED plus the 2 real
*           board LEDs. KEY2 short: speed cycle (500/250/125/60ms step).
*           KEY2 long: reverse direction.
*********************************************************************************************************/
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "Timer.h"
#include "OLED.h"

static const u16 s_arrStep[4] = {500, 250, 125, 60};

static u8  s_ucPos     = 0;
static u8  s_ucDir     = 1;         /* 1 = right */
static u8  s_ucSpeed   = 1;
static u32 s_ulLast    = 0;

static void Enter(void)
{
  s_ucPos   = 0;
  s_ucDir   = 1;
  s_ucSpeed = 1;
  s_ulLast  = GetMsTick();
}

static void Exit(void)
{
}

static void Draw(void)
{
  u8 i;
  u8 x;

  NavCanvasClear();
  OLEDShowString12(4, 20, (const u8*)"MARQUEE", 1);

  for(i = 0; i < 8; i++)
  {
    x = (u8)(6 + i * 16);
    if(i == s_ucPos)
    {
      OLEDFillRect(x, 34, (u8)(x + 11), 44, 1);
    }
    else
    {
      OLEDDrawHLine(44, x, (u8)(x + 11), 1);
    }
  }
  OLEDRefreshGRAM();
}

static void Proc2ms(void)
{
  if((GetMsTick() - s_ulLast) >= s_arrStep[s_ucSpeed])
  {
    s_ulLast = GetMsTick();

    if(s_ucDir)
    {
      s_ucPos = (u8)((s_ucPos + 1) & 7);
    }
    else
    {
      s_ucPos = (u8)((s_ucPos + 7) & 7);
    }

    /* the two real LEDs chase each other */
    GPIO_WriteBit(GPIOC, GPIO_Pin_4, (s_ucPos & 1) ? Bit_SET : Bit_RESET);
    GPIO_WriteBit(GPIOC, GPIO_Pin_5, (s_ucPos & 1) ? Bit_RESET : Bit_SET);

    Draw();
  }
}

static void OnKeyShort(void)
{
  s_ucSpeed = (u8)((s_ucSpeed + 1) & 3);
  Draw();
}

static void OnKeyLong(void)
{
  s_ucDir = (u8)!s_ucDir;
  Draw();
}

const ExpIf Exp03_If = { "03 MARQUEE", Enter, Exit, Proc2ms, 0, OnKeyShort, OnKeyLong };
