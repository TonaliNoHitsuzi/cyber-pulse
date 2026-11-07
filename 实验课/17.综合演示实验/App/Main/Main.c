/*********************************************************************************************************
* Module Name : Main.c
* Abstract    : Integrated demo firmware main. Initializes the board, the host
*               protocol and the navigation system, then runs the 2ms / 1s
*               foreground-background scheduler.
*********************************************************************************************************/

/*********************************************************************************************************
*                                              include files
*********************************************************************************************************/
#include "Main.h"
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "NVIC.h"
#include "SysTick.h"
#include "RCC.h"
#include "Timer.h"
#include "UART1.h"
#include "LED.h"
#include "OLED.h"
#include "experiments.h"
#include "nav.h"
#include "hostif.h"

/*********************************************************************************************************
*                                              main
*********************************************************************************************************/
static void InitHardware(void)
{
  SystemInit();
  InitRCC();
  InitNVIC();
  InitUART1(115200);
  InitTimer();          /* framework.c: TIM2 based 2ms/1s flags, TIM5 kept free */
  InitLED();
  InitSysTick();
  InitOLED();
}

int main(void)
{
  InitHardware();

  printf("\r\n=== STM32F103 Integrated Demo v1.0 ===\r\n");
  printf("16 experiments, KEY1:prev KEY3:next KEY2:interact\r\n");

  HostIfInit();
  InitNav();            /* enters experiment 01 */

  while(1)
  {
    if(Get2msFlag())
    {
      Clr2msFlag();

      HostIfProc2ms();  /* host protocol rx polling          */
      NavProc2ms();     /* key scan, switch animation        */

      if(g_arrExp[GetCurExpIdx()]->Proc2ms != 0)
      {
        g_arrExp[GetCurExpIdx()]->Proc2ms();
      }
    }

    if(Get1SecFlag())
    {
      Clr1SecFlag();

      NavProc1Sec();    /* IWDG latch feeding                */

      if(g_arrExp[GetCurExpIdx()]->Proc1Sec != 0)
      {
        g_arrExp[GetCurExpIdx()]->Proc1Sec();
      }
    }
  }
}
