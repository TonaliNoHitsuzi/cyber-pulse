/*********************************************************************************************************
* Exp 07 : SYSTICK - precise delay demo. A fixed 500ms burst toggles LED1 with
*           SysTick based DelayNus at the selected frequency, then the real
*           number of edges is reported.
*           Freq steps: 2 Hz (visible), 1 kHz, 10 kHz.
*           KEY2 short: next frequency and run burst.  KEY2 long: rerun.
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "SysTick.h"
#include "OLED.h"

static const char* s_arrName[3] = {"2 Hz ", "1 kHz", "10kHz"};
static const u32   s_arrFreq[3] = {2, 1000, 10000};

static u8  s_ucFreqIdx = 0;
static u16 s_iEdges    = 0;
static u8  s_ucBusy    = 0;

static void Enter(void)
{
  s_ucFreqIdx = 0;
  s_iEdges    = 0;
  s_ucBusy    = 0;
}

static void Exit(void)
{
}

static void Draw(void)
{
  char buf[24];

  NavCanvasClear();
  OLEDShowString12(4, 18, (const u8*)"SYSTICK DELAY", 1);
  sprintf(buf, "FREQ : %s", s_arrName[s_ucFreqIdx]);
  OLEDShowString12(4, 32, (const u8*)buf, 1);
  sprintf(buf, "EDGE : %d", s_iEdges);
  OLEDShowString12(4, 44, (const u8*)buf, 1);
  OLEDShowString12(4, 52, (const u8*)(s_ucBusy ? "RUNNING..." : "K2: RUN"), 1);
  OLEDRefreshGRAM();
}

static void RunBurst(void)
{
  u32 halfUs;
  u32 edges;
  u32 i;

  s_ucBusy = 1;
  Draw();

  halfUs = 500000UL / s_arrFreq[s_ucFreqIdx];   /* half period in us */
  edges  = (s_arrFreq[s_ucFreqIdx] / 2) / 2;    /* edges inside 500ms window */
  if(edges < 1)
  {
    edges = 1;
  }

  for(i = 0; i < edges; i++)
  {
    GPIO_WriteBit(GPIOC, GPIO_Pin_4,
      GPIO_ReadOutputDataBit(GPIOC, GPIO_Pin_4) ? Bit_RESET : Bit_SET);
    DelayNus(halfUs);
  }

  s_iEdges = (u16)edges;
  s_ucBusy = 0;
  GPIO_WriteBit(GPIOC, GPIO_Pin_4, Bit_SET);
  printf("[E07] freq %lu Hz, %d edges in 500ms\r\n", s_arrFreq[s_ucFreqIdx], s_iEdges);
  Draw();
}

static void Proc2ms(void)
{
}

static void OnKeyShort(void)
{
  s_ucFreqIdx = (u8)((s_ucFreqIdx + 1) % 3);
  RunBurst();
}

static void OnKeyLong(void)
{
  RunBurst();
}

const ExpIf Exp07_If = { "07 SYSTICK", Enter, Exit, Proc2ms, 0, OnKeyShort, OnKeyLong };
