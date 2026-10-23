"""Generate an unwired KiCad 10 project holding every part for the 1S whoop AIO FC.

Usage: python -I gen_whoopfc.py <output project dir>
"""
import os, re, sys, uuid, json

KICAD = r"C:\Program Files\KiCad\10.0\share\kicad"
SYMDIR = os.path.join(KICAD, "symbols")
FPDIR = os.path.join(KICAD, "footprints")
PROJ = "Whoop_1S_FC"
CUSTOM_LIB = "WhoopFC"
OUT = sys.argv[1]

def uid():
    return str(uuid.uuid4())

# ---------------------------------------------------------------- s-expr utils
def block_end(s, i):
    """Index just past the paren block that starts at s[i] == '('."""
    depth = 0
    instr = False
    j = i
    while j < len(s):
        c = s[j]
        if instr:
            if c == "\\":
                j += 2
                continue
            if c == '"':
                instr = False
        elif c == '"':
            instr = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    raise ValueError("unbalanced")

def top_children(block):
    """Top-level child blocks (start, end) of a block."""
    out = []
    i = block.index("(", 1)
    while True:
        k = block.find("(", i)
        if k < 0:
            break
        # skip if inside a string at depth 1: we walk sequentially, so strings are skipped by block_end
        e = block_end(block, k)
        out.append((k, e))
        i = e
    return out

_libcache = {}
def lib_text(lib):
    if lib not in _libcache:
        with open(os.path.join(SYMDIR, lib + ".kicad_sym"), encoding="utf8") as f:
            _libcache[lib] = f.read()
    return _libcache[lib]

def raw_symbol(lib, name):
    s = lib_text(lib)
    key = '\n\t(symbol "%s"\n' % name
    i = s.find(key)
    if i < 0:
        raise KeyError("%s:%s not in KiCad library" % (lib, name))
    i += 2
    return s[i:block_end(s, i)]

def flat_symbol(lib, name):
    blk = raw_symbol(lib, name)
    m = re.search(r'\n\t\t\(extends "([^"]*)"\)', blk)
    if not m:
        return blk
    parent = flat_symbol(lib, m.group(1))
    child_props = [blk[a:b] for a, b in top_children(blk) if blk.startswith("(property", a)]
    # strip parent's properties, insert child's
    kids = top_children(parent)
    pieces, last = [], 0
    first_prop = None
    for a, b in kids:
        if parent.startswith("(property", a):
            if first_prop is None:
                first_prop = a
            pieces.append(parent[last:a])
            last = b
    pieces.append(parent[last:])
    stripped = "".join(pieces)
    # re-find insertion point: right after the header's last non-property item before symbols
    ins = stripped.find("\n\t\t(symbol ")
    stripped = stripped[:ins] + "\n\t\t" + "\n\t\t".join(child_props) + stripped[ins:]
    pname = m.group(1)
    stripped = stripped.replace('(symbol "%s"' % pname, '(symbol "%s"' % name, 1)
    stripped = stripped.replace('(symbol "%s_' % pname, '(symbol "%s_' % name)
    return stripped

def sym_prop(blk, prop):
    m = re.search(r'\(property "%s" "((?:[^"\\]|\\.)*)"' % re.escape(prop), blk)
    return m.group(1) if m else ""

# ------------------------------------------------------------ custom symbols
def esc(t):
    return t.replace("\\", "\\\\").replace('"', '\\"')

def box_symbol(name, ref, desc, fp, ds, left, right, kw=""):
    """Rectangle symbol; left/right are lists of (num, name, etype) or None for a gap."""
    def tlen(lst):
        return max([len(p[1]) for p in lst if p] + [0])
    width = (tlen(left) + tlen(right)) * 1.27 * 0.75 + 5.08
    width = max(10.16, round(width / 2.54 + 0.4999) * 2.54)
    rows = max(len(left), len(right))
    top = round((rows - 1) / 2) * 2.54
    hw = round(width / 2 / 2.54 + 0.4999) * 2.54
    pins = []
    for side, lst in (("L", left), ("R", right)):
        for r, p in enumerate(lst):
            if not p:
                continue
            num, pname, et = p
            y = top - r * 2.54
            if side == "L":
                x, ang = -hw - 2.54, 0
            else:
                x, ang = hw + 2.54, 180
            hide = ""
            pins.append(
                '\t\t\t(pin %s line\n\t\t\t\t(at %.2f %.2f %d)\n\t\t\t\t(length 2.54)%s\n'
                '\t\t\t\t(name "%s"\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)\n'
                '\t\t\t\t(number "%s"\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)\n\t\t\t)'
                % (et, x, y, ang, hide, esc(pname), num))
    ytop = top + 2.54
    ybot = top - rows * 2.54
    def prop(k, v, x, y, hidden, just=""):
        return ('\t\t(property "%s" "%s"\n\t\t\t(at %.2f %.2f 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)%s%s\n\t\t\t)\n\t\t)'
                % (k, esc(v), x, y, ("\n\t\t\t\t(justify %s)" % just) if just else "", "\n\t\t\t\t(hide yes)" if hidden else ""))
    props = [
        prop("Reference", ref, -hw, ytop + 1.27, False, "left"),
        prop("Value", name, -hw, ybot - 1.27, False, "left"),
        prop("Footprint", fp, 0, ybot - 3.81, True),
        prop("Datasheet", ds, 0, ybot - 6.35, True),
        prop("Description", desc, 0, ybot - 8.89, True),
    ]
    if kw:
        props.append(prop("ki_keywords", kw, 0, 0, True))
    body = ('\t\t(symbol "%s_0_1"\n\t\t\t(rectangle\n\t\t\t\t(start %.2f %.2f)\n\t\t\t\t(end %.2f %.2f)\n'
            '\t\t\t\t(stroke\n\t\t\t\t\t(width 0.254)\n\t\t\t\t\t(type default)\n\t\t\t\t)\n\t\t\t\t(fill\n\t\t\t\t\t(type background)\n\t\t\t\t)\n\t\t\t)\n\t\t)'
            % (name, -hw, ytop, hw, ybot))
    return ('(symbol "%s"\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n%s\n%s\n\t\t(symbol "%s_1_1"\n%s\n\t\t)\n\t)'
            % (name, "\n".join(props), body, name, "\n".join(pins)))

P, IN, OUT_, BI, PWR, PWRO, NC, OC = "passive", "input", "output", "bidirectional", "power_in", "power_out", "no_connect", "open_collector"

