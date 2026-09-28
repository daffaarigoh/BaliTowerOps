"""
Generator Data Sintetis & Database Multi-Tenant PT Bali Towerindo Sentra Tbk (Bali Tower)
Mencakup 3 Scope:
1. Inventory & Procurement
2. HR & Recruitment (Cari/Filter Karyawan, Absensi Geolocation Site, Pengajuan Cuti)
3. Finance & Laporan Keuangan (Pemasukan Invoices, Pengeluaran Sewa Lahan/PLN/Lembur, List Transaksi Jurnal Kas)
"""

import os
import sys
import random
from datetime import datetime, timedelta
from pathlib import Path
import duckdb
import pandas as pd

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "balitower"
STORAGE_DIR = BASE_DIR / "storage"
DB_PATH = STORAGE_DIR / "balitower.db"

INV_DIR = DATA_DIR / "01_inventory"
HR_DIR = DATA_DIR / "02_hr_recruitment"
FIN_DIR = DATA_DIR / "03_finance"

for d in [INV_DIR, HR_DIR, FIN_DIR, STORAGE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

random.seed(42)

# ==============================================================================
# SCOPE 2: MASTER SITES (Hubungan Silang untuk HR Geofencing & Finance Leases)
# ==============================================================================
print(">>> [1/7] Menghasilkan Data Master Sites Menara Telekomunikasi...")

SITES_RAW = [
    ("JKS-MCP-001", "MCP Gatot Subroto Kav 18", "Microcell Pole", "DKI Jakarta", 20.0, "OPERATIONAL"),
    ("JKS-MCP-002", "MCP Sudirman SCBD Lot 8", "Microcell Pole", "DKI Jakarta", 22.0, "OPERATIONAL"),
    ("JKP-TWR-003", "Macro Tower Senayan Palmerah", "Macro 4-Legged", "DKI Jakarta", 45.0, "OPERATIONAL"),
    ("JKB-MCP-004", "MCP Tomang Raya Barat", "Microcell Pole", "DKI Jakarta", 18.0, "OPERATIONAL"),
    ("JKT-TWR-005", "Macro Tower Cawang Interchange", "Macro 4-Legged", "DKI Jakarta", 52.0, "OPERATIONAL"),
    ("DPS-MCP-006", "MCP Teuku Umar Denpasar", "Microcell Pole", "Bali & Nusa Tenggara", 20.0, "OPERATIONAL"),
    ("DPS-TWR-007", "Macro Tower Sanur Bypass", "Macro 4-Legged", "Bali & Nusa Tenggara", 42.0, "OPERATIONAL"),
    ("BDG-TWR-008", "Macro Tower Dago Asri", "Monopole", "Jawa Barat", 36.0, "OPERATIONAL"),
    ("BDG-MCP-009", "MCP Riau Junction Bandung", "Microcell Pole", "Jawa Barat", 18.0, "OPERATIONAL"),
    ("SBY-TWR-010", "Macro Tower Darmo Surabaya", "Macro 4-Legged", "Jawa Timur", 48.0, "OPERATIONAL"),
    ("SBY-MCP-011", "MCP Basuki Rahmat Surabaya", "Microcell Pole", "Jawa Timur", 20.0, "OPERATIONAL"),
    ("JKS-MCP-012", "MCP Kemang Raya Selatan", "Microcell Pole", "DKI Jakarta", 20.0, "OPERATIONAL"),
    ("JKP-TWR-013", "Rooftop Pole Cikini Menteng", "Rooftop Pole", "DKI Jakarta", 15.0, "OPERATIONAL"),
    ("TGR-TWR-014", "Macro Tower BSD Green Office", "Monopole", "Banten", 38.0, "OPERATIONAL"),
    ("DPS-MCP-015", "MCP Sunset Road Kuta", "Microcell Pole", "Bali & Nusa Tenggara", 22.0, "OPERATIONAL"),
]

df_sites = pd.DataFrame(SITES_RAW, columns=[
    "site_id", "site_name", "site_type", "region", "tower_height_m", "status"
])
df_sites.to_csv(HR_DIR / "telecom_sites.csv", index=False)

# ==============================================================================
# SCOPE 1: INVENTORY & PROCUREMENT
# ==============================================================================
print(">>> [2/7] Menghasilkan Data Inventory & Logistics...")

SUPPLIERS_RAW = [
    ("SUP-001", "PT Fiber Teknologi Nusantara", "Fiber Optic & Cable", "Budi Santoso", 4.8, "Net 30", "sales@fibertek.co.id", "021-5582910"),
    ("SUP-002", "PT Power Mandiri Prima", "Power & Battery", "Dewi Lestari", 4.7, "Net 45", "corporate@powermandiri.com", "021-8891240"),
    ("SUP-003", "PT Tower Steel Abadi", "Tower Structure & Steel", "Hendra Gunawan", 4.5, "Net 60", "b2b@towersteel.co.id", "021-4478129"),
    ("SUP-004", "PT Delta Cooling System", "Shelter & HVAC", "Ahmad Fauzi", 4.6, "Net 30", "support@deltacooling.id", "022-7201882"),
    ("SUP-005", "PT Surya RF Komunikasi", "RF & Transmission", "Siti Rahmawati", 4.9, "Net 30", "rf-sales@suryarf.com", "021-7890123"),
    ("SUP-006", "PT Furukawa Optical Solutions", "Fiber Optic & Cable", "Kenji Takahashi", 4.9, "Net 30", "contact@furukawa.co.id", "021-8971200"),
    ("SUP-007", "PT Huawei Tech Investment", "RF & Transmission", "Linda Wijaya", 4.8, "Net 45", "enterprise.id@huawei.com", "021-29398888"),
    ("SUP-008", "PT ZTT Cable Indonesia", "Fiber Optic & Cable", "Rian Pratama", 4.7, "Net 45", "sales@zttcable.co.id", "021-89831122"),
    ("SUP-009", "PT Varta Microbattery Indonesia", "Power & Battery", "Agus Setiawan", 4.8, "Net 30", "sales.id@varta.com", "021-52960011"),
    ("SUP-010", "PT Citra Mandiri Genset", "Shelter & HVAC", "Bambang Sudiro", 4.6, "Net 30", "info@citramandirigenset.com", "021-65301199")
]
df_suppliers = pd.DataFrame(SUPPLIERS_RAW, columns=[
    "supplier_id", "supplier_name", "category", "contact_person", "rating", "payment_terms", "email", "phone"
])
df_suppliers.to_csv(INV_DIR / "suppliers.csv", index=False)

WAREHOUSES_RAW = [
    ("WH-JKT-01", "Central Logistics Warehouse Sunter", "Central Warehouse", "DKI Jakarta", "Jl. Danau Sunter Selatan No. 12", 3500, "Agus Sutanto"),
    ("WH-JKB-01", "Logistics Hub Daan Mogot Barat", "Regional Hub", "DKI Jakarta", "Jl. Daan Mogot KM 14 No. 8", 1800, "Hendra Setiawan"),
    ("WH-BDG-01", "Regional Logistics Hub Bandung", "Regional Hub", "Jawa Barat", "Jl. Soekarno Hatta No. 402", 1500, "Ahmad Sofyan"),
    ("WH-SMG-01", "Regional Logistics Hub Semarang", "Regional Hub", "Jawa Tengah", "Jl. Kaligawe Raya KM 5 No. 18", 1200, "Bambang Prasetyo"),
    ("WH-SBY-01", "Regional Logistics Hub Surabaya", "Regional Hub", "Jawa Timur", "Jl. Rungkut Industri III No. 45", 2200, "Tri Wibowo"),
    ("WH-DPS-01", "Regional Logistics Hub Denpasar", "Regional Hub", "Bali & Nusa Tenggara", "Jl. Gatot Subroto Timur No. 88", 1600, "I Made Sudirga"),
    ("WH-MDN-01", "Regional Logistics Hub Medan", "Regional Hub", "Sumatera Utara", "Jl. Medan-Belawan KM 10.5", 1400, "Rizal Siregar"),
    ("WH-MKS-01", "Regional Logistics Hub Makassar", "Regional Hub", "Sulawesi Selatan", "Kawasan Industri Makassar (KIMA) Kav 7", 1100, "Andi Mappanyukki")
]
df_warehouses = pd.DataFrame(WAREHOUSES_RAW, columns=[
    "warehouse_id", "warehouse_name", "warehouse_type", "region", "address", "capacity_sqm", "supervisor"
])
df_warehouses.to_csv(INV_DIR / "warehouses.csv", index=False)

ITEMS_RAW = [
    # 1. Fiber Optic & Cable (9 Items)
    ("BLT-INV-001", "FO-ADSS-24C", "Kabel Fiber Optic ADSS 24 Core Single Mode", "Fiber Optic & Cable", "meter", 14500, 2000, 1000, 7, "SUP-001"),
    ("BLT-INV-002", "FO-ADSS-48C", "Kabel Fiber Optic ADSS 48 Core Single Mode", "Fiber Optic & Cable", "meter", 22000, 1500, 800, 7, "SUP-001"),
    ("BLT-INV-003", "FO-CLOSURE-48", "Optical Splice Closure 48 Core Dome Type", "Fiber Optic & Cable", "unit", 480000, 25, 10, 5, "SUP-001"),
    ("BLT-INV-004", "ODC-144-MOD", "Optical Distribution Cabinet 144 Port Outdoor", "Fiber Optic & Cable", "unit", 4200000, 10, 4, 14, "SUP-001"),
    ("BLT-INV-015", "FO-DUCT-96C", "Kabel Fiber Optic Duct 96 Core Armor Single Mode", "Fiber Optic & Cable", "meter", 38500, 1200, 600, 10, "SUP-008"),
    ("BLT-INV-016", "FO-DROP-2C", "Kabel Drop Cable Figure-8 2 Core FTTH", "Fiber Optic & Cable", "meter", 3200, 3000, 1500, 5, "SUP-006"),
    ("BLT-INV-017", "ODF-144-RK", "Optical Distribution Frame 144 Port Rackmount 19 Inch", "Fiber Optic & Cable", "unit", 2850000, 15, 6, 7, "SUP-006"),
    ("BLT-INV-018", "PATCH-LC-LC", "Patch Cord Fiber Optic LC-LC Duplex Single Mode 3m", "Fiber Optic & Cable", "pcs", 65000, 80, 30, 3, "SUP-006"),
    ("BLT-INV-019", "FO-CLOSURE-96", "Optical Splice Closure 96 Core Heavy Duty Dome", "Fiber Optic & Cable", "unit", 750000, 20, 8, 7, "SUP-008"),

    # 2. Power & Battery (8 Items)
    ("BLT-INV-005", "BAT-LITH-48V", "Baterai Backup Lithium-Ion LiFePO4 48V 100Ah", "Power & Battery", "unit", 18500000, 15, 6, 21, "SUP-002"),
    ("BLT-INV-006", "RECT-MOD-48V", "Rectifier System Module 48V 50A Hot-Swappable", "Power & Battery", "unit", 12000000, 12, 5, 28, "SUP-002"),
    ("BLT-INV-007", "BAT-VRLA-12V", "Baterai VRLA Deep Cycle 12V 100Ah", "Power & Battery", "unit", 3200000, 30, 12, 10, "SUP-002"),
    ("BLT-INV-020", "BAT-LITH-200A", "Baterai Lithium-Ion LiFePO4 48V 200Ah High Capacity", "Power & Battery", "unit", 34000000, 8, 3, 21, "SUP-009"),
    ("BLT-INV-021", "SOL-PANEL-450", "Solar Panel Monocrystalline 450Wp Tier-1", "Power & Battery", "unit", 2400000, 20, 8, 14, "SUP-002"),
    ("BLT-INV-022", "SOL-MPPT-60A", "Solar Charge Controller MPPT 60A 48V Telecom", "Power & Battery", "unit", 3800000, 10, 4, 10, "SUP-002"),
    ("BLT-INV-023", "GEN-PORT-5KV", "Genset Silent Portable Diesel 5kVA Single Phase", "Power & Battery", "unit", 16500000, 6, 2, 14, "SUP-010"),
    ("BLT-INV-024", "ATS-PANEL-100", "Automatic Transfer Switch Panel 100A 3-Phase", "Power & Battery", "unit", 8900000, 8, 3, 14, "SUP-010"),

    # 3. Tower Structure & Steel (8 Items)
    ("BLT-INV-008", "TWR-BOLT-M24", "Baut Angkur Struktur Tower Grade 8.8 M24 Galv", "Tower Structure", "set", 85000, 200, 80, 5, "SUP-003"),
    ("BLT-INV-009", "ANT-BRK-UNIV", "Universal Antenna Mounting Bracket 3-Sector", "Tower Structure", "set", 1450000, 40, 15, 10, "SUP-003"),
    ("BLT-INV-010", "GRD-COP-50MM", "Kabel Tembaga Grounding BC 50mm Anti-Petir", "Tower Structure", "meter", 95000, 300, 100, 4, "SUP-003"),
    ("BLT-INV-025", "GUY-WIRE-8MM", "Kawat Seling Baja Galvanized Guyed Wire 8mm", "Tower Structure", "meter", 28000, 500, 200, 7, "SUP-003"),
    ("BLT-INV-026", "ROD-COP-58", "Grounding Copper Bonded Rod 5/8 Inch x 3 Meter", "Tower Structure", "batang", 320000, 40, 15, 5, "SUP-003"),
    ("BLT-INV-027", "STEP-BOLT-M16", "Step Bolt Climbing Ladder Tower M16 Galvanized", "Tower Structure", "pcs", 45000, 150, 50, 4, "SUP-003"),
    ("BLT-INV-028", "TWR-AVI-LAMP", "Lampu Aviasi Menara Tower LED Solar Medium Intensity", "Tower Structure", "unit", 4500000, 12, 4, 10, "SUP-003"),
    ("BLT-INV-029", "CLAMP-FEEDER", "Cable Clamp Feeder 7/8 Double 3-Way Stainless Steel", "Tower Structure", "pcs", 24000, 300, 100, 4, "SUP-003"),

    # 4. Shelter & HVAC (5 Items)
    ("BLT-INV-011", "AC-INV-1.5PK", "AC Inverter Heavy Duty Shelter 1.5 PK Dual Auto", "Shelter & HVAC", "unit", 7500000, 8, 3, 12, "SUP-004"),
    ("BLT-INV-012", "GEN-FILT-OIL", "Filter Oli & Solar Genset Perkins 15kVA", "Shelter & HVAC", "set", 650000, 35, 15, 4, "SUP-004"),
    ("BLT-INV-030", "SHL-EXH-FAN", "Exhaust Fan Heavy Duty Shelter 12 Inch IP55", "Shelter & HVAC", "unit", 1250000, 15, 6, 7, "SUP-004"),
    ("BLT-INV-031", "FIRE-AER-GEN", "Tabung Pemadam Aerosol Fire Extinguisher Shelter", "Shelter & HVAC", "unit", 3100000, 10, 4, 10, "SUP-004"),
    ("BLT-INV-032", "DOOR-MAG-LCK", "Smart Magnetic Door Lock Shelter RFID & Keypad", "Shelter & HVAC", "set", 2200000, 12, 5, 7, "SUP-004"),

    # 5. RF & Transmission (5 Items)
    ("BLT-INV-013", "SFP-10G-LR", "Transceiver SFP+ 10G 1310nm 10km LC SMF", "RF & Transmission", "pcs", 750000, 50, 20, 14, "SUP-005"),
    ("BLT-INV-014", "FEED-COAX-78", "Kabel Coaxial Feeder 7/8 Low Loss 50 Ohm", "RF & Transmission", "meter", 82000, 500, 200, 14, "SUP-005"),
    ("BLT-INV-033", "SFP-1G-LX", "Transceiver SFP 1.25G 1310nm 20km Single Mode", "RF & Transmission", "pcs", 280000, 60, 25, 10, "SUP-007"),
    ("BLT-INV-034", "JUMP-COAX-2M", "Coaxial Jumper Cable 1/2 DIN Male to DIN Male 2m", "RF & Transmission", "pcs", 420000, 40, 15, 7, "SUP-005"),
    ("BLT-INV-035", "RF-LIGHT-ARR", "RF Coaxial Surge Coaxial Lightning Arrestor 7/16 DIN", "RF & Transmission", "pcs", 890000, 30, 12, 7, "SUP-007")
]
df_items = pd.DataFrame(ITEMS_RAW, columns=[
    "item_id", "item_code", "item_name", "category", "unit", "unit_price", "min_stock", "safety_stock", "lead_time_days", "supplier_id"
])
df_items.to_csv(INV_DIR / "inventory_items.csv", index=False)

# Stock Balances: Sebaran realistis di 8 Hub Gudang dengan status variatif
stock_records = []

def determine_stock_status(qty: int, r_point: int) -> str:
    if qty == 0:
        return "OUT_OF_STOCK"
    elif qty <= r_point * 0.5:
        return "CRITICAL"
    elif qty <= r_point:
        return "LOW_STOCK"
    return "NORMAL"

# Spesifikasi stok khusus regional (q_hand, q_res)
SPECIAL_STOCKS = {
    # Hub Bandung:
    ("WH-BDG-01", "BLT-INV-002"): (450, 0),      # Kabel FO 48 (min 1.500) -> 450 <= 750: CRITICAL
    ("WH-BDG-01", "BLT-INV-003"): (8, 2),        # Closure 48 (min 25) -> 8 <= 12.5: CRITICAL
    ("WH-BDG-01", "BLT-INV-004"): (6, 1),        # ODC-144 (min 10) -> 5 < 6 <= 10: LOW_STOCK (MENIPIS)
    ("WH-BDG-01", "BLT-INV-006"): (2, 0),        # Rectifier (min 12) -> 2 <= 6: CRITICAL
    ("WH-BDG-01", "BLT-INV-001"): (3500, 120),   # Kabel FO 24 (min 2.000) -> NORMAL
    ("WH-BDG-01", "BLT-INV-018"): (65, 10),      # Patch Cord (min 80) -> LOW_STOCK (MENIPIS)
    ("WH-BDG-01", "BLT-INV-025"): (420, 50),     # Guy Wire (min 500) -> LOW_STOCK (MENIPIS)

    # Hub Denpasar Bali: Menipis baterai lithium & solar panel
    ("WH-DPS-01", "BLT-INV-005"): (3, 1),        # Baterai Lith (min 15) -> 3 <= 7.5: CRITICAL
    ("WH-DPS-01", "BLT-INV-021"): (14, 2),       # Solar Panel (min 20) -> 10 < 14 <= 20: LOW_STOCK
    ("WH-DPS-01", "BLT-INV-001"): (4200, 200),
    ("WH-DPS-01", "BLT-INV-010"): (280, 40),
    ("WH-DPS-01", "BLT-INV-026"): (32, 5),
    ("WH-DPS-01", "BLT-INV-013"): (45, 12),

    # Hub Medan: Menipis genset portable
    ("WH-MDN-01", "BLT-INV-023"): (1, 0),        # Genset (min 6) -> 1 <= 3: CRITICAL
    ("WH-MDN-01", "BLT-INV-012"): (22, 2),       # Filter Oli (min 35) -> 17.5 < 22 <= 35: LOW_STOCK
    ("WH-MDN-01", "BLT-INV-008"): (180, 20),
    ("WH-MDN-01", "BLT-INV-014"): (350, 50),

    # Hub Semarang: Menipis drop cable
    ("WH-SMG-01", "BLT-INV-016"): (2000, 300),   # Drop cable (min 3.000) -> 1.500 < 2.000 <= 3.000: LOW_STOCK
    ("WH-SMG-01", "BLT-INV-003"): (18, 2),
    ("WH-SMG-01", "BLT-INV-033"): (40, 8),

    # Hub Surabaya: Menipis baut M24
    ("WH-SBY-01", "BLT-INV-008"): (120, 10),     # Baut M24 (min 200) -> 100 < 120 <= 200: LOW_STOCK
    ("WH-SBY-01", "BLT-INV-009"): (35, 5),
    ("WH-SBY-01", "BLT-INV-004"): (8, 1),
    ("WH-SBY-01", "BLT-INV-015"): (950, 100),

    # Hub Makassar:
    ("WH-MKS-01", "BLT-INV-013"): (32, 2),       # SFP+ 10G (min 50) -> 25 < 32 <= 50: LOW_STOCK
    ("WH-MKS-01", "BLT-INV-006"): (6, 1),
    ("WH-MKS-01", "BLT-INV-007"): (22, 4)
}

for item in ITEMS_RAW:
    item_id = item[0]
    min_stk = item[6]

    # 1. Central Warehouse Sunter (WH-JKT-01) selalu memiliki seluruh 35 item
    wh_jkt = "WH-JKT-01"
    if item_id in ["BLT-INV-005", "BLT-INV-003"]:
        qty_jkt = random.randint(min_stk - 4, min_stk - 1)
    else:
        qty_jkt = random.randint(min_stk + 10, min_stk * 3)
    st_jkt = determine_stock_status(qty_jkt, min_stk)
    res_jkt = random.randint(0, min(qty_jkt, 5))
    stock_records.append((
        f"STK-{wh_jkt}-{item_id}", item_id, wh_jkt, qty_jkt, res_jkt, min_stk, st_jkt, "2026-03-08", "2026-03-08 14:30:00"
    ))

    # 2. Daan Mogot Warehouse (WH-JKB-01) buffer stock untuk 15 item cepat pakai
    if item[3] in ["Fiber Optic & Cable", "Power & Battery"]:
        wh_jkb = "WH-JKB-01"
        qty_jkb = random.randint(min_stk, min_stk * 2)
        st_jkb = determine_stock_status(qty_jkb, min_stk)
        stock_records.append((
            f"STK-{wh_jkb}-{item_id}", item_id, wh_jkb, qty_jkb, 0, min_stk, st_jkb, "2026-03-07", "2026-03-07 11:15:00"
        ))

# Masukkan stok khusus regional yang sudah didefinisikan
for (wh_id, item_id), stock_tuple in SPECIAL_STOCKS.items():
    q_hand = stock_tuple[0]
    q_res = stock_tuple[1]
    item_data = next((it for it in ITEMS_RAW if it[0] == item_id), None)
    min_stk = item_data[6] if item_data else 50
    st = determine_stock_status(q_hand, min_stk)
    stock_records.append((
        f"STK-{wh_id}-{item_id}", item_id, wh_id, q_hand, q_res, min_stk, st, "2026-03-08", "2026-03-08 16:45:00"
    ))

df_stock = pd.DataFrame(stock_records, columns=[
    "balance_id", "item_id", "warehouse_id", "quantity_on_hand", "quantity_reserved", "reorder_point", "stock_status", "last_stock_take_date", "last_updated"
])
df_stock.to_csv(INV_DIR / "stock_balances.csv", index=False)

# Purchase Orders: 16 PO dengan dua status resmi ERP (ORDERED dan DELIVERED)
EMPTY_PR_PO = os.environ.get("EMPTY_PR_PO", "0") == "1" or any(arg in sys.argv for arg in ["--empty-pr-po", "--clean", "--clean-pr-po"])
if EMPTY_PR_PO:
    print(">>> [Mode Reset Bersih] Tabel Purchase Orders dan PR diinisialisasi KOSONG (0 records).")
    po_records = []
else:
    po_records = [
        # Historical Delivered POs (Stok telah masuk fisik di gudang)
        ("PO-2026-001", "PO/BLT/2026/01/012", "SUP-002", "BLT-INV-005", 10, 18500000, 185000000, "DELIVERED", "2026-01-10", "2026-01-31", "2026-01-29", "WH-JKT-01"),
        ("PO-2026-002", "PO/BLT/2026/01/018", "SUP-001", "BLT-INV-001", 5000, 14500, 72500000, "DELIVERED", "2026-01-15", "2026-01-22", "2026-01-22", "WH-BDG-01"),
        ("PO-2026-003", "PO/BLT/2026/02/004", "SUP-003", "BLT-INV-009", 25, 1450000, 36250000, "DELIVERED", "2026-02-05", "2026-02-15", "2026-02-14", "WH-SBY-01"),
        
        # Active ORDERED POs (Menunggu kedatangan barang fisik di gudang untuk menjadi DELIVERED)
        ("PO-2026-004", "PO/BLT/2026/02/029", "SUP-002", "BLT-INV-006", 8, 12000000, 96000000, "ORDERED", "2026-02-20", "2026-03-12", None, "WH-BDG-01"),
        ("PO-2026-005", "PO/BLT/2026/03/002", "SUP-001", "BLT-INV-003", 20, 480000, 9600000, "ORDERED", "2026-03-01", "2026-03-10", None, "WH-BDG-01"),
        ("PO-2026-006", "PO/BLT/2026/03/008", "SUP-008", "BLT-INV-002", 3000, 22000, 66000000, "ORDERED", "2026-03-03", "2026-03-14", None, "WH-BDG-01"),
        ("PO-2026-007", "PO/BLT/2026/03/011", "SUP-009", "BLT-INV-005", 12, 18500000, 222000000, "ORDERED", "2026-03-04", "2026-03-18", None, "WH-DPS-01"),
        ("PO-2026-008", "PO/BLT/2026/03/014", "SUP-002", "BLT-INV-021", 15, 2400000, 36000000, "ORDERED", "2026-03-05", "2026-03-15", None, "WH-DPS-01"),
        ("PO-2026-009", "PO/BLT/2026/03/017", "SUP-010", "BLT-INV-023", 4, 16500000, 66000000, "ORDERED", "2026-03-06", "2026-03-20", None, "WH-MDN-01"),
        ("PO-2026-010", "PO/BLT/2026/03/020", "SUP-006", "BLT-INV-016", 5000, 3200, 16000000, "ORDERED", "2026-03-07", "2026-03-14", None, "WH-SMG-01"),
        ("PO-2026-011", "PO/BLT/2026/03/022", "SUP-003", "BLT-INV-008", 120, 85000, 10200000, "ORDERED", "2026-03-07", "2026-03-17", None, "WH-SBY-01"),
        ("PO-2026-012", "PO/BLT/2026/03/025", "SUP-007", "BLT-INV-033", 40, 280000, 11200000, "ORDERED", "2026-03-08", "2026-03-22", None, "WH-MKS-01"),
        ("PO-2026-013", "PO/BLT/2026/03/028", "SUP-004", "BLT-INV-011", 5, 7500000, 37500000, "ORDERED", "2026-03-08", "2026-03-25", None, "WH-JKT-01"),
        ("PO-2026-014", "PO/BLT/2026/03/030", "SUP-001", "BLT-INV-004", 4, 4200000, 16800000, "ORDERED", "2026-03-09", "2026-03-23", None, "WH-JKB-01"),
        ("PO-2026-015", "PO/BLT/2026/03/032", "SUP-003", "BLT-INV-025", 300, 28000, 8400000, "ORDERED", "2026-03-09", "2026-03-20", None, "WH-BDG-01"),
        ("PO-2026-016", "PO/BLT/2026/03/035", "SUP-005", "BLT-INV-013", 25, 750000, 18750000, "ORDERED", "2026-03-09", "2026-03-24", None, "WH-JKT-01"),
    ]

df_po = pd.DataFrame(po_records, columns=[
    "po_id", "po_number", "supplier_id", "item_id", "order_quantity", "unit_price", "total_amount", "status", "order_date", "expected_delivery", "actual_delivery", "warehouse_id"
])
df_po["pr_number"] = None
if EMPTY_PR_PO:
    df_po = df_po.astype({
        "po_id": "string",
        "po_number": "string",
        "supplier_id": "string",
        "item_id": "string",
        "order_quantity": "int64",
        "unit_price": "float64",
        "total_amount": "float64",
        "status": "string",
        "order_date": "string",
        "expected_delivery": "string",
        "actual_delivery": "string",
        "warehouse_id": "string",
        "pr_number": "string",
    })
else:
    df_po["pr_number"] = df_po["pr_number"].astype("string")
df_po.to_csv(INV_DIR / "purchase_orders.csv", index=False)

if EMPTY_PR_PO:
    print(">>> [Mode Reset Bersih] Menghapus berkas PDF sisa di direktori storage...")
    for sub in ["documents", "pending", "approved", "rejected", "purchase_orders"]:
        p = STORAGE_DIR / sub
        if p.exists():
            for f in p.glob("*.pdf"):
                try:
                    f.unlink()
                except Exception as e:
                    print(f"Warning: gagal menghapus {f}: {e}")


# ==============================================================================
# SCOPE 2: HR & RECRUITMENT
# ==============================================================================
print(">>> [3/7] Menghasilkan Data HR & Recruitment (Karyawan, Absensi GPS, Cuti, Pelamar)...")

EMPLOYEES_RAW = [
    ("EMP-BLT-001", "Budi Santoso", "Field Operations", "Lead Tower Rigger", "PERMANENT", "TKPK 2", "2027-08-15", 10, 75000),
    ("EMP-BLT-002", "Dedi Kurniawan", "Field Operations", "Tower Climber Specialist", "PERMANENT", "TKPK 1", "2027-04-10", 12, 65000),
    ("EMP-BLT-003", "Ahmad Fauzi", "Field Operations", "Fiber Optic Splicer Lead", "PERMANENT", "K3 Umum", "2026-12-01", 8, 70000),
    ("EMP-BLT-004", "I Made Sudira", "Field Operations", "Regional Field Technician Bali", "PERMANENT", "TKPK 1", "2027-01-20", 11, 65000),
    ("EMP-BLT-005", "Eko Prasetyo", "Field Operations", "Preventive Maintenance Lead", "PERMANENT", "K3 Listrik & Genset", "2028-02-14", 9, 80000),
    ("EMP-BLT-006", "Rian Hidayat", "NOC & Infrastructure", "NOC Shift Lead Tier-2", "PERMANENT", "NONE", None, 14, 85000),
    ("EMP-BLT-007", "Fajar Nugraha", "NOC & Infrastructure", "NOC Surveillance Specialist", "CONTRACT (PKWT)", "NONE", None, 6, 60000),
    ("EMP-BLT-008", "Siti Rahmawati", "Finance & Accounting", "Senior Billing & AR Accountant", "PERMANENT", "NONE", None, 12, 90000),
    ("EMP-BLT-009", "Dewi Lestari", "Finance & Accounting", "Treasury & Site Cost Specialist", "PERMANENT", "NONE", None, 10, 75000),
    ("EMP-BLT-010", "Hendra Gunawan", "Project Engineering", "Site Acquisition & CME Inspector", "PERMANENT", "K3 Umum", "2026-11-30", 7, 85000),
    ("EMP-BLT-011", "Yusuf Maulana", "Field Operations", "Junior Fiber Splicer", "CONTRACT (PKWT)", "K3 Umum", "2027-03-01", 5, 55000),
    ("EMP-BLT-012", "Agus Setiawan", "Field Operations", "Junior Tower Climber", "CONTRACT (PKWT)", "TKPK 1", "2026-10-15", 8, 55000),
]
df_employees = pd.DataFrame(EMPLOYEES_RAW, columns=[
    "employee_id", "full_name", "department", "job_title", "employment_status", "k3_certification", "k3_cert_expiry", "leave_balance", "hourly_overtime_rate"
])
df_employees.to_csv(HR_DIR / "employees.csv", index=False)

# Log Absensi Realistis (30 hari terakhir, ada geofencing validasi site)
attendance_records = []
att_id_counter = 1001
base_date = datetime.now().date() - timedelta(days=25)

# Peta teknisi ke site terdekat
field_techs = ["EMP-BLT-001", "EMP-BLT-002", "EMP-BLT-003", "EMP-BLT-004", "EMP-BLT-005", "EMP-BLT-011", "EMP-BLT-012"]
sites_ids = [s[0] for s in SITES_RAW]

for day_offset in range(25):
    cur_date = base_date + timedelta(days=day_offset)
    if cur_date.weekday() >= 5:  # Weekend hanya ada standby/emergency lembur
        for tech in ["EMP-BLT-001", "EMP-BLT-005"]:
            if random.random() < 0.4:
                chosen_site = random.choice(sites_ids[:5])
                ot_hours = round(random.choice([3.0, 4.5, 6.0]), 1)
                attendance_records.append((
                    f"ATT-{att_id_counter}", tech, str(cur_date), "09:12:00", "15:45:00",
                    chosen_site, "EMERGENCY_REPAIR", ot_hours, "OVERTIME_VERIFIED"
                ))
                att_id_counter += 1
        continue

    # Weekday normal attendance
    for emp in EMPLOYEES_RAW:
        emp_id = emp[0]
        dept = emp[2]
        
        if dept == "Field Operations":
            chosen_site = random.choice(sites_ids)
            # Kadang ada lembur penarikan kabel atau perbaikan genset
            ot_hours = round(random.choice([0.0, 0.0, 1.5, 2.5, 3.0]), 1) if random.random() < 0.45 else 0.0
            clock_in = f"07:{random.randint(45, 59):02d}:00" if random.random() > 0.1 else f"08:{random.randint(15, 30):02d}:00"
            status = "ON_TIME" if clock_in.startswith("07") else "LATE"
            if ot_hours > 0:
                status = "OVERTIME_VERIFIED"
            clock_out = "17:00:00" if ot_hours == 0 else f"{17 + int(ot_hours)}:{int((ot_hours % 1)*60):02d}:00"

            attendance_records.append((
                f"ATT-{att_id_counter}", emp_id, str(cur_date), clock_in, clock_out,
                chosen_site, "SITE_VISIT", ot_hours, status
            ))
            att_id_counter += 1
        else:
            # Office / NOC attendance
            clock_in = f"08:{random.randint(15, 55):02d}:00"
            clock_out = "17:05:00"
            attendance_records.append((
                f"ATT-{att_id_counter}", emp_id, str(cur_date), clock_in, clock_out,
                None, "OFFICE_REGULAR", 0.0, "ON_TIME"
            ))
            att_id_counter += 1

df_attendances = pd.DataFrame(attendance_records, columns=[
    "attendance_id", "employee_id", "date", "clock_in", "clock_out", "site_id", "attendance_type", "overtime_hours", "status"
])
df_attendances.to_csv(HR_DIR / "attendances.csv", index=False)

# Cuti & Perizinan
leave_records = [
    ("LV-2026-001", "EMP-BLT-001", "ANNUAL_LEAVE", "2026-01-20", "2026-01-22", 3, "Keperluan keluarga ke luar kota", "EMP-BLT-002", "APPROVED", "EMP-BLT-005"),
    ("LV-2026-002", "EMP-BLT-003", "SICK_LEAVE", "2026-02-10", "2026-02-11", 2, "Demam tinggi & istirahat dokter (surat terlampir)", "EMP-BLT-011", "APPROVED", "EMP-BLT-005"),
    ("LV-2026-003", "EMP-BLT-007", "ANNUAL_LEAVE", "2026-02-25", "2026-02-27", 3, "Cuti tahunan keperluan pribadi", "EMP-BLT-006", "APPROVED", "EMP-BLT-006"),
    ("LV-2026-004", "EMP-BLT-004", "ANNUAL_LEAVE", "2026-03-12", "2026-03-14", 3, "Upacara adat di Denpasar", "EMP-BLT-002", "PENDING_APPROVAL", None),
    ("LV-2026-005", "EMP-BLT-012", "EMERGENCY_LEAVE", "2026-03-02", "2026-03-02", 1, "Keluarga musibah banjir", "EMP-BLT-002", "APPROVED", "EMP-BLT-005"),
]
df_leave = pd.DataFrame(leave_records, columns=[
    "leave_id", "employee_id", "leave_type", "start_date", "end_date", "days_requested", "reason", "substitute_employee_id", "approval_status", "approved_by"
])
df_leave.to_csv(HR_DIR / "leave_requests.csv", index=False)

# Job Postings & Candidates (Flow Cari & Filter Karyawan)
JOB_POSTINGS_RAW = [
    ("JOB-2026-01", "Tower Rigger / Climber Technician", "Field Operations", "TKPK 1", 2, "Jakarta Selatan", 3, "OPEN"),
    ("JOB-2026-02", "Fiber Optic Splicing Engineer", "Field Operations", "K3 Umum", 1, "Denpasar Bali", 2, "OPEN"),
    ("JOB-2026-03", "NOC Surveillance Specialist 24/7", "NOC & Infrastructure", "NONE", 1, "Jakarta Pusat", 2, "OPEN"),
    ("JOB-2026-04", "Site Acquisition & Permit Officer", "Project Engineering", "NONE", 2, "Bandung", 1, "CLOSED")
]
df_jobs = pd.DataFrame(JOB_POSTINGS_RAW, columns=[
    "job_id", "job_title", "department", "required_k3_cert", "min_experience_years", "location", "quota", "status"
])
df_jobs.to_csv(HR_DIR / "job_postings.csv", index=False)

CANDIDATES_RAW = [
    ("CND-2026-001", "JOB-2026-01", "Ilham Ramadhan", "ilham.ramadhan@email.com", "08128891001", "Jakarta Selatan", "TKPK 1", 3, "FIT_FOR_HEIGHT", 92.5, "INTERVIEW"),
    ("CND-2026-002", "JOB-2026-01", "Bagus Triatmodjo", "bagus.tri@email.com", "08137782910", "Depok", "TKPK 2", 4, "FIT_FOR_HEIGHT", 95.0, "TRIAL"),
    ("CND-2026-003", "JOB-2026-01", "Ari Wibowo", "ari.wib@email.com", "08569918231", "Tangerang", "NONE", 1, "UNFIT (Hipertensi)", 60.0, "REJECTED"),
    ("CND-2026-004", "JOB-2026-01", "Faris Kurnia", "faris.kurnia@email.com", "08129988112", "Bekasi", "TKPK 1", 2, "PENDING_MCU", 84.0, "SCREENED"),
    ("CND-2026-005", "JOB-2026-02", "Ketut Suardika", "ketut.suardika@email.com", "08192288331", "Denpasar", "K3 Umum", 3, "FIT_FOR_HEIGHT", 91.0, "TRIAL"),
    ("CND-2026-006", "JOB-2026-02", "Gede Wira Sanjaya", "gede.wira@email.com", "08183399120", "Badung", "K3 Umum", 2, "FIT_FOR_HEIGHT", 88.5, "SCREENED"),
    ("CND-2026-007", "JOB-2026-03", "Nadia Putri", "nadia.putri@email.com", "08127711223", "Jakarta Timur", "NONE", 2, "FIT_FOR_HEIGHT", 89.0, "INTERVIEW"),
    ("CND-2026-008", "JOB-2026-03", "Kevin Aditya", "kevin.aditya@email.com", "08139900112", "Jakarta Pusat", "NONE", 1, "FIT_FOR_HEIGHT", 82.0, "APPLIED"),
]
df_candidates = pd.DataFrame(CANDIDATES_RAW, columns=[
    "candidate_id", "job_id", "full_name", "email", "phone", "current_city", "k3_cert_held", "years_of_experience", "medical_checkup_status", "technical_score", "recruitment_stage"
])
df_candidates.to_csv(HR_DIR / "candidates.csv", index=False)


# ==============================================================================
# SCOPE 3: FINANCE & LAPORAN KEUANGAN
# ==============================================================================
print(">>> [4/7] Menghasilkan Data Finance & Accounting (Invoices, Land Leases, PLN Utilities)...")

CLIENTS_RAW = [
    ("CLI-001", "PT Telekomunikasi Selular (Telkomsel)", "OPERATOR_SELULER", "01.000.123.4-091.000", "billing@telkomsel.co.id", "Net 30"),
    ("CLI-002", "PT Indosat Ooredoo Hutchison Tbk", "OPERATOR_SELULER", "01.000.456.7-092.000", "finance.tower@ioh.co.id", "Net 45"),
    ("CLI-003", "PT XL Axiata Tbk", "OPERATOR_SELULER", "01.000.789.0-093.000", "sitelease@xl.co.id", "Net 30"),
    ("CLI-004", "PT Smartfren Telecom Tbk", "OPERATOR_SELULER", "01.000.321.9-094.000", "ar-inquiry@smartfren.com", "Net 60"),
    ("CLI-005", "PT Bank Central Asia Tbk (Corporate FO)", "ENTERPRISE", "01.000.999.1-011.000", "it-procurement@bca.co.id", "Net 30"),
]
df_clients = pd.DataFrame(CLIENTS_RAW, columns=["client_id", "client_name", "client_type", "npwp", "billing_email", "payment_terms"])
df_clients.to_csv(FIN_DIR / "telecom_clients.csv", index=False)

# Master Lease Agreements (MLA) Sewa Menara
MLA_CONTRACTS_RAW = [
    ("MLA-2026-001", "CLI-001", "JKS-MCP-001", 24000000, "QUARTERLY", "2024-01-01", "2029-12-31", "ACTIVE"),
    ("MLA-2026-002", "CLI-001", "JKP-TWR-003", 38000000, "QUARTERLY", "2023-06-01", "2028-05-31", "ACTIVE"),
    ("MLA-2026-003", "CLI-002", "JKS-MCP-002", 22500000, "QUARTERLY", "2024-03-01", "2029-02-28", "ACTIVE"),
    ("MLA-2026-004", "CLI-003", "DPS-TWR-007", 32000000, "QUARTERLY", "2023-01-01", "2028-12-31", "ACTIVE"),
    ("MLA-2026-005", "CLI-003", "BDG-TWR-008", 29000000, "QUARTERLY", "2024-05-01", "2029-04-30", "ACTIVE"),
    ("MLA-2026-006", "CLI-004", "SBY-TWR-010", 28000000, "QUARTERLY", "2024-02-01", "2029-01-31", "ACTIVE"),
    ("MLA-2026-007", "CLI-005", "JKS-MCP-012", 18500000, "MONTHLY", "2025-01-01", "2027-12-31", "ACTIVE"),
]
df_mla = pd.DataFrame(MLA_CONTRACTS_RAW, columns=[
    "contract_id", "client_id", "site_id", "monthly_rate", "billing_frequency", "start_date", "end_date", "status"
])
df_mla.to_csv(FIN_DIR / "mla_contracts.csv", index=False)

# Revenue Invoices (Pemasukan)
INVOICES_RAW = [
    ("INV-2026-001", "INV/BLT/2026/01/014", "MLA-2026-001", "CLI-001", "2026-Q1", 72000000, 7920000, 79920000, "2026-01-05", "2026-02-05", "PAID", "2026-02-02"),
    ("INV-2026-002", "INV/BLT/2026/01/015", "MLA-2026-002", "CLI-001", "2026-Q1", 114000000, 12540000, 126540000, "2026-01-05", "2026-02-05", "PAID", "2026-02-04"),
    ("INV-2026-003", "INV/BLT/2026/01/021", "MLA-2026-003", "CLI-002", "2026-Q1", 67500000, 7425000, 74925000, "2026-01-10", "2026-02-25", "PAID", "2026-02-23"),
    ("INV-2026-004", "INV/BLT/2026/01/028", "MLA-2026-004", "CLI-003", "2026-Q1", 96000000, 10560000, 106560000, "2026-01-15", "2026-02-15", "PAID", "2026-02-12"),
    ("INV-2026-005", "INV/BLT/2026/01/035", "MLA-2026-005", "CLI-003", "2026-Q1", 87000000, 9570000, 96570000, "2026-01-15", "2026-02-15", "PAID", "2026-02-14"),
    ("INV-2026-006", "INV/BLT/2026/02/008", "MLA-2026-006", "CLI-004", "2026-Q1", 84000000, 9240000, 93240000, "2026-02-01", "2026-04-01", "UNPAID", None),
    ("INV-2026-007", "INV/BLT/2026/02/012", "MLA-2026-007", "CLI-005", "2026-02", 18500000, 2035000, 20535000, "2026-02-01", "2026-03-01", "PAID", "2026-02-28"),
    ("INV-2026-008", "INV/BLT/2026/03/001", "MLA-2026-007", "CLI-005", "2026-03", 18500000, 2035000, 20535000, "2026-03-01", "2026-04-01", "UNPAID", None),
]
df_invoices = pd.DataFrame(INVOICES_RAW, columns=[
    "invoice_id", "invoice_number", "contract_id", "client_id", "period_covered", "amount_subtotal", "tax_ppn", "total_billed", "invoice_date", "due_date", "payment_status", "payment_date"
])
df_invoices.to_csv(FIN_DIR / "revenue_invoices.csv", index=False)

# Pengeluaran: Sewa Lahan Menara (Land Lease OPEX)
LAND_LEASES_RAW = [
    ("LND-001", "JKS-MCP-001", "Bapak H. Solehuddin (Warga)", 45000000, 5, "2022-01-01", "2027-01-01", "ACTIVE_PAID"),
    ("LND-002", "JKS-MCP-002", "Pengelola Gedung Menara Mandiri SCBD", 85000000, 5, "2023-03-01", "2028-03-01", "ACTIVE_PAID"),
    ("LND-003", "JKP-TWR-003", "Yayasan Pendidikan Senayan", 95000000, 10, "2020-06-01", "2030-06-01", "ACTIVE_PAID"),
    ("LND-004", "DPS-TWR-007", "Desa Adat Sanur Bali", 60000000, 10, "2021-01-01", "2031-01-01", "ACTIVE_PAID"),
    ("LND-005", "BDG-TWR-008", "Bapak Dadan Ramdani", 40000000, 5, "2024-05-01", "2029-05-01", "ACTIVE_PAID"),
    ("LND-006", "SBY-TWR-010", "PT Darmo Property Sentosa", 75000000, 5, "2021-04-01", "2026-04-01", "DUE_FOR_RENEWAL"),
]
df_land_leases = pd.DataFrame(LAND_LEASES_RAW, columns=[
    "lease_id", "site_id", "landowner_name", "annual_lease_cost", "lease_duration_years", "start_date", "end_date", "status"
])
df_land_leases.to_csv(FIN_DIR / "site_land_leases.csv", index=False)

# Pengeluaran: Listrik PLN & BBM Genset Site (Utility OPEX)
UTILITIES_RAW = [
    ("UTL-2026-01", "JKS-MCP-001", "2026-01", "541100918231", 3120, 4980000, 0, 0, 4980000, "PAID"),
    ("UTL-2026-02", "JKS-MCP-002", "2026-01", "541100918242", 3450, 5520000, 0, 0, 5520000, "PAID"),
    ("UTL-2026-03", "JKP-TWR-003", "2026-01", "541100918255", 5890, 9424000, 45, 675000, 10099000, "PAID"),
    ("UTL-2026-04", "DPS-TWR-007", "2026-01", "543200112991", 4920, 7872000, 30, 450000, 8322000, "PAID"),
    ("UTL-2026-05", "BDG-TWR-008", "2026-01", "542100889102", 4100, 6560000, 0, 0, 6560000, "PAID"),
    ("UTL-2026-06", "JKS-MCP-001", "2026-02", "541100918231", 3050, 4880000, 0, 0, 4880000, "PAID"),
    ("UTL-2026-07", "JKP-TWR-003", "2026-02", "541100918255", 6010, 9616000, 60, 900000, 10516000, "PAID"),
]
df_utilities = pd.DataFrame(UTILITIES_RAW, columns=[
    "utility_id", "site_id", "billing_period", "pln_meter_id", "pln_kwh_used", "pln_cost", "genset_fuel_liters", "genset_fuel_cost", "total_utility_cost", "payment_status"
])
df_utilities.to_csv(FIN_DIR / "site_utilities_cost.csv", index=False)

# Note: financial_transactions (general ledger) decommissioned to match active dashboard UI


# ==============================================================================
# DATABASE DUCKDB CREATION & LOADING
# ==============================================================================
print(f">>> [5/7] Memuat Seluruh Tabel ke Database DuckDB di: {DB_PATH}...")

if DB_PATH.exists():
    try:
        DB_PATH.unlink()
    except Exception:
        pass

conn = duckdb.connect(str(DB_PATH))

# Scope 1 Tables
conn.execute("CREATE OR REPLACE TABLE suppliers AS SELECT * FROM df_suppliers;")
conn.execute("CREATE OR REPLACE TABLE warehouses AS SELECT * FROM df_warehouses;")
conn.execute("CREATE OR REPLACE TABLE inventory_items AS SELECT * FROM df_items;")
conn.execute("CREATE OR REPLACE TABLE stock_balances AS SELECT * FROM df_stock;")
conn.execute("CREATE OR REPLACE TABLE purchase_orders AS SELECT * FROM df_po;")

# Scope 2 Tables
conn.execute("CREATE OR REPLACE TABLE telecom_sites AS SELECT * FROM df_sites;")
conn.execute("CREATE OR REPLACE TABLE employees AS SELECT * FROM df_employees;")
conn.execute("CREATE OR REPLACE TABLE leave_requests AS SELECT * FROM df_leave;")
conn.execute("CREATE OR REPLACE TABLE job_postings AS SELECT * FROM df_jobs;")
conn.execute("CREATE OR REPLACE TABLE candidates AS SELECT * FROM df_candidates;")

# Scope 3 Tables
conn.execute("CREATE OR REPLACE TABLE telecom_clients AS SELECT * FROM df_clients;")
conn.execute("CREATE OR REPLACE TABLE mla_contracts AS SELECT * FROM df_mla;")
conn.execute("CREATE OR REPLACE TABLE revenue_invoices AS SELECT * FROM df_invoices;")
conn.execute("CREATE OR REPLACE TABLE site_land_leases AS SELECT * FROM df_land_leases;")
conn.execute("CREATE OR REPLACE TABLE site_utilities_cost AS SELECT * FROM df_utilities;")

# System & Auth Tables (for Login & Workflow Engine)
conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id VARCHAR PRIMARY KEY,
        username VARCHAR NOT NULL UNIQUE,
        password_hash VARCHAR NOT NULL,
        role VARCHAR NOT NULL,
        tenant_id VARCHAR NOT NULL
    );
