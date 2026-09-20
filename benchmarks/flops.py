import time
import machine

# 500,000 ітерацій * 10 інструкцій FPU = 5,000,000 FLOPs (5 MFLOPs)
ITERATIONS = 500_000


# Інструкції FPU напряму для ARM Thumb-2 (Cortex-M33)
@micropython.asm_thumb
def benchmark_fpu_asm(r0):
    # r0 приймає кількість ітерацій (ITERATIONS)

    # Створюємо мітку циклу
    label(LOOP)

    # 10 послідовних апаратних додавань у FPU
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

    # Декремент лічильника циклу r0 = r0 - 1
    sub(r0, 1)
    # Перехід до LOOP, якщо r0 != 0
    bne(LOOP)


print("--- RP2350 MicroPython Hardware FPU Benchmark ---")
print(f"Частота CPU: {machine.freq() / 1_000_000:.1f} MHz")

# Замір часу
start_us = time.ticks_us()
benchmark_fpu_asm(ITERATIONS)
end_us = time.ticks_us()

# Обчислення
duration_us = time.ticks_diff(end_us, start_us)
seconds = duration_us / 1_000_000
total_flops = ITERATIONS * 10
mflops = (total_flops / seconds) / 1_000_000

print(f"Час: {duration_us / 1000:.2f} мс ({seconds:.4f} сек)")
print(f"Продуктивність апаратного FPU: {mflops:.2f} MFLOPS")