CUSTOM = {}
CUSTOM_FP = {}
def custom(name, ref, desc, fp, ds, left, right, kw=""):
    CUSTOM[name] = box_symbol(name, ref, desc, fp, ds, left, right, kw)
    CUSTOM_FP[name] = (fp, [p[0] for p in left + right if p])

custom("ICM-42688-P", "U", "TDK 6-axis IMU (gyro + accel), SPI/I2C/I3C, LGA-14 2.5x3mm. Pinout from TDK DS-000347.",
       "Package_LGA:Bosch_LGA-14_3x2.5mm_P0.5mm", "https://invensense.tdk.com/wp-content/uploads/2020/04/ds-000347_icm-42688-p-datasheet.pdf",
       [("8", "VDD", PWR), ("5", "VDDIO", PWR), None, ("12", "AP_CS", IN), ("13", "AP_SCL/AP_SCLK", IN),
        ("14", "AP_SDA/AP_SDIO/AP_SDI", BI), ("1", "AP_SDO/AP_AD0", BI), None, ("6", "GND", PWR)],
       [("4", "INT1/INT", OUT_), ("9", "INT2/FSYNC/CLKIN", BI), None, ("2", "RESV", P), ("3", "RESV", P),
        ("7", "RESV", P), ("10", "RESV", P), ("11", "RESV", P)], "gyro imu accelerometer")

custom("SPL06-001", "U", "Goertek barometric pressure + temperature sensor, I2C/SPI, LGA-8 2.0x2.5mm (pin-compatible with BMP280/DPS310).",
       "Package_LGA:Bosch_LGA-8_2x2.5mm_P0.65mm_ClockwisePinNumbering", "https://www.lcsc.com/datasheet/C2684428.pdf",
       [("8", "VDD", PWR), ("6", "VDDIO", PWR), None, ("1", "GND", PWR), ("7", "GND", PWR)],
       [("2", "CSB", IN), ("4", "SCK", IN), ("3", "SDI/SDA", BI), ("5", "SDO", BI)], "barometer pressure altitude")

custom("SX1281", "U", "Semtech 2.4 GHz LoRa/FLRC/GFSK transceiver (ExpressLRS), QFN-24 4x4mm. Pinout from SX1280/1 datasheet table 2-1.",
       "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm", "https://www.lcsc.com/datasheet/C2151551.pdf",
       [("15", "VBAT", PWR), ("11", "VBAT_IO", PWR), ("14", "DCC_SW", P), ("12", "DCC_FB", P), ("2", "VDD_IN", P),
        ("1", "VR_PA", P), None, ("4", "XTA", P), ("6", "XTB", P), None,
        ("5", "GND", PWR), ("13", "GND", PWR), ("20", "GND", PWR), ("21", "GND", PWR), ("23", "GND", PWR), ("24", "GND", PWR), ("25", "GND(EP)", PWR)],
       [("19", "NSS_CTS", IN), ("18", "SCK_RTSN", IN), ("17", "MOSI_RX", IN), ("16", "MISO_TX", OUT_), None,
        ("3", "NRESET", IN), ("7", "BUSY", OUT_), ("8", "DIO1", BI), ("9", "DIO2", BI), ("10", "DIO3", BI), None,
        ("22", "RFIO", P)], "ELRS LoRa 2.4GHz")

custom("ESP8285", "U", "Espressif Wi-Fi SoC with 1 MB in-package flash (ELRS RX MCU), QFN-32 5x5mm. Pin-compatible with ESP8266EX.",
       "Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.7x3.7mm", "https://www.espressif.com/sites/default/files/documentation/0a-esp8285_datasheet_en.pdf",
       [("1", "VDDA", PWR), ("30", "VDDA", PWR), ("3", "VDD3P3", PWR), ("4", "VDD3P3", PWR), ("5", "VDD_RTC", PWR),
        ("11", "VDDPST", PWR), ("17", "VDDPST", PWR), ("29", "VDDD", PWR), None,
        ("7", "CHIP_EN", IN), ("32", "~{EXT_RSTB}", IN), None, ("28", "XTAL_IN", P), ("27", "XTAL_OUT", P),
        ("31", "RES12K", P), None, ("2", "LNA", P), ("6", "TOUT", IN), None, ("33", "GND", PWR)],
       [("15", "GPIO0", BI), ("14", "GPIO2", BI), ("16", "GPIO4", BI), ("24", "GPIO5", BI), ("8", "XPD_DCDC/GPIO16", BI),
        ("9", "MTMS/GPIO14", BI), ("10", "MTDI/GPIO12", BI), ("12", "MTCK/GPIO13", BI), ("13", "MTDO/GPIO15", BI),
        ("25", "U0RXD/GPIO3", BI), ("26", "U0TXD/GPIO1", BI), None,
        ("18", "SDIO_DATA_2/GPIO9", BI), ("19", "SDIO_DATA_3/GPIO10", BI), ("20", "SDIO_CMD", BI), ("21", "SDIO_CLK", BI),
        ("22", "SDIO_DATA_0", BI), ("23", "SDIO_DATA_1", BI)], "wifi esp elrs")

custom("EFM8BB51-QFN20", "U", "Silicon Labs EFM8BB51 8051 MCU, 16 kB flash, QFN-20 3x3mm (Bluejay ESC). Pinout from EFM8BB51 datasheet table 6.1. Bluejay BB51 layout C.",
       "Package_DFN_QFN:SiliconLabs_QFN-20-1EP_3x3mm_P0.5mm_EP1.8x1.8mm", "https://www.silabs.com/documents/public/data-sheets/efm8bb51-datasheet.pdf",
       [("4", "VDD", PWR), None, ("5", "RSTb/C2CK", BI), ("6", "P2.0/C2D", BI), None, ("3", "GND", PWR), ("12", "GND", PWR), ("21", "GND(EP)", PWR)],
       [("2", "P0.0", BI), ("1", "P0.1", BI), ("20", "P0.2", BI), ("19", "P0.3", BI), ("18", "P0.4", BI), ("17", "P0.5", BI),
        ("16", "P0.6", BI), ("15", "P0.7", BI), None, ("14", "P1.0", BI), ("13", "P1.1", BI), ("11", "P1.2", BI),
        ("10", "P1.3", BI), ("9", "P1.4", BI), ("8", "P1.5", BI), ("7", "P1.6", BI)], "8051 bluejay esc")

