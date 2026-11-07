/*********************************************************************************************************
* Module Name: Main.c
* Abstract    : External button test. 3-pin button module: VCC/GND wired, SIG -> PA1.
*               LED1 (PC4) lights while button pressed. LED2 (PC5) mirrors raw PA1 level.
*               Idle level is auto-learned at boot (button assumed released), so both
*               press-to-GND and press-to-VCC modules work without code change.
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

/*********************************************************************************************************
*                                              internal variables
*********************************************************************************************************/
static u8 s_ucIdleLevel = 0;   /* PA1 level when released, learned at boot          */
static u8 s_ucLearned   = 0;   /* idle level learned flag                           */
static u8 s_ucPressed   = 0;   /* debounced pressed state                           */
static u8 s_ucShift     = 0;   /* shift register, 4 consecutive same samples = stable */

/*********************************************************************************************************
*                                              internal function prototypes
*********************************************************************************************************/
static void InitHardware(void);
static void ConfigBtnExtGPIO(void);
static void Proc2msTask(void);
static void Proc1SecTask(void);

/*********************************************************************************************************
*                                              internal function implementation
*********************************************************************************************************/
static void ConfigBtnExtGPIO(void)
{
  GPIO_InitTypeDef GPIO_InitStructure;

  RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);

  GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_1;              /* SIG wire from button module */
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;   /* module drives the line       */
  GPIO_Init(GPIOA, &GPIO_InitStructure);
}

static void InitHardware(void)
{
  SystemInit();
  InitRCC();
  InitNVIC();
  InitUART1(115200);
  InitTimer();
  InitLED();
  InitSysTick();
  ConfigBtnExtGPIO();
}

static void Proc2msTask(void)
{
  u8 raw;
  u8 stable;

  if(!Get2msFlag())
  {
    return;
  }
  Clr2msFlag();

  raw = (u8)GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_1);

  if(!s_ucLearned)          /* learn idle level once (button assumed released at boot) */
  {
    s_ucIdleLevel = raw;
    s_ucLearned   = 1;
    printf("[BTN] idle level = %d\r\n", s_ucIdleLevel);
  }

  s_ucShift = (u8)((s_ucShift << 1) | raw);   /* debounce: 8 samples @2ms */
  if(s_ucShift == 0x00)
  {
    stable = 0;
  }
  else if(s_ucShift == 0xFF)
  {
    stable = 1;
  }
  else
  {
    return;                 /* level not stable yet */
  }

  if((u8)(stable != s_ucIdleLevel) != s_ucPressed)
  {
    s_ucPressed = (u8)(stable != s_ucIdleLevel);
    printf("[BTN] level=%d %s\r\n", stable, s_ucPressed ? "PRESSED" : "RELEASED");
  }

  /* LED1 (PC4, active low): ON while pressed */
  GPIO_WriteBit(GPIOC, GPIO_Pin_4, s_ucPressed ? Bit_RESET : Bit_SET);

  /* LED2 (PC5): mirrors raw PA1 level */
  GPIO_WriteBit(GPIOC, GPIO_Pin_5, stable ? Bit_SET : Bit_RESET);
}

static void Proc1SecTask(void)
{
  if(Get1SecFlag())
  {
    Clr1SecFlag();
  }
}

/*********************************************************************************************************
*                                              main
*********************************************************************************************************/
int main(void)
{
  InitHardware();

  printf("External button test on PA1. Press the button...\r\n");

  while(1)
  {
    Proc2msTask();
    Proc1SecTask();
  }
}
