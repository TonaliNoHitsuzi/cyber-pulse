/*********************************************************************************************************
* Exp 17 : SNAKE - snake game, experiment 17.
*           State machine:
*             MENU  - control instructions, KEY2 short starts the game.
*             GAME  - full screen game, arrows:
*                     KEY1 = left, KEY3 = right, KEY2 short = up,
*                     external button on PA1 = down.
*                     KEY2 long quits back to the menu.
*             OVER  - died, KEY2 short restarts, KEY2 long back to menu.
*           Score is drawn vertically in the left column.
*           While playing the nav layer hands KEY1/KEY3 over to the game.
*********************************************************************************************************/
#include <stdio.h>
#include <stdlib.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "experiments.h"
#include "nav.h"
#include "Timer.h"
#include "OLED.h"

#define FIELD_X0    16                      /* playfield pixel origin     */
#define FIELD_Y0    16
#define CELL_W      3                       /* cell size in pixels        */
#define FIELD_CW    37                      /* cells across (x)           */
#define FIELD_CH    15                      /* cells down  (y)            */
#define SNAKE_MAX   200

#define DIR_UP      0
#define DIR_DOWN    1
#define DIR_LEFT    2
#define DIR_RIGHT   3

#define ST_MENU     0
#define ST_GAME     1
#define ST_OVER     2

static u8  s_ucState   = ST_MENU;
static u8  s_arrBodyX[SNAKE_MAX];
static u8  s_arrBodyY[SNAKE_MAX];
static u16 s_usHead    = 0;                 /* ring head index            */
static u16 s_usLen     = 0;
static u8  s_ucDir     = DIR_RIGHT;
static u8  s_ucReqDir  = DIR_RIGHT;
static u8  s_ucFoodX   = 20;
static u8  s_ucFoodY   = 7;
static u16 s_usScore   = 0;
static u16 s_usMsPer   = 260;               /* tick interval              */
static u32 s_ulLastTick = 0;

/* external button (PA1) */
static u8  s_ucExtShift  = 0xFF;
static u8  s_ucExtIdle   = 1;
static u8  s_ucExtLearned = 0;

/* on board KEY1 (PC1) and KEY3 (PA0), self scanned for LEFT / RIGHT */
static u8  s_arrArrowShift[2]  = {0xFF, 0xFF};
static u8  s_arrArrowStable[2] = {1, 1};

static void ConfigExtBtn(void);
static void PlaceFood(void);

static void ConfigExtBtn(void)
{
  GPIO_InitTypeDef GPIO_InitStructure;

  RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);

  GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_1;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;
  GPIO_Init(GPIOA, &GPIO_InitStructure);
}

static void ReleaseExtBtn(void)
{
  GPIO_InitTypeDef GPIO_InitStructure;

  GPIO_InitStructure.GPIO_Pin  = GPIO_Pin_1;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;
  GPIO_Init(GPIOA, &GPIO_InitStructure);
}

static void ResetGame(void)
{
  u8  i;
  u16 idx;

  s_usHead = 0;
  s_usLen  = 3;

  for(i = 0; i < 3; i++)                    /* head at right most */
  {
    idx = (u16)((s_usHead + SNAKE_MAX - i) % SNAKE_MAX);
    s_arrBodyX[idx] = (u8)(10 - i);
    s_arrBodyY[idx] = 7;
  }

  s_ucDir    = DIR_RIGHT;
  s_ucReqDir = DIR_RIGHT;
  s_usScore  = 0;
  s_usMsPer  = 260;
  srand(GetMsTick());
  PlaceFood();                              /* avoids spawning on the snake */
}

static void DrawScoreColumn(void)
{
  char buf[6];
  u8   i;
  u8   y;

  sprintf(buf, "%03d", s_usScore > 999 ? 999 : s_usScore);

  y = 17;
  for(i = 0; i < 3; i++)
  {
    OLEDShowChar(5, y, (u8)buf[i], 12, 1);
    y = (u8)(y + 13);
  }
}