custom("SiA517DJ", "Q", "Vishay dual MOSFET, ch1 N-channel / ch2 P-channel, 12 V, PowerPAK SC-70-6 Dual (D1/D2 pads tied to pins 6/3). One ESC half-bridge.",
       "Package_TO_SOT_SMD:Vishay_PowerPAK_SC70-6L_Dual", "https://www.vishay.com/docs/64832/sia517dj.pdf",
       [("2", "G1(N)", IN), ("5", "G2(P)", IN)],
       [("6", "D1(N)", P), ("1", "S1(N)", P), ("4", "S2(P)", P), ("3", "D2(P)", P)], "mosfet complementary half-bridge")

custom("TPS63802", "U", "TI 2 A buck-boost converter, 1.3-5.5 V in, VSON-HR-10 2x3mm (DLA). No stock KiCad footprint: create one from TI land pattern.",
       "", "https://www.ti.com/lit/ds/symlink/tps63802.pdf",
       [("10", "VIN", PWR), ("1", "EN", IN), ("2", "MODE", IN), None, ("9", "L1", P), None, ("3", "AGND", PWR), ("8", "GND", PWR)],
       [("6", "VOUT", PWRO), ("4", "FB", IN), ("5", "PG", OC), None, ("7", "L2", P)], "buck-boost regulator 3.3V")

custom("TPS61023", "U", "TI synchronous boost converter, 0.5-5.5 V in, 3.7 A switch, SOT-563 (DRL).",
       "Package_TO_SOT_SMD:SOT-563", "https://www.ti.com/lit/ds/symlink/tps61023.pdf",
       [("3", "VIN", PWR), ("2", "EN", IN), None, ("4", "GND", PWR)],
       [("5", "SW", P), ("6", "VOUT", PWRO), ("1", "FB", IN)], "boost regulator 5V")

custom("RTC6705", "U", "RichWave 5.8 GHz FM video transmitter + synthesizer, WQFN-40 6x6mm (LCSC C913074). Pinout from RTC6705-DST-001.",
       "Package_DFN_QFN:QFN-40-1EP_6x6mm_P0.5mm_EP4.6x4.6mm", "https://www.lcsc.com/datasheet/C913074.pdf",
       [("8", "VDD33_DIG", PWR), ("22", "VDD3V3", PWR), ("13", "AVDD_6", PWR), ("17", "AVDD_6.5", PWR), ("30", "VDDVT", PWR),
        ("31", "BUFVDD", PWR), ("32", "PAVDD", PWR), ("39", "VCOVDD", PWR), None,
        ("9", "V2D5_PLL", P), ("23", "REG1D8_1", P), ("26", "REG1D8", P), ("40", "LDD2V5", P), None,
        ("24", "XTAL1", P), ("25", "XTAL2", P), None,
        ("28", "GND", PWR), ("38", "GND", PWR), ("33", "RFGND", PWR), ("41", "GND(EP)", PWR)],
       [("1", "SPI_SE", IN), ("3", "S", IN), ("4", "BX", IN), ("5", "SPIDATA/CS0", IN), ("6", "SPILE/CS1", IN), ("7", "SPICLK/CS2", IN), None,
        ("10", "VT_Mod", IN), ("11", "RF_VT2", IN), None,
        ("14", "AVT1", P), ("15", "ACP1", P), ("16", "AOUT1", P), ("19", "AOUT2", P), ("20", "ACP2", P), ("21", "AVT2", P),
        ("27", "CP", P), ("29", "VT", P), None, ("34", "PAOUT2", P), ("35", "PAOUT1", P), None,
        ("2", "NC", NC), ("12", "NC", NC), ("18", "NC", NC), ("36", "NC", NC), ("37", "NC", NC)], "vtx video transmitter 5.8GHz")

custom("AT7456E", "U", "Single-channel monochrome OSD with EEPROM (MAX7456 clone), HTSSOP-28-EP (LCSC C82351). Pinout from AT7456E-S402.",
       "Package_SO:HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP2.85x5.4mm", "https://www.lcsc.com/datasheet/C82351.pdf",
       [("3", "DVDD", PWR), ("21", "AVDD", PWR), ("24", "PVDD", PWR), None, ("5", "CLKIN", P), ("6", "XFB", P), ("7", "CLKOUT", OUT_), None,
        ("4", "DGND", PWR), ("20", "AGND", PWR), ("23", "PGND", PWR), ("29", "EP(AGND)", PWR)],
       [("8", "~{CS}", IN), ("9", "SDIN", IN), ("10", "SCLK", IN), ("11", "SDOUT", OUT_), ("19", "~{RESET}", IN), None,
        ("22", "VIN", IN), ("26", "VOUT", OUT_), ("25", "SAG", IN), None,
        ("12", "LOS", OC), ("13", "SYNC_IN", IN), ("17", "~{VSYNC}", OC), ("18", "~{HSYNC}", OC), None,
        ("1", "NC", NC), ("2", "NC", NC), ("14", "NC", NC), ("15", "NC", NC), ("16", "NC", NC), ("27", "NC", NC), ("28", "NC", NC)], "osd video overlay")

custom("TCXO_2016", "Y", "4-pad 2.0x1.6mm TCXO / clipped-sine oscillator (1=VC or NC, 2=GND, 3=OUT, 4=VCC). Verify pad map against chosen part.",
       "Oscillator:Oscillator_SMD_SiT_PQFN-4Pin_2.0x1.6mm", "",
       [("4", "VCC", PWR), ("1", "VC/NC", IN), ("2", "GND", PWR)],
       [("3", "OUT", OUT_)], "tcxo oscillator")

custom("SE5004L", "U", "Skyworks 5 GHz 26 dBm PA with power detector, QFN-20 4x4mm. Pinout from datasheet 202393B; EP (pad 21) is ground.",
       "Package_DFN_QFN:QFN-20-1EP_4x4mm_P0.5mm_EP2.5x2.5mm", "https://www.skyworksinc.com/Products/Amplifiers/SE5004L",
       [("20", "VCC1", PWR), ("19", "VCC2", PWR), ("8", "VCC2", PWR), ("18", "VCC3", PWR), ("9", "VCC3", PWR), None,
        ("5", "VREF", IN), ("6", "SP1", P), ("7", "SP2", P), None,
        ("2", "GND", PWR), ("4", "GND", PWR), ("11", "GND", PWR), ("12", "GND", PWR), ("14", "GND", PWR),
        ("15", "GND", PWR), ("16", "GND", PWR), ("17", "GND", PWR), ("21", "GND(EP)", PWR)],
       [("3", "RFIN", P), ("13", "RFOUT", P), None, ("10", "DET", OUT_), None, ("1", "NU", NC)], "pa amplifier 5.8GHz")

