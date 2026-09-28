Výchozí pravidla pro review firmwaru ESP32. Pro konkrétní projekt je nahraď souborem `REVIEW-PRAVIDLA.md`
v kořeni jeho repozitáře.

- Aktualizace firmwaru (OTA) je kritická: deska jde často aktualizovat jen po síti. Každou změnu, která může
  zabránit stažení, instalaci nebo potvrzení nového firmwaru, označ jako kritickou.
- Nový firmware se smí potvrdit až po úspěšném spojení se serverem. Cokoli, co potvrzení obchází, zpožďuje
  nad limit rollbacku nebo mění limit rollbacku, je kritické.
- Piny motorů musí po startu zůstat v nule (bezpečnost robota).
- FreeRTOS: `vTaskDelay` bere tiky, `pdMS_TO_TICKS` převádí ms na tiky. Hlídej dvojí převod a záměnu jednotek.
- ESP32 má dvě jádra: data sdílená mezi úlohami potřebují zámek nebo atomický přístup.
