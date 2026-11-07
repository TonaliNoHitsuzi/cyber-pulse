/*********************************************************************************************************
* Exp 12 : FLASH - internal flash write / read / erase at 0x0800C000.
*           KEY2 short: cycle menu item (WRITE / READ / ERASE).
*           KEY2 long : execute selected item.
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "OLED.h"
#include "Flash.h"

#define TEST_ADDR   0x0800C000
#define TEST_WORDS  4

static const u32 s_arrPattern[TEST_WORDS] = {0x20261107, 0xA5A55A5A, 0x12345678, 0xDEADBEEF};
static const u32 s_arrErased[TEST_WORDS]  = {0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF};

static u8  s_ucSel = 0;              /* 0 write 1 read 2 erase */
static u32 s_arrRd[TEST_WORDS] = {0};
static u8  s_ucHasData = 0;
static u8  s_ucBusy    = 0;

static void Enter(void)
{
  s_ucSel     = 0;
  s_ucHasData = 0;
  s_ucBusy    = 0;
  printf("[E12] flash test @0x0800C000, K2 short=select, long=run\r\n");
}

static void Exit(void)
{
}

static void Draw(void)
{
  char buf[24];
  u8   i;
  u8   y;

  NavCanvasClear();

  OLEDShowString12(4, 16, (const u8*)"WRITE ", (u8)(s_ucSel == 0 ? 0 : 1));
  OLEDShowString12(46, 16, (const u8*)"READ ", (u8)(s_ucSel == 1 ? 0 : 1));
  OLEDShowString12(82, 16, (const u8*)"ERASE", (u8)(s_ucSel == 2 ? 0 : 1));

  if(s_ucHasData)
  {
    y = 28;
    for(i = 0; i < 2; i++)
    {
      sprintf(buf, "%08lX %08lX", s_arrRd[i * 2], s_arrRd[i * 2 + 1]);
      OLEDShowString12(4, y, (const u8*)buf, 1);
      y = (u8)(y + 11);
    }
  }
  else
  {
    OLEDShowString12(4, 32, (const u8*)"NO DATA YET", 1);
  }

  OLEDShowString12(4, 50, (const u8*)(s_ucBusy ? "RUNNING..." : "K2:SEL / K2x1:RUN"), 1);
  OLEDRefreshGRAM();
}

static void Proc2ms(void)
{
}

static void OnKeyShort(void)
{
  s_ucSel = (u8)((s_ucSel + 1) % 3);
  Draw();
}

static void OnKeyLong(void)
{
  s_ucBusy = 1;
  Draw();

  switch(s_ucSel)
  {
    case 0:
      STM32FlashWriteWord(TEST_ADDR, (u32*)s_arrPattern, TEST_WORDS);
      printf("[E12] wrote 4 words @0x0800C000\r\n");
      break;

    case 1:
      STM32FlashReadWord(TEST_ADDR, s_arrRd, TEST_WORDS);
      s_ucHasData = 1;
      printf("[E12] read: %08lX %08lX %08lX %08lX\r\n",
             s_arrRd[0], s_arrRd[1], s_arrRd[2], s_arrRd[3]);
      break;

    default:
      STM32FlashWriteWord(TEST_ADDR, (u32*)s_arrErased, TEST_WORDS);
      printf("[E12] erased 4 words\r\n");
      break;
  }

  /* LED2 blip */
  GPIO_WriteBit(GPIOC, GPIO_Pin_5, Bit_SET);
  GPIO_WriteBit(GPIOC, GPIO_Pin_5, Bit_RESET);

  s_ucBusy = 0;
  Draw();
}

const ExpIf Exp12_If = { "12 FLASH", Enter, Exit, Proc2ms, 0, OnKeyShort, OnKeyLong };
