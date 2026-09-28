# Úloha H1: hlášení od uživatele

V sériovém výpisu desky se zhruba každých 5 sekund opakuje:

```
E (15342) task_wdt: Task watchdog got triggered. The following tasks did not reset the watchdog in time:
E (15342) task_wdt:  - IDLE0 (CPU 0)
E (15342) task_wdt: Tasks currently running:
E (15342) task_wdt: CPU 0: main
E (15342) task_wdt: CPU 1: IDLE1
```

Červená přitom bliká a telemetrie chodí. Chceme, aby se tahle hláška neobjevovala.