static void DrawGame(void)
{
  u16 i;
  u8  x;
  u8  y;
  u8  on;
  u8  idx;

  NavCanvasClear();

  /* playfield border */
  OLEDDrawVLine(15, 16, 61, 1);
  OLEDDrawVLine(127, 16, 61, 1);
  OLEDDrawHLine(61, 16, 127, 1);

  /* food, blinking on absolute phase (independent of redraw timing) */
  on = (u8)((GetMsTick() / 250) & 1);
  if(on)
  {
    OLEDFillRect((u8)(FIELD_X0 + s_ucFoodX * CELL_W),
                 (u8)(FIELD_Y0 + s_ucFoodY * CELL_W),
                 (u8)(FIELD_X0 + s_ucFoodX * CELL_W + 1),
                 (u8)(FIELD_Y0 + s_ucFoodY * CELL_W + 1), 1);
  }

  /* snake body, head is a full 3x3 cell */
  for(i = 0; i < s_usLen; i++)
  {
    idx = (u16)((s_usHead + SNAKE_MAX - i) % SNAKE_MAX);
    x = (u8)(FIELD_X0 + s_arrBodyX[idx] * CELL_W);
    y = (u8)(FIELD_Y0 + s_arrBodyY[idx] * CELL_W);

    if(i == 0)
    {
      OLEDFillRect(x, y, (u8)(x + 2), (u8)(y + 2), 1);
    }
    else
    {
      OLEDFillRect(x, y, (u8)(x + 1), (u8)(y + 1), 1);
    }
  }

  DrawScoreColumn();
  OLEDRefreshGRAM();
}

static void DrawMenu(void)
{
  NavCanvasClear();
  OLEDShowString12(4, 17, (const u8*)"SNAKE", 1);
  OLEDShowString12(4, 29, (const u8*)"K1:L  K3:R", 1);
  OLEDShowString12(4, 39, (const u8*)"K2:U EXT:D", 1);
  OLEDShowString12(4, 49, (const u8*)"K2:GO HOLD:QUIT", 1);
  OLEDRefreshGRAM();
}

static void DrawOver(void)
{
  char buf[16];

  DrawGame();                               /* keep the final scene      */
  OLEDFillRect(30, 24, 110, 52, 1);         /* overlay box               */
  OLEDShowString12(40, 27, (const u8*)"GAME OVER", 0);
  sprintf(buf, "SCORE %03d", s_usScore);
  OLEDShowString12(40, 39, (const u8*)buf, 0);
  OLEDShowString12(37, 49, (const u8*)"K2:AGAIN", 0);
  OLEDRefreshGRAM();
}

static u8 HitSelf(u8 cx, u8 cy)
{
  u16 i;
  u8  idx;

  for(i = 0; i < s_usLen; i++)
  {
    idx = (u16)((s_usHead + SNAKE_MAX - i) % SNAKE_MAX);
    if(s_arrBodyX[idx] == cx && s_arrBodyY[idx] == cy)
    {
      return 1;
    }
  }
  return 0;
}

static void PlaceFood(void)
{
  do
  {
    s_ucFoodX = (u8)(rand() % FIELD_CW);
    s_ucFoodY = (u8)(rand() % FIELD_CH);
  }
  while(HitSelf(s_ucFoodX, s_ucFoodY));
}

static void StartGame(void)
{
  ResetGame();
  s_ucState = ST_GAME;
  NavSetKeysOwned(1);                       /* arrows belong to the game  */
  s_ulLastTick  = GetMsTick();
  DrawGame();
  printf("[E17] game start\r\n");
}

static void BackToMenu(void)
{
  s_ucState = ST_MENU;
  NavSetKeysOwned(0);                       /* nav takes the arrows back  */
  DrawMenu();
  printf("[E17] back to menu\r\n");
}

