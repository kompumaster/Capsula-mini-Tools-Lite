/* Пустышка без libc: _start -> exit_group(1). Аргументы игнорируются.
 * Код 1 повторяет поведение fwupdater при «обновления нет». */
    .text
    .globl _start
_start:
    mov x0, #1
    mov x8, #94          /* __NR_exit_group */
    svc #0