# ------------------------------------------------------------------ the BOM
R, C, L, LED, FB, XTAL = "Device:R_Small", "Device:C_Small", "Device:L_Small", "Device:LED_Small", "Device:FerriteBead_Small", "Device:Crystal_GND24_Small"
TP, UFL = "Connector:TestPoint", "Connector:Conn_Coaxial_Small"
F_R, F_C, F_C6, F_C8, F_LED, F_L = ("Resistor_SMD:R_0402_1005Metric", "Capacitor_SMD:C_0402_1005Metric", "Capacitor_SMD:C_0603_1608Metric",
                                    "Capacitor_SMD:C_0805_2012Metric", "LED_SMD:LED_0402_1005Metric", "Inductor_SMD:L_0402_1005Metric")
F_X = "Crystal:Crystal_SMD_2016-4Pin_2.0x1.6mm"
F_TP, F_TPB = "TestPoint:TestPoint_Pad_1.0x1.0mm", "TestPoint:TestPoint_Pad_1.5x1.5mm"
F_UFL = "Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical"
W = CUSTOM_LIB + ":"

SHEETS = []  # (file, title, paper, groups); group = (heading, [parts]); part dict
def sheet(fname, title):
    s = {"file": fname, "title": title, "groups": []}
    SHEETS.append(s)
    return s
def group(s, heading):
    g = (heading, [])
    s["groups"].append(g)
    return g[1]
def part(g, lib_id, value, fp=None, desc="", mpn="", n=1, variant="", ref=None):
    for _ in range(n):
        g.append(dict(lib_id=lib_id, value=value, fp=fp, desc=desc, mpn=mpn, variant=variant, ref=ref))

# MCU
s = sheet("mcu.kicad_sch", "Flight controller MCU")
g = group(s, "STM32G473CEU6 - Betaflight STM32G47X target")
part(g, "MCU_ST_STM32G4:STM32G473CEUx", "STM32G473CEU6", mpn="STM32G473CEU6")
g = group(s, "HSE crystal 8 MHz")
part(g, XTAL, "8MHz", F_X, "HSE crystal, 2.0x1.6mm")
part(g, C, "10pF", F_C, "HSE load cap (match crystal CL)", n=2)
g = group(s, "MCU decoupling / reset / boot")
part(g, C, "100nF", F_C, "VDD/VBAT decoupling, one per supply pin", n=5)
part(g, C, "1uF", F_C, "VDDA/VREF+ decoupling")
part(g, C, "4.7uF", F_C6, "MCU 3V3 bulk")
part(g, C, "100nF", F_C, "NRST filter cap")
part(g, R, "10k", F_R, "BOOT0 pull-down")
part(g, TP, "BOOT0", F_TP, "BOOT0 pad (bridge to 3V3 for DFU)")
g = group(s, "Status LEDs (MCU GPIO, active high) / LED strip pad / buzzer")
part(g, LED, "Blue", F_LED, "Status LED (Betaflight LED0)")
part(g, R, "1k", F_R, "LED0 resistor")
part(g, LED, "Orange", F_LED, "Status LED (Betaflight LED1)")
part(g, R, "1k", F_R, "LED1 resistor")
part(g, LED, "Yellow", F_LED, "Status LED (Betaflight LED2)")
part(g, R, "1k", F_R, "LED2 resistor")
part(g, TP, "LED_STRIP", F_TP, "LED strip data out pad (external strip powered from VBAT)")
part(g, TP, "BUZ-", F_TP, "Buzzer pad (optional, DShot beacon works without)")

# Sensors
s = sheet("sensors.kicad_sch", "Gyro, barometer, Blackbox flash")
g = group(s, "Gyro / IMU - ICM-42688-P on its own SPI bus (BMI270 = alt, different pinout)")
part(g, W + "ICM-42688-P", "ICM-42688-P", mpn="ICM-42688-P")
part(g, C, "100nF", F_C, "Gyro VDD decoupling (datasheet C1)")
part(g, C, "2.2uF", F_C, "Gyro VDD decoupling (datasheet C2)")
part(g, C, "100nF", F_C, "Gyro VDDIO decoupling")
part(g, FB, "600R@100MHz", "Inductor_SMD:L_0402_1005Metric", "Ferrite: filtered 3V3 branch for gyro/RX")
part(g, C, "4.7uF", F_C6, "Filtered gyro rail bulk")
g = group(s, "Barometer - SPL06-001 (DPS310 pin-compatible alt), I2C")
part(g, W + "SPL06-001", "SPL06-001", mpn="SPL06-001")
part(g, C, "100nF", F_C, "Baro VDD/VDDIO decoupling", n=2)
part(g, R, "4.7k", F_R, "I2C SDA/SCL pull-up", n=2)
g = group(s, "Blackbox flash - W25Q128JV 16 MB (shared SPI with OSD)")
part(g, "Memory_Flash:W25Q128JVP", "W25Q128JVPIQ", mpn="W25Q128JVPIQ")
part(g, C, "100nF", F_C, "Flash decoupling")
part(g, R, "10k", F_R, "Flash /CS pull-up")

