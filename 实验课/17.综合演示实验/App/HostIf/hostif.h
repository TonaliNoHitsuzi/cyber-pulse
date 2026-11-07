/*********************************************************************************************************
* Module Name : hostif.h
* Abstract    : Host PC protocol. Compatible with the experiment 15/16 framing:
*               10 byte frames, module id < 0x80, all other bytes have MSB set,
*               a bit-stuffed head byte and a modulo-128 checksum.
*               New commands (module 0x01 SYS):
*                 0x82 GET_EXP   -> replies current experiment number (1..16)
*                 0x83 SET_EXP   -> data[0] = 1..16 switches experiment
*                 0x84 TELEM     -> data[0] = 0 off / 1 on (14/15/16 streams)
*               Original command kept:
*                 0x71 WAVE / 0x80 GEN_WAVE -> data[0] 0 sine 1 tri 2 rect
*********************************************************************************************************/
#ifndef _HOSTIF_H_
#define _HOSTIF_H_

#include "DataType.h"

void  HostIfInit(void);
void  HostIfProc2ms(void);                 /* poll uart rx and parse           */

u8    HostIfTelemIsOn(void);

/* send helpers (frame + push to uart) */
void  HostIfSendWave5(u8* p5);             /* 5 byte wave payload              */
void  HostIfSendInfo(u8 b0, u8 b1);        /* generic info payload             */

u8    HostIfPollGenWave(u8* pWave);  //exp 15 polls remote wave select

#endif
