/*********************************************************************************************************
* Module Name : hostif.c
* Abstract    : Host protocol implementation, byte stream state machine fed by
*               polling ReadUART1 every 2ms (no ISR hooks needed).
*               Framing copied from the course PackUnpack module:
*               frame = [id(<0x80)] [head] [sid] [data0..5] [sum]  = 10 bytes
*               Every byte except the id has MSB forced to 1; the stolen MSBs
*               travel in the head byte (bit0 = sid, bit1..6 = data0..data5).
*               Payload values must fit 7 bits each (caller responsibility,
*               builder masks defensively).
*********************************************************************************************************/
#include <stdio.h>
#include "stm32f10x_conf.h"
#include "DataType.h"
#include "hostif.h"
#include "UART1.h"
#include "experiments.h"
#include "nav.h"

#define MOD_SYS   0x01
#define MOD_WAVE  0x71

#define SID_ACK   0x04
#define SID_GETE  0x82
#define SID_SETE  0x83
#define SID_TELEM 0x84
#define SID_GENW  0x80

#define ACK_OK     0
#define ACK_PARAM  4
#define ACK_NOTACC 5

static u8  s_ucTelem = 0;
static u8  s_arrRxBuf[10];
static u8  s_ucRxLen   = 0;
static u8  s_ucInFrame = 0;

static u8  s_arrTxBuf[10];

static volatile u8 s_ucGenWaveReq = 0;
static volatile u8 s_ucGenWaveVal = 0;

/* --- frame builder ------------------------------------------------------- */
static void BuildAndSend(u8 mod, u8 sid, const u8* pData6)
{
  u8  checkSum;
  u8  dataHead;
  u8  i;
  i16 j;

  s_arrTxBuf[0] = mod;
  s_arrTxBuf[2] = (u8)((sid & 0x7F) | 0x80);
  for(i = 0; i < 6; i++)
  {
    s_arrTxBuf[3 + i] = (u8)((pData6[i] & 0x7F) | 0x80);
  }

  /* head: bit0 = sid MSB, bit1..bit6 = data0..data5 MSBs */
  dataHead = 0;
  for(j = 5; j >= 0; j--)              /* data5 first so it lands on bit6 */
  {
    dataHead = (u8)((dataHead << 1) | (u8)((pData6[j] & 0x80) >> 7));
  }
  dataHead = (u8)((dataHead << 1) | (u8)((sid & 0x80) >> 7));
  s_arrTxBuf[1] = (u8)(dataHead | 0x80);

  checkSum = s_arrTxBuf[0];
  for(i = 1; i < 9; i++)
  {
    checkSum = (u8)(checkSum + s_arrTxBuf[i]);
  }
  s_arrTxBuf[9] = (u8)((checkSum & 0x7F) | 0x80);

  WriteUART1(s_arrTxBuf, 10);
}

/* --- frame parser ------------------------------------------------------- */
static u8 ParseFrame(u8* p)            /* p[0..9], returns 1 when checksum ok */
{
  u8 checkSum;
  u8 dataHead;
  u8 i;

  checkSum = p[0];
  checkSum = (u8)(checkSum + p[1]);    /* raw wire byte, MSB included */
  dataHead = (u8)(p[1] & 0x7F);

  for(i = 2; i < 9; i++)
  {
    checkSum = (u8)(checkSum + p[i]);
    p[i] = (u8)((p[i] & 0x7F) | (u8)((dataHead & 0x01) << 7));
    dataHead = (u8)(dataHead >> 1);
  }

  if((u8)(checkSum & 0x7F) != (u8)(p[9] & 0x7F))
  {
    return 0;
  }
  return 1;
}

static void SendAck(u8 mod, u8 sid, u8 ack)
{
  u8 data[6];

  data[0] = mod;
  data[1] = sid;
  data[2] = ack;
  data[3] = 0;
  data[4] = 0;
  data[5] = 0;
  BuildAndSend(MOD_SYS, SID_ACK, data);
}

