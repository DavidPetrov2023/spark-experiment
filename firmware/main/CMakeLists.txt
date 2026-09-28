# Bez REQUIRES schvalne: explicitni seznam odrizne main od implicitnich
# komponent a build pak nenajde esp_https_ota.h (naraz z Zobo robota).
idf_component_register(SRCS "main.c"
                            "wifi.c"
                            "ota.c"
                            "telemetry.c"
                       INCLUDE_DIRS ".")
