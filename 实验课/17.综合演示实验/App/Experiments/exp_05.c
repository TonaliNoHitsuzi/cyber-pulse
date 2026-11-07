/*********************************************************************************************************
* Exp 05 : ECHO - uart loopback. Everything received on UART1 is echoed back.
*           KEY2 short: send a test line.  KEY2 long: clear counters.
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "OLED.h"
#include "UART1.h"

static u32 s_ulRx = 0;
static u32 s_ulTx = 0;

static void Enter(void)
{
  s_ulRx = 0;
  s_ulTx = 0;
  printf("[E05] echo mode, send anything\r\n");
}

static void Exit(void)
{
}

static void Draw(void)
{
  char buf[24];

  NavCanvasClear();
  OLEDShowString12(4, 18, (const u8*)"UART ECHO", 1);
  sprintf(buf, "RX: %lu", s_ulRx);
  OLEDShowString12(4, 32, (const u8*)buf, 1);
  sprintf(buf, "TX: %lu", s_ulTx);
  OLEDShowString12(4, 44, (const u8*)buf, 1);
  OLEDRefreshGRAM();
}

static void Proc2ms(void)
{
  u8 buf[16];
  u8 n;
  static u8 s_ucDrawDiv = 0;

  n = ReadUART1(buf, 16);
  if(n > 0)
  {
    s_ulRx += n;
    s_ulTx += WriteUART1(buf, n);
    GPIO_WriteBit(GPIOC, GPIO_Pin_5, Bit_SET);
  }
  else
  {
    GPIO_WriteBit(GPIOC, GPIO_Pin_5, Bit_RESET);
  }

  s_ucDrawDiv++;
  if(s_ucDrawDiv >= 50)
  {
    s_ucDrawDiv = 0;
    Draw();
  }
}

static void OnKeyShort(void)
{
  s_ulTx += (u32)WriteUART1((u8*)"[E05] ping\r\n", 12);
  Draw();
}

static void OnKeyLong(void)
{
  s_ulRx = 0;
  s_ulTx = 0;
  Draw();
}

const ExpIf Exp05_If = { "05 ECHO", Enter, Exit, Proc2ms, 0, OnKeyShort, OnKeyLong };
