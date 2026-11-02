/* Пустышка без libc: _start -> exit_group(0). Аргументы игнорируются. */
    .text
    .globl _start
_start:
    mov x0, #0
    mov x8, #94          /* __NR_exit_group */
    svc #0
