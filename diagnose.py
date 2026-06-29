import json
import gspread

SPREADSHEET_ID = "1wmEzZyxmhuvqDZXYBaP0j44c-lb1PLncO_ZtoB5sQxk"
CREDENTIALS_FILE = "credentials.json"

print("=== Paragon GSheets Diagnostic ===\n")

with open(CREDENTIALS_FILE) as f:
    creds = json.load(f)
print(f"[OK] credentials.json terbaca")
print(f"     client_email : {creds.get('client_email')}")
print(f"     project_id   : {creds.get('project_id')}\n")

try:
    client = gspread.service_account(filename=CREDENTIALS_FILE)
    print("[OK] gspread client berhasil dibuat\n")
except Exception as e:
    print(f"[FAIL] Gagal buat client: {e}")
    raise

try:
    sh = client.open_by_key(SPREADSHEET_ID)
    print(f"[OK] Spreadsheet ditemukan: '{sh.title}'\n")
except Exception as e:
    print(f"[FAIL] open_by_key gagal")
    print(f"       Type    : {type(e).__name__}")
    print(f"       Message : {e}")
    cause = getattr(e, '__cause__', None)
    if cause:
        print(f"       Cause   : {type(cause).__name__}: {cause}")
        response = getattr(cause, 'response', None)
        if response is not None:
            print(f"       HTTP    : {response.status_code}")
            print(f"       Body    : {response.text[:500]}")
    raise

try:
    ws = sh.worksheet("Budget Tracking")
    rows = ws.get_all_records()
    print(f"[OK] Tab 'Budget Tracking' terbaca — {len(rows)} baris\n")
except Exception as e:
    print(f"[FAIL] Baca worksheet gagal: {type(e).__name__}: {e}")
    raise

try:
    ws2 = sh.worksheet("Daftar Proyek")
    rows2 = ws2.get_all_records()
    print(f"[OK] Tab 'Daftar Proyek' terbaca — {len(rows2)} baris\n")
except Exception as e:
    print(f"[FAIL] Baca worksheet gagal: {type(e).__name__}: {e}")
    raise

print("=== Semua koneksi berhasil! ===")
