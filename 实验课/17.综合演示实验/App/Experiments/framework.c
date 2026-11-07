/*********************************************************************************************************
* Module Name : framework.c
* Abstract    : System tick replacement. The original Timer.c used TIM2 for the
*               2ms flag AND TIM5 for the 1s flag. TIM5 is reserved for the input
*               capture experiment (exp 14), so this module drives both flags from
*               TIM2 only (1ms interrupt, software divider). Same API as Timer.h.
*********************************************************************************************************/
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "Timer.h"

static volatile u8  s_i2msFlag  = FALSE;
static volatile u8  s_i1secFlag = FALSE;
static volatile u32 s_ulMsTick  = 0;         /* free running millisecond counter */

void TIM2_IRQHandler(void)
{
  static u16 s_iCnt2    = 0;
  static u16 s_iCnt1000 = 0;

  if(TIM_GetITStatus(TIM2, TIM_IT_Update) == SET)
  {
    TIM_ClearITPendingBit(TIM2, TIM_FLAG_Update);
  }

  s_ulMsTick++;

  s_iCnt2++;
  if(s_iCnt2 >= 2)
  {
    s_iCnt2    = 0;
    s_i2msFlag = TRUE;
  }

  s_iCnt1000++;
  if(s_iCnt1000 >= 1000)
  {
    s_iCnt1000 = 0;
    s_i1secFlag = TRUE;
  }
}

void InitTimer(void)
{
  TIM_TimeBaseInitTypeDef TIM_TimeBaseStructure;
  NVIC_InitTypeDef        NVIC_InitStructure;

  RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2, ENABLE);

  /* 72MHz / (71+1) = 1MHz, period 1000 -> 1ms */
  TIM_TimeBaseStructure.TIM_Period        = 999;
  TIM_TimeBaseStructure.TIM_Prescaler     = 71;
  TIM_TimeBaseStructure.TIM_ClockDivision = 0;
  TIM_TimeBaseStructure.TIM_CounterMode   = TIM_CounterMode_Up;
  TIM_TimeBaseInit(TIM2, &TIM_TimeBaseStructure);

  TIM_ITConfig(TIM2, TIM_IT_Update, ENABLE);

  NVIC_InitStructure.NVIC_IRQChannel                   = TIM2_IRQn;
  NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 0;
  NVIC_InitStructure.NVIC_IRQChannelSubPriority        = 3;
  NVIC_InitStructure.NVIC_IRQChannelCmd                = ENABLE;
  NVIC_Init(&NVIC_InitStructure);

  TIM_Cmd(TIM2, ENABLE);
}

u8  Get2msFlag(void)               { return s_i2msFlag;   }
void Clr2msFlag(void)              { s_i2msFlag = FALSE;  }
u8  Get1SecFlag(void)              { return s_i1secFlag;  }
void Clr1SecFlag(void)             { s_i1secFlag = FALSE; }
u32 GetMsTick(void)                { return s_ulMsTick;   }
