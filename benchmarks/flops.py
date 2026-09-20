import time
import machine

# 500,000 iterations * 10 FPU instructions = 5,000,000 FLOPs (5 MFLOPs)
ITERATIONS = 500_000


# Direct FPU instructions for ARM Thumb-2 (Cortex-M33)
@micropython.asm_thumb
def benchmark_fpu_asm(r0):
    # r0 accepts the number of iterations (ITERATIONS)

    # Creating a loop label
    label(LOOP)

    # 10 consecutive hardware additions in the FPU
    vadd(s0, s0, s1)
    vadd(s0, s0, s1)
    vadd(s0, s0, s1)
    vadd(s0, s0, s1)
    vadd(s0, s0, s1)
    vadd(s0, s0, s1)
    vadd(s0, s0, s1)
    vadd(s0, s0, s1)
    vadd(s0, s0, s1)
    vadd(s0, s0, s1)

    # Decrement loop counter r0 = r0 - 1
    sub(r0, 1)
    # Jump to LOOP if r0 != 0
    bne(LOOP)


print("--- RP2350 MicroPython Hardware FPU Benchmark ---")
print(f"CPU Freq: {machine.freq() / 1_000_000:.1f} MHz")

# Time measurement
start_us = time.ticks_us()
benchmark_fpu_asm(ITERATIONS)
end_us = time.ticks_us()

# Calculation
duration_us = time.ticks_diff(end_us, start_us)
seconds = duration_us / 1_000_000
total_flops = ITERATIONS * 10
mflops = (total_flops / seconds) / 1_000_000

print(f"Time: {duration_us / 1000:.2f} ms ({seconds:.4f} sec)")
print(f"Hardware FPU performance: {mflops:.2f} MFLOPS")