static void HandleFrame(u8* p)
{
  u8  data[6];
  u8  cur;
  u8  target;

  cur = (u8)(GetCurExpIdx() + 1);      /* 1..16 */

  switch(p[0])
  {
    case MOD_SYS:
      switch(p[2])
      {
        case SID_GETE:
          data[0] = cur;
          data[1] = 0; data[2] = 0; data[3] = 0; data[4] = 0; data[5] = 0;
          BuildAndSend(MOD_SYS, SID_GETE, data);
          break;

        case SID_SETE:
          target = p[3];
          if(target >= 1 && target <= EXP_NUM)
          {
            SendAck(MOD_SYS, SID_SETE, ACK_OK);
            NavRemoteSwitch((u8)(target - 1));
          }
          else
          {
            SendAck(MOD_SYS, SID_SETE, ACK_PARAM);
          }
          break;

        case SID_TELEM:
          s_ucTelem = (u8)(p[3] ? 1 : 0);
          SendAck(MOD_SYS, SID_TELEM, ACK_OK);
          break;

        default:
          SendAck(MOD_SYS, p[2], ACK_NOTACC);
          break;
      }
      break;

    case MOD_WAVE:
      if(p[2] == SID_GENW)
      {
        if(cur == 15 && p[3] <= 2)
        {
          s_ucGenWaveVal = p[3];
          s_ucGenWaveReq = 1;
          SendAck(MOD_WAVE, SID_GENW, ACK_OK);
        }
        else
        {
          SendAck(MOD_WAVE, SID_GENW, ACK_NOTACC);
        }
      }
      else
      {
        SendAck(MOD_WAVE, p[2], ACK_NOTACC);
      }
      break;

    default:
      break;
  }
}

/* --- public API --------------------------------------------------------- */
void HostIfInit(void)
{
  s_ucTelem    = 0;
  s_ucRxLen    = 0;
  s_ucInFrame  = 0;
  s_ucGenWaveReq = 0;
}

void HostIfProc2ms(void)
{
  u8 buf[20];
  u8 n;
  u8 i;
  u8 b;

  /* experiment 05 owns the uart for its echo demo, do not steal its bytes */
  if(GetCurExpIdx() == 4)
  {
    return;
  }

  n = ReadUART1(buf, 20);
  for(i = 0; i < n; i++)
  {
    b = buf[i];

    if(!s_ucInFrame)
    {
      if(b < 0x80)                     /* module id byte starts a frame */
      {
        s_arrRxBuf[0] = b;
        s_ucRxLen     = 1;
        s_ucInFrame   = 1;
      }
    }
    else
    {
      if(b < 0x80)                     /* unexpected id byte: restart */
      {
        s_arrRxBuf[0] = b;
        s_ucRxLen     = 1;
        continue;
      }

      if(s_ucRxLen < 10)
      {
        s_arrRxBuf[s_ucRxLen++] = b;
      }

      if(s_ucRxLen == 10)
      {
        s_ucInFrame = 0;
        if(ParseFrame(s_arrRxBuf))
        {
          HandleFrame(s_arrRxBuf);
        }
      }
    }
  }
}

u8 HostIfTelemIsOn(void)
{
  return s_ucTelem;
}

u8 HostIfPollGenWave(u8* pWave)
{
  if(s_ucGenWaveReq)
  {
    s_ucGenWaveReq = 0;
    *pWave = s_ucGenWaveVal;
    return 1;
  }
  return 0;
}

void HostIfSendWave5(u8* p5)
{
  u8 data[6];

  data[0] = (u8)(p5[0] & 0x7F);
  data[1] = (u8)(p5[1] & 0x7F);
  data[2] = (u8)(p5[2] & 0x7F);
  data[3] = (u8)(p5[3] & 0x7F);
  data[4] = (u8)(p5[4] & 0x7F);
  data[5] = 0;
  BuildAndSend(MOD_WAVE, 0x02, data);
}

void HostIfSendInfo(u8 b0, u8 b1)
{
  u8 data[6];

  data[0] = (u8)(b0 & 0x7F);
  data[1] = (u8)(b1 & 0x7F);
  data[2] = 0; data[3] = 0; data[4] = 0; data[5] = 0;
  BuildAndSend(MOD_SYS, 0x02, data);
}