static void GameTick(void)
{
  u8  nx;
  u8  ny;
  u8  grow;

  /* apply requested direction, no reversing */
  if(!((s_ucReqDir == DIR_UP    && s_ucDir == DIR_DOWN) ||
       (s_ucReqDir == DIR_DOWN  && s_ucDir == DIR_UP)   ||
       (s_ucReqDir == DIR_LEFT  && s_ucDir == DIR_RIGHT)||
       (s_ucReqDir == DIR_RIGHT && s_ucDir == DIR_LEFT)))
  {
    s_ucDir = s_ucReqDir;
  }

  nx = s_arrBodyX[s_usHead];
  ny = s_arrBodyY[s_usHead];

  switch(s_ucDir)
  {
    case DIR_UP:    ny = (u8)(ny - 1); break;
    case DIR_DOWN:  ny = (u8)(ny + 1); break;
    case DIR_LEFT:  nx = (u8)(nx - 1); break;
    default:        nx = (u8)(nx + 1); break;
  }

  /* wall collision */
  if(nx >= FIELD_CW || ny >= FIELD_CH)
  {
    s_ucState = ST_OVER;
    DrawOver();
    printf("[E17] dead, score %d\r\n", s_usScore);
    return;
  }

  /* self collision */
  if(HitSelf(nx, ny))
  {
    s_ucState = ST_OVER;
    DrawOver();
    printf("[E17] dead, score %d\r\n", s_usScore);
    return;
  }

  /* advance head */
  s_usHead = (u16)((s_usHead + 1) % SNAKE_MAX);
  s_arrBodyX[s_usHead] = nx;
  s_arrBodyY[s_usHead] = ny;

  grow = (u8)((nx == s_ucFoodX) && (ny == s_ucFoodY));
  if(grow)
  {
    if(s_usLen < SNAKE_MAX)
    {
      s_usLen++;
    }
    s_usScore++;
    if(s_usMsPer > 120)
    {
      s_usMsPer = (u16)(s_usMsPer - 20);    /* speed up */
    }
    PlaceFood();
    printf("[E17] food! score %d\r\n", s_usScore);
  }
  /* tail pops automatically: the ring only renders s_usLen cells */

  DrawGame();
}

static void Enter(void)
{
  ConfigExtBtn();
  s_ucExtLearned = 0;
  s_ucExtShift   = 0xFF;
  BackToMenu();
}

static void Exit(void)
{
  NavSetKeysOwned(0);
  ReleaseExtBtn();
}

static void Proc2ms(void)
{
  u8 raw;
  u8 stable;
  u8 i;
  u8 arrRaw[2];

  if(s_ucState != ST_GAME)
  {
    return;
  }

  /* on board arrows: KEY1 = PC1 (left), KEY3 = PA0 (right) */
  arrRaw[0] = (u8)GPIO_ReadInputDataBit(GPIOC, GPIO_Pin_1);
  arrRaw[1] = (u8)GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_0);

  for(i = 0; i < 2; i++)
  {
    s_arrArrowShift[i] = (u8)((s_arrArrowShift[i] << 1) | arrRaw[i]);

    if(s_arrArrowShift[i] == 0x00)
    {
      stable = 0;
    }
    else if(s_arrArrowShift[i] == 0xFF)
    {
      stable = 1;
    }
    else
    {
      continue;
    }

    if(stable != s_arrArrowStable[i])
    {
      s_arrArrowStable[i] = stable;

      if(stable == 0)                       /* press edge */
      {
        if(i == 0 && s_ucDir != DIR_RIGHT)
        {
          s_ucReqDir = DIR_LEFT;
        }
        else if(i == 1 && s_ucDir != DIR_LEFT)
        {
          s_ucReqDir = DIR_RIGHT;
        }
      }
    }
  }

  /* external button scan (DOWN) */
  raw = (u8)GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_1);

  if(!s_ucExtLearned)
  {
    s_ucExtIdle    = raw;
    s_ucExtLearned = 1;
  }

  s_ucExtShift = (u8)((s_ucExtShift << 1) | raw);
  if(s_ucExtShift == 0x00)
  {
    stable = 0;
  }
  else if(s_ucExtShift == 0xFF)
  {
    stable = 1;
  }
  else
  {
    stable = 0xFF;
  }

  if(stable != 0xFF && stable != s_ucExtIdle)
  {
    if(s_ucDir != DIR_UP)                   /* no reversing */
    {
      s_ucReqDir = DIR_DOWN;
    }
  }

  /* game tick */
  if((GetMsTick() - s_ulLastTick) >= s_usMsPer)
  {
    s_ulLastTick = GetMsTick();
    GameTick();                             /* redraw also refreshes the blink */
  }
}

static void OnKeyShort(void)
{
  switch(s_ucState)
  {
    case ST_MENU:
      StartGame();
      break;

    case ST_GAME:
      if(s_ucDir != DIR_DOWN)
      {
        s_ucReqDir = DIR_UP;
      }
      break;

    default:                                /* OVER: retry */
      StartGame();
      break;
  }
}

static void OnKeyLong(void)
{
  switch(s_ucState)
  {
    case ST_GAME:
    case ST_OVER:
      BackToMenu();
      break;

    default:
      break;
  }
}

const ExpIf Exp17_If = { "17 SNAKE", Enter, Exit, Proc2ms, 0, OnKeyShort, OnKeyLong };
