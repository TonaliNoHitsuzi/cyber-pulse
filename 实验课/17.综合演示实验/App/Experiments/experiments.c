/*********************************************************************************************************
* Module Name : experiments.c
* Abstract    : Experiment registry. Circular ring order = experiment number.
*********************************************************************************************************/
#include "experiments.h"

extern const ExpIf Exp01_If;
extern const ExpIf Exp02_If;
extern const ExpIf Exp03_If;
extern const ExpIf Exp04_If;
extern const ExpIf Exp05_If;
extern const ExpIf Exp06_If;
extern const ExpIf Exp07_If;
extern const ExpIf Exp08_If;
extern const ExpIf Exp09_If;
extern const ExpIf Exp10_If;
extern const ExpIf Exp11_If;
extern const ExpIf Exp12_If;
extern const ExpIf Exp13_If;
extern const ExpIf Exp14_If;
extern const ExpIf Exp15_If;
extern const ExpIf Exp16_If;
extern const ExpIf Exp17_If;

const ExpIf* g_arrExp[EXP_NUM] =
{
  &Exp01_If, &Exp02_If, &Exp03_If, &Exp04_If,
  &Exp05_If, &Exp06_If, &Exp07_If, &Exp08_If,
  &Exp09_If, &Exp10_If, &Exp11_If, &Exp12_If,
  &Exp13_If, &Exp14_If, &Exp15_If, &Exp16_If,
  &Exp17_If
};
