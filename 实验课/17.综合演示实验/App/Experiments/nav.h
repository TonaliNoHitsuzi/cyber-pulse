/*********************************************************************************************************
* Module Name : nav.h
* Abstract    : Navigation layer. KEY1 = previous experiment, KEY3 = next
*               experiment (circular ring), KEY2 = interaction key of the active
*               experiment (short / long). Switching an experiment is a full
*               reset: Exit() of the old one, Enter() of the new one.
*********************************************************************************************************/
#ifndef _NAV_H_
#define _NAV_H_

#include "DataType.h"

void  InitNav(void);
void  NavProc2ms(void);
void  NavProc1Sec(void);

/* helpers for experiments */
void  NavCanvasClear(void);          /* clear the canvas area (y 16..63) in GRAM only */
void  NavSetLogSilent(u8 on);        /* 15/16 silence text logs for host protocol     */
u8    NavIsLogSilent(void);
void  NavExpPrintf(const char* p);   /* print with silent flag respected, line given by caller */

void  NavNotifyIwdgArmed(void);  //exp 11 latch: nav starts auto-feeding

void  NavRemoteSwitch(u8 idx);   //host protocol SET_EXP: jump to experiment idx (0..15)

void  NavSetKeysOwned(u8 on);     /* 1 = exp owns KEY1/KEY3, nav stops switching */

#endif