""")
conn.execute("DELETE FROM users;")
admin_hash = "$2b$12$reziVbiqV1qNNnELI.rGjeE7dJOMBhtT3C6/J3oP4foGl8JaE7ujm" # admin123
user_hash = "$2b$12$/GHm/zDxQu4BNJ0DX0VBB.Msd3hWRvLEOl.6eo20LIFxXTiYBoLX." # user123
users_data = [
    ("USR-001", "admin", admin_hash, "ADMIN", "ALL"),
    ("USR-002", "usera", user_hash, "USER", "INVENTORY"),
    ("USR-003", "userb", user_hash, "USER", "HR"),
    ("USR-004", "userc", user_hash, "USER", "FINANCE")
]
conn.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?);", users_data)

conn.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key VARCHAR PRIMARY KEY,
        value TEXT NOT NULL
    );
""")
conn.execute("DELETE FROM system_settings;")
default_prompt = (
    "Anda adalah Asisten AI Terpadu PT Bali Towerindo Sentra Tbk (Bali Tower).\n"
    "Anda memiliki akses ke 3 domain data operasional: "
    "1) Logistik Material & Stok Tower/FO, 2) HR & Teknisi Lapangan (Cuti, Rekrutmen K3), 3) Keuangan (Sewa Menara, Listrik PLN, Sewa Lahan).\n"
    "Berikan respon berbasis data yang akurat, terstruktur, dan profesional dalam Bahasa Indonesia."
)
conn.execute("INSERT INTO system_settings VALUES ('system_prompt', ?)", [default_prompt])

