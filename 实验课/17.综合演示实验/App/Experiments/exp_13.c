/*********************************************************************************************************
* Exp 13 : PWM - 120 Hz PWM on PB5 (TIM3_CH2), duty 0..600 (step 50, 12 steps).
*           KEY2 short: duty +1 step.  KEY2 long: duty -1 step.
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "Timer.h"
#include "OLED.h"
#include "PWM.h"

static i16 s_iDuty = 0;              /* 0..600, mirrors PWM module state */

static void Enter(void)
{
  InitPWM();
  SetPWM(0);
  s_iDuty = 0;
  printf("[E13] PWM 120Hz on PB5, K2 short=+ long=-\r\n");
}

static void Exit(void)
{
  GPIO_InitTypeDef GPIO_InitStructure;

  TIM_DeInit(TIM3);
  RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM3, DISABLE);
  GPIO_PinRemapConfig(GPIO_PartialRemap_TIM3, DISABLE);

  /* release PB5 */
  GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_5;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPU;
  GPIO_Init(GPIOB, &GPIO_InitStructure);
}

static void Draw(void)
{
  char buf[24];
  u8   w;
  u8   pct;

  pct = (u8)((s_iDuty * 100) / 600);
  w   = (u8)((120 * s_iDuty) / 600);

  NavCanvasClear();
  OLEDShowString12(4, 18, (const u8*)"PWM 120Hz PB5", 1);
  sprintf(buf, "%d%%", pct);
  OLEDShowString(48, 30, (const u8*)buf);

  OLEDFillRect(4, 50, 124, 58, 0);
  OLEDDrawVLine(4, 50, 58, 1);
  OLEDDrawVLine(124, 50, 58, 1);
  OLEDFillRect(4, 50, (u8)(4 + w), 58, 1);
  OLEDRefreshGRAM();
}

static void Proc2ms(void)
{
  static u8 s_ucDiv = 0;
  static u8 s_ucBlink = 0;
  static u8 s_ucBlinkC = 0;

  s_ucBlinkC++;
  if(s_ucBlinkC >= 250)
  {
    s_ucBlinkC = 0;
    s_ucBlink  = (u8)!s_ucBlink;
    GPIO_WriteBit(GPIOC, GPIO_Pin_5, s_ucBlink ? Bit_SET : Bit_RESET);
  }

  s_ucDiv++;
  if(s_ucDiv >= 50)
  {
    s_ucDiv = 0;
    Draw();
  }
}

static void OnKeyShort(void)
{
  IncPWMDutyCycle();
  if(s_iDuty < 600)
  {
    s_iDuty = (i16)(s_iDuty + 50);
  }
  printf("[E13] duty %d/600\r\n", s_iDuty);
  Draw();
}

static void OnKeyLong(void)
{
  DecPWMDutyCycle();
  if(s_iDuty > 0)
  {
    s_iDuty = (i16)(s_iDuty - 50);
  }
  printf("[E13] duty %d/600\r\n", s_iDuty);
  Draw();
}

const ExpIf Exp13_If = { "13 PWM", Enter, Exit, Proc2ms, 0, OnKeyShort, OnKeyLong };
