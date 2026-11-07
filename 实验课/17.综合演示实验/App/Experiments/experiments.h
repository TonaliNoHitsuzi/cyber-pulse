/*********************************************************************************************************
* Module Name : experiments.h
* Abstract    : Experiment plugin interface for the integrated demo firmware.
*               Each experiment is one .c file providing a const ExpIf struct.
*               The navigation layer walks the registry as a circular ring.
*********************************************************************************************************/
#ifndef _EXPERIMENTS_H_
#define _EXPERIMENTS_H_

#include "DataType.h"

typedef struct
{
  const char* name;              /* short English title shown in the top bar  */
  void (*Enter)(void);           /* take hardware, reset state                 */
  void (*Exit)(void);            /* release hardware (deinit everything)       */
  void (*Proc2ms)(void);         /* called every 2ms while active              */
  void (*Proc1Sec)(void);        /* called every 1s while active               */
  void (*OnKeyShort)(void);      /* KEY2 short press  (<500ms)                 */
  void (*OnKeyLong)(void);       /* KEY2 long press  (>=500ms, single fire)    */
}ExpIf;

#define EXP_NUM  17

extern const ExpIf* g_arrExp[EXP_NUM];

u8   GetCurExpIdx(void);

#endif