conn.execute("""
    CREATE TABLE IF NOT EXISTS workflows (
        id VARCHAR PRIMARY KEY,
        name VARCHAR NOT NULL,
        description TEXT,
        business_instruction TEXT NOT NULL,
        compiled_json TEXT NOT NULL,
        tenant_id VARCHAR DEFAULT 'ALL',
        example_prompts TEXT DEFAULT '[]'
    );
""")
conn.execute("DELETE FROM workflows;")
import json

workflows_file = DATA_DIR / "balitower" / "workflows.json"
if not workflows_file.exists():
    workflows_file = DATA_DIR / "workflows.json"

if workflows_file.exists():
    with open(workflows_file, "r", encoding="utf-8") as f:
        wfs_json = json.load(f)
        wf_list = [
            (
                w["id"],
                w["name"],
                w.get("description", ""),
                w.get("business_instruction", ""),
                json.dumps(w.get("compiled_json", {})),
                w.get("tenant_id", "ALL"),
                json.dumps(w.get("example_prompts", []), ensure_ascii=False)
            )
            for w in wfs_json
        ]
else:
    wf_list = [
        ("WF-A01", "Pipeline Pengadaan Material PR-to-PO End-to-End", "Alur pengadaan otomatis terintegrasi dari inspeksi stok, penerbitan PR draf, approval email, hingga penerbitan PO ke vendor.", "Periksa seluruh saldo stok material menara dan kabel fiber optic di gudang logistik usera yang berada di bawah ambang batas minimum. Hitung kuantitas reorder dan vendor rekanan terbaik, terbitkan dokumen resmi Purchase Requisition (PR) dan draf PO PENDING_APPROVAL, lalu kirim email notifikasi ke manajer.", json.dumps({"workflow": "pipeline_pengadaan_material_pr_to_po_end_to_end", "steps": [{"type": "tool", "tool": "inventory.get_low_stock_products"}, {"type": "agent", "task": "calculate_reorder_quantity"}, {"type": "tool", "tool": "docgen.compile"}, {"type": "tool", "tool": "notification.dispatch"}]}), "INVENTORY", json.dumps(["Periksa stok menara yang menipis dan buatkan draf PR"])),
        ("WF-A02", "Penerimaan Barang Fisik PO & Update Saldo", "Verifikasi barang Purchase Order (PO) yang tiba di gudang logistik dan sinkronisasi penambahan stok fisik.", "Verifikasi kedatangan barang Purchase Order yang tiba di gudang, catat penerimaan aktual, update status DELIVERED, dan tambahkan stok ke saldo gudang.", json.dumps({"workflow": "usera_po_goods_receipt", "steps": [{"type": "tool", "tool": "inventory.check_specific_stock"}, {"type": "tool", "tool": "inventory.crud_record"}, {"type": "tool", "tool": "notification.dispatch"}]}), "INVENTORY", json.dumps(["Catat penerimaan PO/BLT/2026/09/031 untuk semua gudang"])),
        ("WF-6D8863", "Mutasi Karyawan", "Melakukan mutasi departemen dan posisi/jabatan karyawan dengan data yang baru.", "Lakukan pembaruan posisi atau departemen karyawan aktif di tabel employees sesuai input user, lalu konfirmasi perubahan datanya.", json.dumps({"workflow": "mutasi_karyawan", "steps": [{"type": "tool", "tool": "hr.update_employee_mutation"}]}), "HR", json.dumps(["Mutasi Dewi Lestari ke departemen IT dengan jabatan Full Stack", "Pindahkan Budi Santoso ke departemen Project Engineering dengan jabatan Site Supervisor"])),
        ("WF-B02", "Filter & Screening Pelamar Teknisi K3", "Menyaring kandidat teknisi lapangan secara dinamis berdasarkan kualifikasi posisi dan sertifikasi K3 (TKPK Tingkat 1, TKPK Tingkat 2, K3 Umum, atau seluruh pelamar).", "Filter dan seleksi kandidat pelamar teknisi secara dinamis sesuai kriteria sertifikasi K3 (TKPK Tingkat 1, TKPK Tingkat 2, K3 Umum) atau seluruh kandidat sesuai permintaan pengguna.", json.dumps({"workflow": "hr_filter_candidates", "steps": [{"type": "tool", "tool": "hr.filter_candidates"}]}), "HR", json.dumps(["Filter kandidat rigger tower yang memiliki sertifikat TKPK tingkat 2"])),
        ("WF-B03", "Pengajuan Cuti Teknisi dan Penerbitan Dokumen PDF HR", "Mencatat permohonan cuti teknisi ke database DuckDB, mencetak formulir resmi PDF Typst, dan mendistribusikan notifikasi email ke HR.", "Catat permohonan cuti karyawan ke dalam database, cetak formulir resmi cuti format PDF dengan kop surat PT Bali Towerindo Sentra Tbk, lalu kirimkan notifikasi dan lampiran PDF ke email HR.", json.dumps({"workflow": "pengajuan-cuti-teknisi-dan-penerbitan-dokumen-pdf-hr", "steps": [{"type": "tool", "tool": "hr.submit_leave_request"}, {"type": "tool", "tool": "docgen.compile_leave_pdf"}, {"type": "tool", "tool": "notification.send_email"}]}), "HR", json.dumps(["Ajukan cuti tahunan 3 hari untuk teknisi Budi Santoso mulai besok"])),
        ("WF-C01", "Laporan Pendapatan Sewa Menara", "Rekapitulasi tagihan invoice sewa menara ke operator telekomunikasi (Telkomsel, XL, IOH).", "Tarik data invoice sewa menara per operator dan status pembayarannya.", json.dumps({"workflow": "finance_revenue_report", "steps": [{"type": "tool", "tool": "finance.revenue_report"}]}), "FINANCE", json.dumps(["Tampilkan rekapitulasi invoice sewa menara per operator dan status pembayarannya"])),
        ("WF-C02", "Audit Beban Listrik & Sewa Lahan", "Laporan pengeluaran operasional utilitas listrik PLN, BBM genset, dan sewa lahan tower.", "Analisis beban operasional per site mencakup tagihan PLN dan jatuh tempo sewa tanah.", json.dumps({"workflow": "finance_opex_audit", "steps": [{"type": "tool", "tool": "finance.opex_audit"}]}), "FINANCE", json.dumps(["Audit pengeluaran operasional listrik PLN dan sewa lahan menara regional Jawa Barat"])),
        ("WF-C04", "Pendaftaran Klien Operator & Kontrak Sewa Menara Baru (Otorisasi Email)", "Pendaftaran operator telekomunikasi baru dan penerbitan draf kontrak sewa menara (MLA). Sistem menyimpan draf ke basis data dengan status PENDING_APPROVAL dan mengklarifikasi atau mengirimkan berkas faktur serta tombol otorisasi persetujuan ke email Finance Manager.", "Susun draf pendaftaran operator klien baru dan kontrak sewa menara (MLA) ke dalam basis data dengan status PENDING_APPROVAL. Hitung estimasi tagihan invoice perdana. Jika pengguna menyertakan email tujuan, kirimkan faktur perdana dan tombol otorisasi persetujuan ke email tersebut. Jika tidak, berikan klarifikasi apakah berkas cukup disimpan di database atau dikirimkan ke email otorisasi.", json.dumps({"workflow": "pendaftaran-klien-operator-dan-kontrak-sewa-menara", "steps": [{"type": "tool", "tool": "finance.draft_client_onboarding"}, {"type": "agent", "task": "agent.reason_and_validate"}, {"type": "tool", "tool": "notification.send_email"}]}), "FINANCE", json.dumps(["Daftarkan kontrak sewa menara baru untuk operator Telkomsel selama 5 tahun dengan tarif 15 juta per bulan dan kirimkan ke email finance.mgr@balitower.co.id"])),
        ("WF-ALL-01", "Cek Profil Akun & Hak Akses", "Melihat informasi profil pengguna yang sedang login, role, divisi tenant, dan modul yang dapat diakses.", "Periksa akun yang sedang login dan tampilkan detail hak akses serta batasan divisi.", json.dumps({"workflow": "check_user_profile", "steps": [{"type": "tool", "tool": "system.check_profile"}]}), "ALL", json.dumps(["Tampilkan informasi profil akun dan batasan hak akses divisi"])),
        ("WF-ALL-02", "Informasi Sistem & Status Layanan", "Melihat ringkasan status operasional server, versi aplikasi, database DuckDB, dan gateway AI.", "Cek status operasional seluruh modul sistem AutoRestock-Agent.", json.dumps({"workflow": "system_health_info", "steps": [{"type": "tool", "tool": "system.get_system_info"}]}), "ALL", json.dumps(["status kesehatan sistem saat ini"])),
        ("WF-ALL-03", "Panduan Operasional & Kontak Darurat", "Panduan SOP penggunaan sistem AutoRestock-Agent, navigasi modul, dan kontak darurat IT/Operasional.", "Tampilkan panduan operasional perusahaan dan kontak darurat lintas divisi.", json.dumps({"workflow": "company_guidelines", "steps": [{"type": "tool", "tool": "system.get_company_guidelines"}]}), "ALL", json.dumps(["Tampilkan panduan operasional perusahaan dan kontak darurat helpdesk"]))
    ]