# Receiver
s = sheet("receiver.kicad_sch", "ELRS 2.4 GHz receiver (SX1281 + ESP8285, CRSF over UART)")
g = group(s, "SX1281 radio + 52 MHz TCXO")
part(g, W + "SX1281", "SX1281IMLTRT", mpn="SX1281IMLTRT")
part(g, W + "TCXO_2016", "52MHz TCXO", desc="52 MHz TCXO +/-1-2 ppm, 2.0x1.6mm")
part(g, C, "100nF", F_C, "TCXO supply decoupling")
part(g, C, "10pF", F_C, "TCXO -> XTA coupling (per Semtech ref)")
part(g, C, "100nF", F_C, "SX1281 VBAT / VBAT_IO decoupling", n=2)
part(g, C, "4.7uF", F_C, "SX1281 supply bulk")
part(g, L, "15uH", "Inductor_SMD:L_0603_1608Metric", "SX1281 DC-DC inductor DCC_SW-DCC_FB (verify vs Semtech ref)")
part(g, C, "470nF", F_C, "DCC_FB decoupling (verify vs Semtech ref)")
part(g, C, "47nF", F_C, "VR_PA decoupling (verify vs Semtech ref)")
g = group(s, "2.4 GHz RF match / ESD / antenna (copy Semtech/ELRS reference layout)")
part(g, L, "TBD", F_L, "RF match / balun inductor (Semtech ref)", n=2)
part(g, C, "TBD", F_C, "RF match / balun capacitor (Semtech ref)", n=3)
part(g, "Diode:ESD131-B1-W0201", "ESD131-B1-W0201", desc="Low-cap RF ESD at antenna feed", mpn="ESD131-B1-W0201")
part(g, UFL, "U.FL", F_UFL, "u.FL for 2.4 GHz dipole (most durable antenna option)", mpn="U.FL-R-SMT-1")
g = group(s, "ESP8285 ELRS MCU + 26 MHz crystal")
part(g, W + "ESP8285", "ESP8285", mpn="ESP8285N08")
part(g, XTAL, "26MHz", F_X, "ESP8285 crystal, 2.0x1.6mm")
part(g, C, "10pF", F_C, "26 MHz load cap (match crystal CL)", n=2)
part(g, R, "12k 1%", F_R, "RES12K bias resistor")
part(g, R, "10k", F_R, "CHIP_EN / EXT_RSTB pull-up", n=2)
part(g, C, "100nF", F_C, "ESP8285 decoupling", n=3)
part(g, C, "10uF", F_C6, "ESP8285 bulk")
part(g, TP, "BIND/BOOT", F_TP, "GPIO0 bind / boot pad")
part(g, LED, "Green", F_LED, "ELRS link LED")
part(g, R, "1k", F_R, "ELRS LED resistor")

# ESC
s = sheet("esc.kicad_sch", "4-in-1 Bluejay ESC (EFM8BB51 + 3x SiA517DJ per motor)")
for m in range(1, 5):
    g = group(s, "ESC %d / Motor %d" % (m, m))
    part(g, W + "EFM8BB51-QFN20", "EFM8BB51F16G-C-QFN20", mpn="EFM8BB51F16G-C-QFN20")
    part(g, C, "1uF", F_C, "ESC MCU bulk")
    part(g, C, "100nF", F_C, "ESC MCU decoupling")
    part(g, W + "SiA517DJ", "SiA517DJ", desc="Phase half-bridge (alt SiA527DJ)", mpn="SIA517DJ-T1-GE3", n=3)
    part(g, R, "0R", F_R, "Gate resistor (tune vs ringing)", n=6)
    part(g, R, "TBD", F_R, "Back-EMF phase divider (copy Bluejay 1S ref)", n=6)
    part(g, R, "TBD", F_R, "Virtual-neutral network (copy Bluejay 1S ref)", n=3)
    part(g, R, "100k", F_R, "DShot input pull-down (no twitch at power-up)")
    part(g, C, "10uF", F_C6, "Per-ESC bulk cap near FETs (10-22uF)")
    for ph in "ABC":
        part(g, TP, "M%d_%s" % (m, ph), F_TPB, "Motor %d phase %s solder pad" % (m, ph))
    part(g, TP, "ESC%d_SIG" % m, F_TP, "DShot / Bluejay passthrough test pad")
    part(g, TP, "ESC%d_C2CK" % m, F_TP, "C2 programming clock pad")
    part(g, TP, "ESC%d_C2D" % m, F_TP, "C2 programming data pad")

# Power
s = sheet("power.kicad_sch", "Power: 1S input, 3.3 V buck-boost, 5 V boost, sensing")
g = group(s, "Battery input (BT2.0 pigtail) and protection")
part(g, TP, "VBAT+", "TestPoint:TestPoint_Pad_2.0x2.0mm", "Battery + pigtail pad (22-24 AWG to BT2.0)")
part(g, TP, "VBAT-", "TestPoint:TestPoint_Pad_2.0x2.0mm", "Battery - pigtail pad")
part(g, "Diode:SMF5V0A", "SMF5.0A", desc="5 V unidirectional TVS at battery input", mpn="SMF5.0A")
part(g, "Device:C_Polarized_Small", "100uF 6.3V", "Capacitor_Tantalum_SMD:CP_EIA-3528-12_Kemet-T", "Input bulk, low-ESR polymer (47-220uF)")
g = group(s, "3.3 V rail - TPS63802 buck-boost (brownout-proof)")
part(g, W + "TPS63802", "TPS63802DLAR", mpn="TPS63802DLAR")
part(g, L, "0.47uH", "Inductor_SMD:L_Murata_DFE201610P", "Buck-boost inductor (DFE201610E-R47M or similar)")
part(g, C, "10uF", F_C6, "TPS63802 input cap")
part(g, C, "22uF", F_C6, "TPS63802 output cap", n=2)
part(g, R, "560k", F_R, "FB top (3.3 V = 0.5 V x (1 + 560k/100k))")
part(g, R, "100k", F_R, "FB bottom")
g = group(s, "5 V rail - TPS61023 boost (VTX variant only)")
part(g, W + "TPS61023", "TPS61023DRLR", mpn="TPS61023DRLR", variant="FPV")
part(g, L, "1uH", "Inductor_SMD:L_Murata_DFE201610P", "Boost inductor", variant="FPV")
part(g, C, "10uF", F_C6, "TPS61023 input cap", variant="FPV")
part(g, C, "22uF", F_C6, "TPS61023 output cap (TI Fig 8-1: 2 x 22uF)", n=2, variant="FPV")
part(g, R, "732k 1%", F_R, "FB top (TI Fig 8-1: 732k/100k for 5 V)", variant="FPV")
part(g, R, "100k", F_R, "FB bottom", variant="FPV")
g = group(s, "Battery voltage sense / power LED")
part(g, R, "10k", F_R, "VBAT divider top", n=2)
part(g, C, "100nF", F_C, "VBAT ADC filter cap")
part(g, LED, "Red", F_LED, "3.3 V power LED")
part(g, R, "1k", F_R, "Power LED resistor")

