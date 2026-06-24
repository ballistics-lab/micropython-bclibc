#ifndef _MPY_MATH_SHADOW_H
#define _MPY_MATH_SHADOW_H

/* musl libm_dbl declares __sin(double,double,int), __cos(double,double),
 * __tan(double,double,int) as internal kernel helpers.
 * glibc's <math.h> also declares __sin(double), __cos(double), __tan(double)
 * as hidden aliases — different signatures, causing a conflicting-types error.
 *
 * Intercept <math.h> via -I priority: temporarily rename glibc's hidden
 * aliases while processing the real header, then undo so libm.h can declare
 * the musl kernel prototypes without conflict. */

#define __sin _glibc_sin1arg
#define __cos _glibc_cos1arg
#define __tan _glibc_tan1arg

#include_next <math.h>

#undef __sin
#undef __cos
#undef __tan

#endif /* _MPY_MATH_SHADOW_H */
