# Phil: 1S whoop flight controller (KiCad 10)

Three stacked 19x19 / 16x16 boards on a 12.8 mm M1.4 screw square:

- `Whoop_1S_FC.*`: flight controller (STM32G473 WLCSP-81, ICM-42688-P, SPL06, ELRS SX1281 + ESP8285, TPS63802)
- `Phil_ESC/`: 4-in-1 Bluejay ESC (4x EFM8BB51, 12x SiA517DJ)
- `Phil_VTX/`: 5.8 GHz VTX (RTC6705 + SE5004L), AT7456E OSD, blackbox flash, 5 V boost

Shared libraries: `WhoopFC.kicad_sym`, `WhoopFC.pretty/`, `WhoopFC.3dshapes/`.
Note: 3D model paths in the footprints are absolute (C:/Users/Survi/...), so other machines won't show them without editing.
