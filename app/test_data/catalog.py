"""Synthetic price bands and eligibility dates, not market quotations."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    category: str
    item_code: str
    name: str
    minimum_price: int
    maximum_price: int
    eligible_from: str
    useful_life_days: int


# Group totals for the official 1000-device dataset. Network = 40 + 30 + 30;
# projectors, servers and office equipment = 40 + 30 + 30.
DISTRIBUTION = {"laptop": 300, "desktop": 200, "monitor": 200, "printer": 100,
                "switch": 40, "router": 30, "network": 30, "projector": 40,
                "server": 30, "office": 30}
LOCATIONS = ("NIK", "KGK", "LIB", "BARK", "KANDÓ")
CATALOG = (
    Product("laptop", "LAT5540", "Dell Latitude 5540", 320000, 540000, "2023-07-01", 1825),
    Product("laptop", "LAT5550", "Dell Latitude 5550", 360000, 580000, "2024-07-01", 1825),
    Product("laptop", "T14G4", "Lenovo ThinkPad T14 Gen 4", 420000, 650000, "2023-07-01", 1825),
    Product("laptop", "EB840G10", "HP EliteBook 840 G10", 400000, 620000, "2023-07-01", 1825),
    Product("laptop", "PB450G10", "HP ProBook 450 G10", 270000, 430000, "2023-07-01", 1825),
    Product("desktop", "OPT7010", "Dell OptiPlex 7010", 220000, 420000, "2023-07-01", 2190),
    Product("desktop", "TCM70Q", "Lenovo ThinkCentre M70q", 210000, 410000, "2021-01-01", 2190),
    Product("desktop", "HP800G6", "HP EliteDesk 800 G6", 200000, 380000, "2021-01-01", 2190),
    Product("monitor", "U2723QE", "Dell UltraSharp U2723QE", 150000, 250000, "2022-07-01", 2555),
    Product("monitor", "P2422H", "Dell P2422H", 60000, 110000, "2022-01-01", 2555),
    Product("monitor", "HPE24G4", "HP E24 G4", 55000, 100000, "2021-01-01", 2555),
    Product("printer", "M404DN", "HP LaserJet Pro M404dn", 110000, 190000, "2020-01-01", 2190),
    Product("printer", "M405DN", "HP LaserJet Pro M405dn", 120000, 200000, "2021-01-01", 2190),
    Product("printer", "HLL5200", "Brother HL-L5200DW", 95000, 170000, "2020-01-01", 2190),
    Product("switch", "CAT9200", "Cisco Catalyst 9200", 380000, 850000, "2020-01-01", 2920),
    Product("switch", "CAT2960", "Cisco Catalyst 2960", 150000, 350000, "2020-01-01", 2920),
    Product("router", "ISR1100", "Cisco ISR 1100", 180000, 400000, "2020-01-01", 2555),
    Product("router", "RB4011", "MikroTik RB4011", 70000, 140000, "2020-01-01", 2555),
    Product("network", "U6PRO", "Ubiquiti UniFi U6 Pro", 65000, 110000, "2022-01-01", 2190),
    Product("network", "EAP245", "TP-Link Omada EAP245", 30000, 60000, "2020-01-01", 2190),
    Product("projector", "EBFH52", "Epson EB-FH52", 260000, 430000, "2021-01-01", 2555),
    Product("projector", "MW550", "BenQ MW550", 160000, 270000, "2020-01-01", 2555),
    Product("server", "R450", "Dell PowerEdge R450", 950000, 2100000, "2022-01-01", 2190),
    Product("server", "DL360G10", "HPE ProLiant DL360 Gen10", 900000, 2000000, "2020-01-01", 2190),
    Product("office", "SCANS1300", "Fujitsu ScanSnap S1300i", 80000, 140000, "2020-01-01", 2190),
    Product("office", "BR900", "APC Back-UPS Pro BR900", 70000, 130000, "2020-01-01", 1825),
)
BY_CODE = {product.item_code: product for product in CATALOG}