conn.executemany("INSERT INTO workflows VALUES (?, ?, ?, ?, ?, ?, ?);", wf_list)

# Compatibility Table: items & purchase_requests (for existing agents/PR flows)
conn.execute("""
    CREATE OR REPLACE TABLE items AS
    SELECT 
        i.item_id,
        i.item_name AS name,
        i.category,
        COALESCE(SUM(sb.quantity_on_hand), i.min_stock * 2) AS current_stock,
        CASE WHEN COUNT(sb.warehouse_id) > 0 THEN CAST(SUM(sb.reorder_point) AS BIGINT) ELSE i.min_stock END AS min_threshold,
        CASE WHEN COUNT(sb.warehouse_id) > 0 THEN CAST(SUM(sb.reorder_point * 3) AS BIGINT) ELSE i.min_stock * 3 END AS max_threshold,
        15.0 AS avg_daily_usage,
        i.lead_time_days,
        i.unit,
        'ALL' AS tenant_id,
        i.unit_price
    FROM inventory_items i
    LEFT JOIN stock_balances sb ON i.item_id = sb.item_id
    GROUP BY i.item_id, i.item_name, i.category, i.min_stock, i.lead_time_days, i.unit, i.unit_price;
""")

# Compatibility Tables & Operational DDL: orders & purchase_requests
conn.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id VARCHAR PRIMARY KEY,
        pr_number VARCHAR NOT NULL,
        item_id VARCHAR NOT NULL,
        vendor_id VARCHAR NOT NULL,
        quantity BIGINT NOT NULL,
        unit_price DOUBLE NOT NULL,
        total_price DOUBLE NOT NULL,
        status VARCHAR NOT NULL,
        tenant_id VARCHAR NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
""")

conn.execute("""
    CREATE TABLE IF NOT EXISTS purchase_requests (
        pr_number VARCHAR PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status VARCHAR DEFAULT 'PENDING',
        total_amount BIGINT,
        items_json TEXT,
        tenant_id VARCHAR DEFAULT 'INVENTORY'
    );
""")

# Permanently drop truly legacy/unused tables
conn.execute("DROP TABLE IF EXISTS attendances;")
conn.execute("DROP TABLE IF EXISTS vendors;")

if EMPTY_PR_PO:
    conn.execute("DELETE FROM purchase_orders;")
    conn.execute("DELETE FROM orders;")
    conn.execute("DELETE FROM purchase_requests;")

conn.close()

print(">>> [6/7] Seluruh Tabel Berhasil Dimuat ke DuckDB!")
print(f">>> [7/7] Selesai! Semua CSV tersimpan rapi di {DATA_DIR} dan DuckDB di {DB_PATH}")