# VTX / OSD
s = sheet("vtx_osd.kicad_sch", "Analog VTX + OSD (FPV variant)")
g = group(s, "RTC6705 5.8 GHz VTX")
part(g, W + "RTC6705", "RTC6705", mpn="RTC6705", variant="FPV")
part(g, XTAL, "8MHz", F_X, "RTC6705 reference crystal (Fosc = 8 MHz per datasheet)", variant="FPV")
part(g, C, "TBD", F_C, "RTC6705 crystal load cap", n=2, variant="FPV")
part(g, C, "100nF", F_C, "RTC6705 supply decoupling", n=5, variant="FPV")
part(g, C, "10uF", F_C6, "RTC6705 bulk", variant="FPV")
part(g, R, "TBD", F_R, "PLL loop filter (copy reference AIO)", variant="FPV")
part(g, C, "TBD", F_C, "PLL loop filter (copy reference AIO)", n=2, variant="FPV")
g = group(s, "5.8 GHz PA + antenna")
part(g, W + "SE5004L", "SE5004L", desc="5.8 GHz PA (or the PA from your reference AIO)", mpn="SE5004L", variant="FPV")
part(g, C, "100nF", F_C, "PA decoupling", n=3, variant="FPV")
part(g, C, "10uF", F_C6, "PA bulk", variant="FPV")
part(g, C, "TBD", F_C, "PA in/out match / DC block (copy reference)", n=2, variant="FPV")
part(g, UFL, "U.FL", F_UFL, "u.FL for 5.8 GHz dipole", mpn="U.FL-R-SMT-1", variant="FPV")
g = group(s, "AT7456E OSD + 27 MHz crystal")
part(g, W + "AT7456E", "AT7456E", mpn="AT7456E", variant="FPV")
part(g, XTAL, "27MHz", F_X, "OSD crystal", variant="FPV")
part(g, C, "TBD", F_C, "27 MHz load cap (match crystal CL)", n=2, variant="FPV")
part(g, C, "100nF", F_C, "OSD DVDD/AVDD/PVDD decoupling", n=3, variant="FPV")
part(g, C, "100nF", F_C, "Video in coupling cap", variant="FPV")
part(g, R, "75R", F_R, "Video input termination", variant="FPV")
g = group(s, "Camera connector")
part(g, "Connector_Generic:Conn_01x03", "CAM", "Connector_JST:JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal",
     "Camera: VIDEO / 5V / GND (JST-SH 1.0mm)", mpn="SM03B-SRSS-TB", variant="FPV")

# Connectors / programming / mechanical
s = sheet("connectors.kicad_sch", "Config port, programming, test points, mechanical")
g = group(s, "Config port - JST-SH 4-pin USB (5V, D+, D-, GND) + ESD")
part(g, "Connector_Generic:Conn_01x04", "USB_CFG", "Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal",
     "Native-USB config port to USB-C breakout cable", mpn="SM04B-SRSS-TB")
part(g, "Power_Protection:USBLC6-2SC6", "USBLC6-2SC6", desc="ESD on D+/D-", mpn="USBLC6-2SC6")
g = group(s, "SWD - Tag-Connect TC2030-NL (factory flash / debug)")
part(g, "Connector:Conn_ARM_SWD_TagConnect_TC2030-NL", "TC2030-NL", mpn="TC2030-IDC-NL")
g = group(s, "Test points (pogo jig)")
for n_ in ["3V3", "5V", "GND", "VBAT", "SWDIO", "SWCLK", "NRST", "UART_TX", "UART_RX"]:
    part(g, TP, n_, F_TP, "Test / pogo pad")
g = group(s, "Mechanical - 25.5 mm whoop mount, fiducials")
part(g, "Mechanical:MountingHole", "MountingHole", "MountingHole:MountingHole_2mm", "25.5 mm whoop pattern soft-mount hole", n=4)
part(g, "Mechanical:Fiducial", "Fiducial", "Fiducial:Fiducial_0.5mm_Mask1.5mm", "Assembly fiducial", n=3)

# ------------------------------------------------- footprint size reduction
# Signal-level passives go to 0201. Anything on the battery / regulator power path,
# and caps >= 1uF on 3.3 V, stay larger: bigger MLCCs crack less when the board flexes
# in a crash and keep their capacitance under DC bias.
R0201, C0201, C0402, L0201 = ("Resistor_SMD:R_0201_0603Metric", "Capacitor_SMD:C_0201_0603Metric",
                              "Capacitor_SMD:C_0402_1005Metric", "Inductor_SMD:L_0201_0603Metric")
X1612 = "Crystal:Crystal_SMD_WE_IQXC-26-4Pin_1.6x1.2mm"
SMALL_C = {"10pF", "47nF", "100nF", "470nF", "TBD"}
POWER_PATH = ("Per-ESC bulk", "TPS63802", "TPS61023")
def shrink(p):
    fp, v, d = p["fp"], p["value"], p["desc"]
    if fp == F_R:
        p["fp"] = R0201
    elif fp == F_C and v in SMALL_C:
        p["fp"] = C0201
    elif fp == F_C6 and p["lib_id"] == C and not d.startswith(POWER_PATH):
        p["fp"] = C0402                       # 4.7uF / 10uF on 3.3 V rails
    elif fp == F_L:
        p["fp"] = L0201                       # RF match inductors
    elif p["lib_id"] == FB:
        p["fp"] = L0201                       # gyro/RX ferrite, low current
    elif p["lib_id"] == L and v == "15uH":
        p["fp"] = "Inductor_SMD:L_0402_1005Metric"   # SX1281 DC-DC, tens of mA
    elif p["lib_id"] == XTAL and v in ("26MHz", "27MHz"):
        p["fp"] = X1612                       # 1612 parts exist >= ~24 MHz; 8 MHz stays 2016
        p["desc"] = d.replace(", 2.0x1.6mm", "") + ", 1.6x1.2mm"
    elif fp and "CP_EIA-3528" in fp:
        p["fp"] = "Capacitor_Tantalum_SMD:CP_EIA-3216-18_Kemet-A"
for sh in SHEETS:
    for _, parts in sh["groups"]:
        for p in parts:
            shrink(p)

# ------------------------------------------------------------ symbol data
LIBSYM = {}   # lib_id -> flat block text (name without lib prefix)
def get_sym(lib_id):
    if lib_id not in LIBSYM:
        lib, name = lib_id.split(":", 1)
        LIBSYM[lib_id] = CUSTOM[name] if lib == CUSTOM_LIB else flat_symbol(lib, name)
    return LIBSYM[lib_id]

