Po poslední úpravě firmwaru jsou na desce dvě potíže:

1. Červená LED se po startu rozsvítí a už nezhasne. Má blikat: 500 ms svítí, 500 ms nesvítí.
2. Volný heap (esp_get_free_heap_size) klesá zhruba o 300 bajtů každých 5 sekund a deska se po několika hodinách sama restartuje.

Oprav obojí.
