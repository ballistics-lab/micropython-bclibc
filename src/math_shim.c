/* sincosf / sincos shim.
 * GCC -O2 merges adjacent sinf()+cosf() / sin()+cos() calls into a single
 * sincosf / sincos call (GNU extension absent from fdlibm / musl libm_dbl).
 * -O0 prevents the compiler from doing the same to this wrapper itself,
 * which would cause infinite recursion. */
#pragma GCC optimize("O0")
#include <math.h>

#if defined(TINY_BCLIBC_SINGLE_PRECISION)
void sincosf(float x, float *s, float *c)
{
    *s = sinf(x);
    *c = cosf(x);
}
#else
void sincos(double x, double *s, double *c)
{
    *s = sin(x);
    *c = cos(x);
}
#endif