def sym_geometry(blk):
    """bbox (lib coords, y up) and list of pin numbers."""
    body = blk
    # drop property blocks so their positions don't count
    for a, b in reversed([(a, b) for a, b in top_children(blk) if blk.startswith("(property", a)]):
        body = body[:a] + body[b:]
    xs, ys = [], []
    for m in re.finditer(r"\((?:start|end|xy|center|mid) (-?[\d.]+) (-?[\d.]+)\)", body):
        xs.append(float(m.group(1))); ys.append(float(m.group(2)))
    pins = []
    for m in re.finditer(r"\(pin \w+ \w+\s*\(at (-?[\d.]+) (-?[\d.]+) (\d+)\)\s*\(length ([\d.]+)\)", body):
        x, y, a, l = float(m.group(1)), float(m.group(2)), int(m.group(3)), float(m.group(4))
        xs += [x]; ys += [y]
        dx, dy = {0: (l, 0), 90: (0, l), 180: (-l, 0), 270: (0, -l)}[a]
        xs.append(x + dx); ys.append(y + dy)
    for m in re.finditer(r'\(number "([^"]*)"', body):
        pins.append(m.group(1))
    for m in re.finditer(r"\(circle\s*\(center (-?[\d.]+) (-?[\d.]+)\)\s*\(radius ([\d.]+)\)", body):
        cx, cy, r = map(float, m.groups())
        xs += [cx - r, cx + r]; ys += [cy - r, cy + r]
    if not xs:
        xs, ys = [-1.27, 1.27], [-1.27, 1.27]
    return (min(xs), min(ys), max(xs), max(ys)), sorted(set(pins), key=lambda p: (len(p), p))

# --------------------------------------------------------- validation checks
problems = []
def fp_pads(fp):
    lib, name = fp.split(":", 1)
    path = os.path.join(FPDIR, lib + ".pretty", name + ".kicad_mod")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf8") as f:
        return set(re.findall(r'\(pad "([^"]+)"', f.read()))

for sh in SHEETS:
    for _, parts in sh["groups"]:
        for p in parts:
            blk = get_sym(p["lib_id"])
            if p["fp"] is None:
                p["fp"] = sym_prop(blk, "Footprint")
            if p["fp"] and fp_pads(p["fp"]) is None:
                problems.append("footprint missing: %s (%s)" % (p["fp"], p["lib_id"]))
for name, (fp, pins) in CUSTOM_FP.items():
    if len(pins) != len(set(pins)):
        problems.append("duplicate pin numbers in " + name)
    if fp:
        pads = fp_pads(fp)
        if pads is None:
            problems.append("custom footprint missing " + fp)
        elif set(pins) != pads:
            problems.append("%s pins %s != pads %s" % (name, sorted(set(pins) - pads), sorted(pads - set(pins))))
if problems:
    print("\n".join(problems))
    sys.exit(1)

# ------------------------------------------------------------ references
COUNTERS = {}
for idx, sh in enumerate(SHEETS):
    base = (idx + 1) * 100
    for _, parts in sh["groups"]:
        for p in parts:
            pre = re.match(r"[A-Z#]+", sym_prop(get_sym(p["lib_id"]), "Reference")).group(0)
            if p["lib_id"] == TP:
                pre = "TP"
            key = (idx, pre)
            COUNTERS[key] = COUNTERS.get(key, 0) + 1
            n = COUNTERS[key]
            if sh["file"] == "esc.kicad_sch" and n > 99:
                raise SystemExit("ref overflow")
            p["ref"] = "%s%d" % (pre, base + n)

# ------------------------------------------------------------ writers
def prop_inst(k, v, x, y, hide=False, size=1.27, just=None):
    return ('\t\t(property "%s" "%s"\n\t\t\t(at %.2f %.2f 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size %.2f %.2f)\n\t\t\t\t)%s%s\n\t\t\t)\n\t\t)'
            % (k, esc(v), x, y, size, size, ("\n\t\t\t\t(justify %s)" % just) if just else "", "\n\t\t\t\t(hide yes)" if hide else ""))

def text_item(t, x, y, size=2.0, bold=True):
    return ('\t(text "%s"\n\t\t(exclude_from_sim no)\n\t\t(at %.2f %.2f 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size %.2f %.2f)%s\n\t\t\t)\n\t\t\t(justify left bottom)\n\t\t)\n\t\t(uuid "%s")\n\t)'
            % (esc(t), x, y, size, size, "\n\t\t\t\t(bold yes)" if bold else "", uid()))

def snap(v, g=2.54):
    return round(v / g) * g


def sym_instance(p, cx, cy, bbox, pins, tsize, sheet_path):
    bx0, by0, bx1, by1 = bbox
    props = [
        prop_inst("Reference", p["ref"], cx + bx0, cy - by1 - 1.0, size=tsize, just="left"),
        prop_inst("Value", p["value"], cx + bx0, cy - by0 + tsize + 0.8, size=tsize, just="left"),
        prop_inst("Footprint", p["fp"] or "", cx, cy, hide=True),
        prop_inst("Datasheet", sym_prop(get_sym(p["lib_id"]), "Datasheet"), cx, cy, hide=True),
        prop_inst("Description", p["desc"] or sym_prop(get_sym(p["lib_id"]), "Description"), cx, cy, hide=True),
    ]
    if p["mpn"]:
        props.append(prop_inst("MPN", p["mpn"], cx, cy, hide=True))
    if p["variant"]:
        props.append(prop_inst("Variant", p["variant"], cx, cy, hide=True))
    pin_txt = "\n".join('\t\t(pin "%s"\n\t\t\t(uuid "%s")\n\t\t)' % (n, uid()) for n in pins)
    return ('\t(symbol\n\t\t(lib_id "%s")\n\t\t(at %.2f %.2f 0)\n\t\t(unit 1)\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n'
            '\t\t(uuid "%s")\n%s\n%s\n\t\t(instances\n\t\t\t(project "%s"\n\t\t\t\t(path "%s"\n\t\t\t\t\t(reference "%s")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)'
            % (p["lib_id"], cx, cy, uid(), "\n".join(props), pin_txt, PROJ, sheet_path, p["ref"]))

def lib_symbols_block(lib_ids):
    out = []
    for lid in sorted(lib_ids):
        blk = get_sym(lid)
        name = lid.split(":", 1)[1]
        blk = blk.replace('(symbol "%s"' % name, '(symbol "%s"' % lid, 1)
        out.append("\t\t" + blk)
    return "\t(lib_symbols\n%s\n\t)" % "\n".join(out)

def title_block(title, n):
    return ('\t(title_block\n\t\t(title "%s")\n\t\t(date "2026-10-12")\n\t\t(rev "2")\n\t\t(company "1S Whoop AIO FC")\n'
            '\t\t(comment 1 "Parts placement only - not wired")\n\t\t(comment 2 "Source: 1S Whoop Flight Controller - Design and Parts Guide")\n\t)' % (esc(title), ))

def write(path, text):
    with open(path, "w", encoding="utf8", newline="\n") as f:
        f.write(text)


ROOT_UUID = uid()
BLOCK_W = 400.0
GAP = 20.32
MARGIN = 25.4
NOTES_H = 7 + 6 * 3.5

