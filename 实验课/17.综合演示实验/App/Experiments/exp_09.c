/*********************************************************************************************************
* Exp 09 : EXTI - external interrupt demo. KEY2 (PC2) is wired to EXTI line 2,
*           every falling edge counts and toggles LED1. Navigation still works
*           through KEY1 / KEY3.
*           KEY2 long: clear counter.
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "OLED.h"

static volatile u16 s_usCount = 0;

static void ConfigExti(void)
{
  EXTI_InitTypeDef EXTI_InitStructure;
  NVIC_InitTypeDef NVIC_InitStructure;

  RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOC, ENABLE);
  RCC_APB2PeriphClockCmd(RCC_APB2Periph_AFIO, ENABLE);

  GPIO_EXTILineConfig(GPIO_PortSourceGPIOC, GPIO_PinSource2);

  EXTI_InitStructure.EXTI_Line    = EXTI_Line2;
  EXTI_InitStructure.EXTI_Mode   = EXTI_Mode_Interrupt;
  EXTI_InitStructure.EXTI_Trigger = EXTI_Trigger_Falling;
  EXTI_InitStructure.EXTI_LineCmd = ENABLE;
  EXTI_Init(&EXTI_InitStructure);

  NVIC_InitStructure.NVIC_IRQChannel                   = EXTI2_IRQn;
  NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 2;
  NVIC_InitStructure.NVIC_IRQChannelSubPriority        = 0;
  NVIC_InitStructure.NVIC_IRQChannelCmd                = ENABLE;
  NVIC_Init(&NVIC_InitStructure);
}

void EXTI2_IRQHandler(void)
{
  if(EXTI_GetITStatus(EXTI_Line2) != RESET)
  {
    EXTI_ClearITPendingBit(EXTI_Line2);
    s_usCount++;
    GPIO_WriteBit(GPIOC, GPIO_Pin_4,
      GPIO_ReadOutputDataBit(GPIOC, GPIO_Pin_4) ? Bit_RESET : Bit_SET);
  }
}

static void Enter(void)
{
  s_usCount = 0;
  GPIO_WriteBit(GPIOC, GPIO_Pin_4, Bit_SET);
  ConfigExti();
  printf("[E09] EXTI2 on KEY2 armed\r\n");
}

static void Exit(void)
{
  EXTI_InitTypeDef EXTI_InitStructure;

  EXTI_DeInit();

  EXTI_InitStructure.EXTI_Line    = EXTI_Line2;
  EXTI_InitStructure.EXTI_Mode    = EXTI_Mode_Interrupt;
  EXTI_InitStructure.EXTI_Trigger = EXTI_Trigger_Rising_Falling;
  EXTI_InitStructure.EXTI_LineCmd = DISABLE;
  EXTI_Init(&EXTI_InitStructure);
}

static void Draw(void)
{
  char buf[16];

  NavCanvasClear();
  OLEDShowString12(4, 18, (const u8*)"KEY2 -> EXTI2", 1);
  sprintf(buf, "%d", s_usCount);
  OLEDShowString(48, 32, (const u8*)buf);
  OLEDShowString12(4, 48, (const u8*)"FALLING EDGE COUNT", 1);
  OLEDRefreshGRAM();
}

static void Proc2ms(void)
{
  static u16 s_usLast = 0xFFFF;
  static u8  s_ucDiv  = 0;

  s_ucDiv++;
  if(s_ucDiv >= 50 || s_usCount != s_usLast)
  {
    s_ucDiv  = 0;
    s_usLast = s_usCount;
    Draw();
  }
}

static void OnKeyShort(void)
{
  /* the press itself is the demo event, nothing extra to do */
}

static void OnKeyLong(void)
{
  s_usCount = 0;
  printf("[E09] counter cleared\r\n");
  Draw();
}

const ExpIf Exp09_If = { "09 EXTI", Enter, Exit, Proc2ms, 0, OnKeyShort, OnKeyLong };
