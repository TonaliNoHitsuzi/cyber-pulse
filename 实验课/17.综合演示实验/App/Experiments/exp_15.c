/*********************************************************************************************************
* Exp 15 : DAC - waveform output on PA4 (10 Hz, 100 points per cycle).
*           KEY2 short: cycle wave SINE / TRI / RECT.  KEY2 long: output on/off.
*           The preview on the canvas is plotted from the real wave table.
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "Timer.h"
#include "OLED.h"
#include "DAC.h"
#include "Wave.h"
#include "hostif.h"

static u8 s_ucWave = 0;              /* 0 sine 1 tri 2 rect */
static u8 s_ucOn   = 1;

static const char* s_arrName[3] = {"SINE", "TRI ", "RECT"};

static void ApplyWave(void)
{
  StructDACWave wave;

  switch(s_ucWave)
  {
    case 0:  wave.waveBufAddr = (u32)GetSineWave100PointAddr(); break;
    case 1:  wave.waveBufAddr = (u32)GetTriWave100PointAddr();  break;
    default: wave.waveBufAddr = (u32)GetRectWave100PointAddr(); break;
  }
  wave.waveBufSize = 100;
  SetDACWave(wave);
}

static void Enter(void)
{
  s_ucWave = 0;
  s_ucOn   = 1;
  InitWave();
  InitDAC();
  ApplyWave();
  printf("[E15] DAC sine 10Hz on PA4\r\n");
}

static void Exit(void)
{
  GPIO_InitTypeDef GPIO_InitStructure;

  TIM_DeInit(TIM4);
  RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM4, DISABLE);

  DAC_Cmd(DAC_Channel_1, DISABLE);
  DAC_DMACmd(DAC_Channel_1, DISABLE);
  RCC_APB1PeriphClockCmd(RCC_APB1Periph_DAC, DISABLE);

  GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_4;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPU;
  GPIO_Init(GPIOA, &GPIO_InitStructure);
}

static void Draw(void)
{
  u16* pTable;
  char buf[24];
  u8   i;
  u8   x;
  u8   y;
  u16  v;

  switch(s_ucWave)
  {
    case 0:  pTable = (u16*)GetSineWave100PointAddr(); break;
    case 1:  pTable = (u16*)GetTriWave100PointAddr();  break;
    default: pTable = (u16*)GetRectWave100PointAddr(); break;
  }

  NavCanvasClear();
  OLEDShowString12(4, 16, (const u8*)"DAC 10Hz PA4", 1);
  sprintf(buf, "%s  %s", s_arrName[s_ucWave], s_ucOn ? "ON " : "OFF");
  OLEDShowString12(4, 28, (const u8*)buf, 1);

  /* live preview from the actual table */
  OLEDFillRect(2, 38, 125, 58, 0);
  for(i = 0; i < 100; i++)
  {
    v = pTable[i];
    x = (u8)(4 + i);
    y = (u8)(56 - ((v * 18UL) / 4095UL));
    OLEDDrawPointEx(x, y, 1);
  }
  OLEDRefreshGRAM();
}

static void Proc2ms(void)
{
  u8  wave;
  static u8 s_ucBlink  = 0;
  static u8 s_ucBlinkC = 0;

  /* remote wave select from host protocol */
  if(HostIfPollGenWave(&wave))
  {
    s_ucWave = wave;
    if(s_ucOn)
    {
      ApplyWave();
    }
    printf("[E15] remote wave %s\r\n", s_arrName[s_ucWave]);
    Draw();
  }

  if(s_ucOn)
  {
    s_ucBlinkC++;
    if(s_ucBlinkC >= 250)
    {
      s_ucBlinkC = 0;
      s_ucBlink  = (u8)!s_ucBlink;
      GPIO_WriteBit(GPIOC, GPIO_Pin_5, s_ucBlink ? Bit_SET : Bit_RESET);
    }
  }
  else
  {
    GPIO_WriteBit(GPIOC, GPIO_Pin_5, Bit_RESET);
  }
}

static void OnKeyShort(void)
{
  s_ucWave = (u8)((s_ucWave + 1) % 3);
  ApplyWave();
  printf("[E15] wave %s\r\n", s_arrName[s_ucWave]);
  Draw();
}

static void OnKeyLong(void)
{
  s_ucOn = (u8)!s_ucOn;
  if(s_ucOn)
  {
    ApplyWave();
  }
  else
  {
    TIM_Cmd(TIM4, DISABLE);
    DAC_SetChannel1Data(DAC_Align_12b_R, 0);
  }
  printf("[E15] output %s\r\n", s_ucOn ? "on" : "off");
  Draw();
}

const ExpIf Exp15_If = { "15 DAC", Enter, Exit, Proc2ms, 0, OnKeyShort, OnKeyLong };