def layout_block(sh, bw):
    """Shelf-pack one subsystem at origin (0,0). Returns (placed, texts, width, height)."""
    x0, y = 5.08, 15.24
    xmax = bw - 5.08
    placed, texts = [], [(sh["title"], 5.08, 10.16, 3.0)]
    used_w = 5.08 + len(sh["title"]) * 3.0 * 0.95
    for heading, parts in sh["groups"]:
        texts.append((heading, x0, y, 2.0))
        used_w = max(used_w, x0 + len(heading) * 2.0 * 0.95)
        y += 5.08
        x = x0
        row_h = 0
        for p in parts:
            (bx0, by0, bx1, by1), pins = sym_geometry(get_sym(p["lib_id"]))
            tsize = 1.27 if (bx1 - bx0) > 8 else 1.0
            tw = max(len(p["ref"]), len(p["value"])) * tsize * 0.85
            w = max(bx1 - bx0, tw) + 3.81
            h = (by1 - by0) + 2 * tsize + 4.5
            if x + w > xmax and x > x0:
                x = x0
                y += row_h
                row_h = 0
            cx = x + (w - (bx1 - bx0)) / 2 - bx0
            cy = y + tsize + 2.0 + by1
            placed.append((p, cx, cy, (bx0, by0, bx1, by1), pins, tsize))
            x += w
            used_w = max(used_w, x)
            row_h = max(row_h, h)
        y += row_h + 7.62
    return placed, texts, used_w + 5.08, y

blocks = [layout_block(sh, BLOCK_W) for sh in SHEETS]

# assign blocks (in order) to the currently shortest column; pick the column count
# whose page is closest to a landscape ISO aspect ratio
best = None
for ncols in range(1, 5):
    cols = [[] for _ in range(ncols)]
    heights = [0.0] * ncols
    for i, b in enumerate(blocks):
        c = heights.index(min(heights))
        cols[c].append(i)
        heights[c] += b[3] + GAP
    colw = [max([blocks[i][2] for i in col] or [0]) for col in cols]
    W = 2 * MARGIN + sum(colw) + GAP * (ncols - 1)
    H = 2 * MARGIN + max(heights) + 45 + NOTES_H          # room for the title block
    score = abs(W / H - 2 ** 0.5)
    if best is None or score < best[0]:
        best = (score, cols, colw, W, H)
_, cols, colw, PW, PH = best

ISO = [("A3", 420, 297), ("A2", 594, 420), ("A1", 841, 594), ("A0", 1189, 841)]
paper = None
if paper is None:
    PW, PH = snap(PW + 10, 10), snap(PH + 10, 10)
    paper = '"User" %d %d' % (PW, PH)

items, syms, origin = [], [], {}
xcol = MARGIN
for c, col in enumerate(cols):
    y = MARGIN + 15 + NOTES_H
    for i in col:
        origin[i] = (xcol, y)
        y += blocks[i][3] + GAP
    xcol += colw[c] + GAP

path = "/" + ROOT_UUID
for i, (placed, texts, bw, bh) in enumerate(blocks):
    ox, oy = origin[i]
    ox, oy = snap(ox), snap(oy)
    items.append('\t(rectangle\n\t\t(start %.2f %.2f)\n\t\t(end %.2f %.2f)\n\t\t(stroke\n\t\t\t(width 0.3)\n\t\t\t(type dash)\n\t\t)\n'
                 '\t\t(fill\n\t\t\t(type none)\n\t\t)\n\t\t(uuid "%s")\n\t)' % (ox, oy, ox + bw, oy + bh, uid()))
    for t, x, y, sz in texts:
        items.append(text_item(t, ox + x, oy + y, size=sz))
    for p, cx, cy, bb, pins, ts in placed:
        syms.append(sym_instance(p, snap(ox + cx), snap(oy + cy), bb, pins, ts, path))

notes = [
    "Part placement only - nothing is wired yet. Dashed boxes = subsystems.",
    "Custom symbols (WhoopFC lib): pinouts from vendor datasheets - re-check before layout.",
    "Variant field 'FPV' = parts only fitted on the VTX/OSD build.",
    "TBD values: RF match, back-EMF dividers, PLL loop filter - copy from Semtech / Bluejay / reference AIO designs.",
    "TPS63802 (VSON-HR-10 DLA) has no stock KiCad footprint - create it from the TI land pattern.",
    "Footprints: signal passives 0201; power-path and >=1uF caps kept 0402/0603 for crack resistance and DC-bias.",
]
items.append(text_item("1S Whoop AIO Flight Controller (STM32G473 / ICM-42688-P / ELRS / 4x Bluejay ESC)", MARGIN, MARGIN, size=4.0))
for k, n_ in enumerate(notes):
    items.append(text_item(n_, MARGIN, MARGIN + 7 + k * 3.5, size=2.0, bold=False))

libs = {p["lib_id"] for sh in SHEETS for _, parts in sh["groups"] for p in parts}
root = ('(kicad_sch\n\t(version 20260306)\n\t(generator "eeschema")\n\t(generator_version "10.0")\n\t(uuid "%s")\n\t(paper %s)\n%s\n%s\n%s\n%s\n'
        '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n'
        % (ROOT_UUID, paper, title_block("1S Whoop AIO Flight Controller", 0), lib_symbols_block(libs), "\n".join(items), "\n".join(syms)))
os.makedirs(OUT, exist_ok=True)
write(os.path.join(OUT, PROJ + ".kicad_sch"), root)

lib = '(kicad_symbol_lib\n\t(version 20251024)\n\t(generator "kicad_symbol_editor")\n\t(generator_version "10.0")\n%s\n)\n' % "\n".join(
    "\t" + CUSTOM[k] for k in sorted(CUSTOM))
write(os.path.join(OUT, CUSTOM_LIB + ".kicad_sym"), lib)
write(os.path.join(OUT, "sym-lib-table"),
      '(sym_lib_table\n  (version 7)\n  (lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s.kicad_sym")(options "")(descr "Custom symbols for the 1S whoop FC"))\n)\n'
      % (CUSTOM_LIB, CUSTOM_LIB))
pro = {"meta": {"filename": PROJ + ".kicad_pro", "version": 3}, "sheets": [[ROOT_UUID, "Root"]]}
write(os.path.join(OUT, PROJ + ".kicad_pro"), json.dumps(pro, indent=2) + "\n")
print("paper", paper, "columns", len(cols), "parts", len(syms))
