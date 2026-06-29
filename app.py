import os
import re
import json
import time
import anthropic
import streamlit as st
import gspread
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound
from dotenv import load_dotenv

load_dotenv()

SPREADSHEET_ID = "1wmEzZyxmhuvqDZXYBaP0j44c-lb1PLncO_ZtoB5sQxk"
SHEET_BUDGET   = "Budget Tracking"
SHEET_PROJECTS = "Daftar Proyek"
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")

st.set_page_config(
    page_title="Paragon Production Dashboard",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# GLOBAL CSS  –  StudioBinder-inspired aesthetic
# ============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"], .stMarkdown, .stText, p, div, span, label {
    font-family: 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif !important;
}

/* App background */
.stApp { background-color: #F7F8FA; }

/* Remove default Streamlit chrome */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }

/* Main content area */
.block-container {
    padding-top: 2.5rem !important;
    padding-bottom: 3rem !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] > div:first-child {
    background-color: #1A202C;
    border-right: none;
}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] div {
    color: #CBD5E0 !important;
}
section[data-testid="stSidebar"] hr {
    border-color: #2D3748 !important;
    margin: 12px 0 !important;
}
section[data-testid="stSidebar"] button {
    background-color: #2D3748 !important;
    color: #E2E8F0 !important;
    border: 1px solid #4A5568 !important;
    border-radius: 6px !important;
}
section[data-testid="stSidebar"] button:hover {
    background-color: #4A5568 !important;
    border-color: #718096 !important;
}

/* ── Streamlit metric cards ── */
[data-testid="metric-container"] {
    background: transparent;
}

/* ── Selectbox ── */
.stSelectbox > div > div {
    background: #FFFFFF !important;
    border-color: #E2E8F0 !important;
    border-radius: 6px !important;
    font-size: 14px !important;
}

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    background: #FFFFFF;
    border-radius: 8px;
    border: 2px dashed #E2E8F0;
    padding: 8px;
}

/* ── Override st.error / st.warning default loud colors with softer tones ── */
div[data-testid="stNotification"] {
    border-radius: 8px !important;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# GOOGLE SHEETS  –  koneksi & data fetching
# ============================================================

@st.cache_resource
def _get_gspread_client():
    import base64
    if os.path.exists(CREDENTIALS_FILE):
        return gspread.service_account(filename=CREDENTIALS_FILE)
    try:
        # Metode utama: credentials.json di-encode base64, bebas dari masalah TOML/copy-paste
        if "GOOGLE_CREDENTIALS_B64" in st.secrets:
            raw = base64.b64decode(st.secrets["GOOGLE_CREDENTIALS_B64"]).decode("utf-8")
            creds_dict = json.loads(raw)
            return gspread.service_account_from_dict(creds_dict)
        # Fallback: format lama g_credentials (tidak disarankan)
        creds_dict = dict(st.secrets["g_credentials"])
        return gspread.service_account_from_dict(creds_dict)
    except KeyError:
        raise RuntimeError(
            "Google credentials tidak ditemukan.\n"
            "Lokal: pastikan file 'credentials.json' ada di folder yang sama dengan app.py.\n"
            "Cloud: tambahkan [g_credentials] di Streamlit Secrets."
        )


@st.cache_data(ttl=600)
def fetch_budget_data() -> list[dict]:
    client = _get_gspread_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    return sh.worksheet(SHEET_BUDGET).get_all_records()


@st.cache_data(ttl=600)
def fetch_project_data() -> list[dict]:
    client = _get_gspread_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    return sh.worksheet(SHEET_PROJECTS).get_all_records()


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def _fmt_rp(value) -> str:
    try:
        return f"Rp {int(float(str(value).replace(',', '').replace('.', '') or 0)):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"


def _to_int(value) -> int:
    try:
        return int(float(str(value).replace(',', '').replace('.', '') or 0))
    except (ValueError, TypeError):
        return 0


# ============================================================
# HTML COMPONENT BUILDERS
# ============================================================

def _badge(label: str, color: str = "gray") -> str:
    palettes = {
        "green":  ("#276749", "#F0FFF4", "#C6F6D5"),
        "yellow": ("#7B6000", "#FEFCBF", "#FAF089"),
        "red":    ("#C53030", "#FFF5F5", "#FEB2B2"),
        "blue":   ("#2B6CB0", "#EBF8FF", "#BEE3F8"),
        "purple": ("#553C9A", "#FAF5FF", "#E9D8FD"),
        "gray":   ("#4A5568", "#EDF2F7", "#E2E8F0"),
        "orange": ("#9C4221", "#FFFAF0", "#FBD38D"),
    }
    tc, bg, bd = palettes.get(color, palettes["gray"])
    return (
        f'<span style="display:inline-block;padding:3px 11px;border-radius:20px;'
        f'font-size:11px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;'
        f'color:{tc};background:{bg};border:1px solid {bd};">{label}</span>'
    )


def _status_badge(status: str) -> str:
    s = status.lower()
    if any(x in s for x in ["over", "melebihi", "exceed"]):
        return _badge("Over-Budget", "red")
    if any(x in s for x in ["selesai", "released", "done", "complete"]):
        return _badge("Selesai", "purple")
    if any(x in s for x in ["terlambat", "delay", "mundur"]):
        return _badge("Terlambat", "orange")
    if any(x in s for x in ["post", "editing", "grading", "mixing", "vfx"]):
        return _badge("Post-Production", "blue")
    if any(x in s for x in ["shooting", "production", "syuting", "produksi"]):
        return _badge("Production", "green")
    if any(x in s for x in ["pre", "development", "pra", "prep"]):
        return _badge("Pre-Production", "yellow")
    return _badge("On-Going", "gray")


def _redflag_banner(msg: str) -> str:
    return (
        '<div style="background:#FFF5F5;border-left:4px solid #FC8181;'
        'border-radius:0 8px 8px 0;padding:14px 20px;margin-bottom:10px;">'
        f'<span style="color:#C53030;font-size:14px;font-weight:500;">{msg}</span>'
        '</div>'
    )


def _hero_metric(label: str, value: str, sub: str = "", accent: str = "#1A202C") -> str:
    sub_html = (
        f'<div style="font-size:12px;color:#A0AEC0;margin-top:5px;">{sub}</div>'
        if sub else ""
    )
    return (
        '<div style="background:#FFFFFF;border-radius:8px;'
        'box-shadow:0 4px 12px rgba(0,0,0,0.03);'
        f'padding:28px 20px;text-align:center;border-top:3px solid {accent};">'
        '<div style="font-size:10px;font-weight:700;letter-spacing:1.8px;'
        f'text-transform:uppercase;color:#A0AEC0;margin-bottom:10px;">{label}</div>'
        f'<div style="font-size:24px;font-weight:800;color:#1A202C;letter-spacing:-0.5px;">{value}</div>'
        f'{sub_html}'
        '</div>'
    )


def _project_card(row: dict) -> str:
    judul      = row.get("Judul Film", "(tanpa judul)")
    budget     = _to_int(row.get("Total Budget", 0))
    spent      = _to_int(row.get("Actual Spent", 0))
    director   = str(row.get("Director", row.get("Sutradara", ""))).strip()
    partner    = str(row.get("Production Partner", "")).strip()
    pct        = round(spent / budget * 100, 1) if budget > 0 else 0
    over       = spent > budget

    # Status Update — coba beberapa nama kolom
    status = str(
        row.get("Status Update Project") or
        row.get("Status Update") or
        row.get("Status") or ""
    ).strip()

    # Next Steps — kolom opsional
    next_steps = str(
        row.get("Next Steps") or
        row.get("To Do") or
        row.get("To Do Next") or
        row.get("Action Items") or
        row.get("Next Action") or ""
    ).strip()

    border_color = "#FC8181" if over else ("#ECC94B" if pct >= 80 else "#68D391")
    spent_color  = "#C53030" if over else "#2D3748"
    badge_html   = _status_badge(status) if status else _badge("On-Going", "gray")

    meta_parts = []
    if director:
        meta_parts.append(f"Sutradara: {director}")
    if partner:
        meta_parts.append(f"Partner: {partner}")
    dir_html = (
        f'<div style="font-size:13px;color:#718096;margin-top:3px;">'
        + " &nbsp;·&nbsp; ".join(meta_parts)
        + "</div>"
    ) if meta_parts else ""

    # Seksi Latest Update
    update_html = ""
    if status:
        update_html = (
            '<div style="margin-top:14px;padding-top:14px;border-top:1px solid #F7FAFC;">'
            '<div style="font-size:10px;font-weight:600;letter-spacing:1px;text-transform:uppercase;'
            'color:#A0AEC0;margin-bottom:6px;">📋 Latest Update</div>'
            f'<div style="font-size:13px;color:#4A5568;line-height:1.6;">{status}</div>'
            '</div>'
        )

    # Seksi Next Steps (hanya tampil jika kolom ada dan berisi data)
    next_html = ""
    if next_steps and next_steps.lower() not in ("belum diketahui", "-", ""):
        # Render sebagai bullet list jika teks mengandung newline atau "- "
        if "\n" in next_steps or next_steps.startswith("- "):
            items = [l.lstrip("- ").strip() for l in next_steps.splitlines() if l.strip()]
            bullets = "".join(
                f'<li style="margin-bottom:4px;">{item}</li>' for item in items
            )
            next_content = f'<ul style="margin:0;padding-left:18px;">{bullets}</ul>'
        else:
            next_content = f'<div style="font-size:13px;color:#4A5568;line-height:1.6;">{next_steps}</div>'

        next_html = (
            '<div style="margin-top:12px;padding-top:12px;border-top:1px solid #F7FAFC;">'
            '<div style="font-size:10px;font-weight:600;letter-spacing:1px;text-transform:uppercase;'
            'color:#A0AEC0;margin-bottom:6px;">✅ To Do Next</div>'
            f'{next_content}'
            '</div>'
        )

    return (
        '<div style="background:#FFFFFF;border-radius:8px;'
        'box-shadow:0 4px 12px rgba(0,0,0,0.03);'
        f'padding:20px 24px;margin-bottom:12px;border-left:4px solid {border_color};">'

        # Header: judul + badge
        '<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
        '<div>'
        f'<div style="font-size:17px;font-weight:700;color:#1A202C;">{judul}</div>'
        f'{dir_html}'
        '</div>'
        f'<div style="flex-shrink:0;margin-left:12px;">{badge_html}</div>'
        '</div>'

        # Budget row
        '<div style="display:flex;gap:32px;margin-top:14px;padding-top:14px;'
        'border-top:1px solid #F7FAFC;">'
        '<div>'
        '<div style="font-size:10px;font-weight:600;letter-spacing:1px;'
        'text-transform:uppercase;color:#A0AEC0;">Budget</div>'
        f'<div style="font-size:14px;font-weight:600;color:#2D3748;margin-top:2px;">{_fmt_rp(budget)}</div>'
        '</div>'
        '<div>'
        '<div style="font-size:10px;font-weight:600;letter-spacing:1px;'
        'text-transform:uppercase;color:#A0AEC0;">Terpakai</div>'
        f'<div style="font-size:14px;font-weight:600;color:{spent_color};margin-top:2px;">'
        f'{_fmt_rp(spent)} <span style="font-size:12px;font-weight:400;color:#A0AEC0;">({pct}%)</span>'
        '</div>'
        '</div>'
        '</div>'

        # Update & Next Steps
        f'{update_html}'
        f'{next_html}'

        '</div>'
    )


def _info_card(title: str, items: list) -> str:
    rows_html = "".join(
        '<div style="margin-bottom:18px;">'
        f'<div style="font-size:10px;font-weight:700;letter-spacing:1.5px;'
        f'text-transform:uppercase;color:#A0AEC0;margin-bottom:4px;">{lbl}</div>'
        f'<div style="font-size:15px;color:#2D3748;font-weight:500;line-height:1.65;">{val}</div>'
        '</div>'
        for lbl, val in items if val and str(val).strip()
    )
    return (
        '<div style="background:#FFFFFF;border-radius:8px;'
        'box-shadow:0 4px 12px rgba(0,0,0,0.03);padding:24px;margin-bottom:16px;">'
        '<div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;'
        'color:#A0AEC0;padding-bottom:14px;margin-bottom:18px;border-bottom:1px solid #EDF2F7;">'
        f'{title}</div>'
        f'{rows_html}'
        '</div>'
    )


def _drive_button(url: str) -> str:
    return (
        f'<a href="{url}" target="_blank" style="'
        'display:block;background:#1A202C;color:#FFFFFF !important;'
        'text-align:center;padding:14px 20px;border-radius:6px;'
        'font-size:14px;font-weight:600;text-decoration:none;'
        'letter-spacing:0.3px;">'
        '📁 &nbsp; Buka Folder Google Drive'
        '</a>'
    )


def _page_header(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div style="margin-bottom:28px;">'
        f'<div style="font-size:28px;font-weight:800;color:#1A202C;letter-spacing:-0.5px;">{title}</div>'
        f'<div style="font-size:14px;color:#718096;margin-top:4px;">{subtitle}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _section_label(text: str) -> None:
    st.markdown(
        f'<div style="font-size:11px;font-weight:700;letter-spacing:2px;'
        f'text-transform:uppercase;color:#A0AEC0;margin:20px 0 14px 0;">{text}</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown(
        '<div style="padding:8px 0 20px 0;">'
        '<div style="font-size:10px;font-weight:700;letter-spacing:2px;'
        'text-transform:uppercase;color:#4A5568;margin-bottom:6px;">PRODUCTION STUDIO</div>'
        '<div style="font-size:22px;font-weight:800;color:#FFFFFF;letter-spacing:-0.5px;">Paragon Pictures</div>'
        '<div style="font-size:13px;color:#718096;margin-top:2px;">Internal Dashboard</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    selected_tab = st.radio(
        "Navigasi",
        options=["Dashboard Utama", "Project Tracking", "AI Automation Center"],
        index=0,
        label_visibility="collapsed",
    )
    st.markdown("---")
    if st.button("🔄 Refresh Data", use_container_width=True,
                 help="Paksa ambil ulang data dari Google Sheets"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Cache otomatis diperbarui tiap 10 menit.")
    st.markdown("---")
    st.caption("Fase 3 · Internal Use Only")


# ============================================================
# TAB 1 – DASHBOARD UTAMA
# ============================================================
def render_dashboard():
    _page_header(
        "Dashboard Utama",
        "Overview portofolio produksi & alert budget real-time dari Google Sheets.",
    )

    try:
        rows = fetch_budget_data()
    except Exception as e:
        st.error("🚨 CRITICAL ERROR: Aplikasi Gagal Memuat Data 🚨")
        st.exception(e)
        st.stop()

    if not rows:
        st.warning("Tab 'Budget Tracking' tidak memiliki data.")
        return

    # Merge dengan Daftar Proyek untuk mendapatkan Status Update & Next Steps
    try:
        proj_rows = fetch_project_data()
        proj_lookup = {
            str(r.get("Judul Film", "")).strip().lower(): r
            for r in proj_rows
        }
    except Exception:
        proj_lookup = {}

    # Gabungkan field dari Daftar Proyek ke dalam setiap budget row
    merged_rows = []
    for r in rows:
        judul_key = str(r.get("Judul Film", "")).strip().lower()
        proj_data = proj_lookup.get(judul_key, {})
        merged_rows.append({**proj_data, **r})  # budget fields override jika ada duplikat
    rows = merged_rows

    # ── Red Flag Alerts ──────────────────────────────────────────────────────
    _RF_KEYWORDS = ["kritis", "red flag", "sengketa", "terancam", "over-budget"]
    red_flags = []
    for row in rows:
        budget = _to_int(row.get("Total Budget", 0))
        spent  = _to_int(row.get("Actual Spent", 0))
        judul  = row.get("Judul Film", "(tanpa judul)")
        if spent > budget:
            selisih = _fmt_rp(spent - budget)
            red_flags.append(
                f"⚠️ OVER-BUDGET: Proyek <strong>{judul}</strong> melebihi anggaran! "
                f"&nbsp;·&nbsp; Selisih: <strong>{selisih}</strong>"
            )
        else:
            status_text = str(
                row.get("Status Update Project") or
                row.get("Status Update") or
                row.get("Status") or ""
            ).lower()
            for kw in _RF_KEYWORDS:
                if kw in status_text:
                    red_flags.append(
                        f"🚩 ALERT: Proyek <strong>{judul}</strong> — status mengandung kata kunci: "
                        f"<em>\"{kw.title()}\"</em>"
                    )
                    break

    if red_flags:
        _section_label("🚨 RED FLAG ALERTS")
        st.markdown(
            "".join(_redflag_banner(m) for m in red_flags),
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

    # ── Hero Metrics ─────────────────────────────────────────────────────────
    total_proyek = len(rows)
    total_budget = sum(_to_int(r.get("Total Budget", 0)) for r in rows)
    total_spent  = sum(_to_int(r.get("Actual Spent", 0)) for r in rows)
    pct_terpakai = round(total_spent / total_budget * 100, 1) if total_budget > 0 else 0

    _section_label("KEY METRICS")
    c1, c2, c3 = st.columns(3, gap="medium")
    c1.markdown(
        _hero_metric("Total Proyek Aktif", str(total_proyek), "Dari Google Sheets", "#4A5568"),
        unsafe_allow_html=True,
    )
    c2.markdown(
        _hero_metric("Total Budget", _fmt_rp(total_budget), "Seluruh portofolio", "#1A202C"),
        unsafe_allow_html=True,
    )
    c3.markdown(
        _hero_metric(
            "Total Pengeluaran",
            _fmt_rp(total_spent),
            f"{pct_terpakai}% dari total budget",
            "#E53E3E" if pct_terpakai > 90 else "#2B6CB0",
        ),
        unsafe_allow_html=True,
    )

    # ── Project Grid ─────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    _section_label("PROYEK AKTIF")
    st.markdown(
        "".join(_project_card(r) for r in rows),
        unsafe_allow_html=True,
    )


# ============================================================
# TAB 2 – PROJECT TRACKING
# ============================================================
def render_project_tracking():
    _page_header(
        "Project Tracking",
        "Detail lengkap setiap proyek dari Google Sheets.",
    )

    try:
        rows = fetch_project_data()
    except Exception as e:
        st.error("🚨 CRITICAL ERROR: Aplikasi Gagal Memuat Data 🚨")
        st.exception(e)
        st.stop()

    if not rows:
        st.warning("Tab 'Daftar Proyek' tidak memiliki data.")
        return

    film_titles = [r.get("Judul Film", "") for r in rows if r.get("Judul Film")]

    selected = st.selectbox(
        "Pilih Film",
        options=["— Pilih Film —"] + film_titles,
        index=0,
        label_visibility="collapsed",
    )

    if selected == "— Pilih Film —":
        st.markdown(
            f'<div style="color:#718096;padding:16px 0;">'
            f'{len(film_titles)} proyek tersedia · Pilih dari dropdown di atas untuk melihat detail.</div>',
            unsafe_allow_html=True,
        )
        return

    film = next((r for r in rows if r.get("Judul Film") == selected), None)
    if film is None:
        st.error("Data film tidak ditemukan.")
        return

    judul     = str(film.get("Judul Film", "-"))
    partner   = str(film.get("Production Partner", "-"))
    status    = str(
        film.get("Status Update Project") or
        film.get("Status Update") or
        film.get("Status") or ""
    ).strip()
    director  = str(film.get("Director", film.get("Sutradara", "-"))).strip()
    producer  = str(film.get("Producer", film.get("Produser", "-"))).strip()
    synopsis  = str(film.get("Short Synopsis", film.get("Synopsis", film.get("Sinopsis", "-")))).strip()
    cast      = str(film.get("Cast", "-")).strip()
    drive_url = str(film.get("Link Google Drive", film.get("Link Drive", film.get("Drive", "")))).strip()

    # Film header
    st.markdown(
        '<div style="padding:28px 0 20px 0;border-bottom:2px solid #EDF2F7;margin-bottom:28px;">'
        '<div style="font-size:10px;font-weight:700;letter-spacing:2px;'
        'text-transform:uppercase;color:#A0AEC0;margin-bottom:10px;">NOW VIEWING</div>'
        '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:16px;">'
        f'<div style="font-size:2.2rem;font-weight:800;color:#1A202C;'
        f'letter-spacing:-1px;line-height:1.15;max-width:80%;">{judul}</div>'
        f'<div style="flex-shrink:0;padding-top:8px;">{_status_badge(status)}</div>'
        '</div>'
        f'<div style="font-size:14px;color:#718096;margin-top:10px;">'
        f'Production Partner: <strong style="color:#2D3748;">{partner}</strong></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    col_left, col_right = st.columns([3, 2], gap="large")

    with col_left:
        _section_label("PRODUCTION PROFILE")
        st.markdown(
            _info_card("", [
                ("Production Partner", partner),
                ("Produser", producer),
                ("Sutradara", director),
            ]),
            unsafe_allow_html=True,
        )
        # Status update styled box
        status_display = status if status and status.lower() not in ("-", "belum diketahui") \
            else "Belum ada update terkini."
        st.markdown(
            '<div style="background:#FFFFFF;border-radius:8px;'
            'box-shadow:0 4px 12px rgba(0,0,0,0.03);padding:24px;margin-bottom:16px;">'
            '<div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;'
            'color:#A0AEC0;padding-bottom:14px;margin-bottom:18px;border-bottom:1px solid #EDF2F7;">'
            'STATUS UPDATE</div>'
            f'<div style="font-size:14px;color:#2D3748;line-height:1.75;">{status_display}</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    with col_right:
        _section_label("CREATIVE & ASSETS")
        st.markdown(
            _info_card("", [
                ("Sinopsis", synopsis),
                ("Cast", cast),
            ]),
            unsafe_allow_html=True,
        )
        if drive_url and drive_url not in ("-", ""):
            st.markdown(_drive_button(drive_url), unsafe_allow_html=True)
        else:
            st.button("📁 Link Drive belum tersedia", disabled=True, use_container_width=True)


# ============================================================
# AI EXTRACTION & SHEETS SYNC FUNCTIONS
# ============================================================

_EXTRACTION_SYSTEM_PROMPT = """Anda adalah asisten ekstraksi data untuk rumah produksi film Indonesia.
Tugas Anda: baca teks Minutes of Meeting (MoM) rapat produksi, lalu ekstrak informasi setiap film yang dibahas.

PENTING: Kembalikan HANYA sebuah JSON Array (list of objects) — satu objek per judul film.
Jangan gabungkan beberapa judul film menjadi satu objek. Pisahkan secara ketat berdasarkan judul.
Tanpa penjelasan, tanpa markdown, tanpa kode block. Hanya JSON array murni.

Format output wajib (array, meski hanya satu film):
[
  {
    "judul_film": "Judul film pertama yang dibahas",
    "production_partner": "Nama perusahaan atau partner produksi",
    "short_synopsis": "Ringkasan singkat cerita film (1-2 kalimat)",
    "cast": "Nama-nama pemeran, dipisahkan koma",
    "producer": "Nama produser",
    "director": "Nama sutradara",
    "status_update_project": "Rangkuman status atau keputusan utama untuk film ini dari rapat"
  },
  {
    "judul_film": "Judul film kedua (jika ada)",
    ...
  }
]

Aturan wajib:
- Buat SATU objek terpisah untuk SETIAP judul film yang dibahas dalam MoM
- Isi setiap field HANYA dengan informasi yang tersebut di MoM untuk film tersebut
- Jika suatu informasi tidak disebutkan untuk film itu, isi dengan: "Belum Diketahui"
- Jangan mengarang data yang tidak ada di teks MoM
- "status_update_project" harus spesifik per film, bukan rangkuman seluruh rapat"""


def _read_uploaded_file(uploaded_file) -> str:
    """Ekstrak teks dari file .txt, .pdf, atau .docx."""
    name = uploaded_file.name.lower()

    if name.endswith(".txt"):
        return uploaded_file.read().decode("utf-8", errors="ignore")

    if name.endswith(".pdf"):
        import pypdf
        reader = pypdf.PdfReader(uploaded_file)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if name.endswith(".docx"):
        import docx
        doc = docx.Document(uploaded_file)
        return "\n".join(p.text for p in doc.paragraphs)

    raise ValueError(f"Format file tidak didukung: {uploaded_file.name}")


def _get_anthropic_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
    return key


def _extract_mom_with_ai(mom_text: str) -> list[dict]:
    """Kirim teks MoM ke Claude, kembalikan list of dict (satu dict per film)."""
    api_key = _get_anthropic_api_key()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY belum dikonfigurasi di .env maupun Streamlit Secrets")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=_EXTRACTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": mom_text}],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code block jika Claude tetap menyertakannya
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    json_str = match.group(1) if match else raw

    parsed = json.loads(json_str)

    # Normalisasi: jika Claude mengembalikan objek tunggal, bungkus jadi list
    if isinstance(parsed, dict):
        parsed = [parsed]

    return parsed


def _sync_to_sheets(data: dict) -> tuple[str, str]:
    """
    Sinkronisasi data hasil ekstraksi AI ke Google Sheets.
    Return: (action, pesan_sukses)  —  action = 'added' | 'updated'
    """
    gs_client = _get_gspread_client()
    sh        = gs_client.open_by_key(SPREADSHEET_ID)
    ws_proj   = sh.worksheet(SHEET_PROJECTS)
    ws_budget = sh.worksheet(SHEET_BUDGET)
    judul     = str(data.get("judul_film", "")).strip()

    # Baca semua data proyek yang sudah ada
    all_proj = ws_proj.get_all_records()
    proj_headers = ws_proj.row_values(1)

    # Periksa apakah film sudah ada (case-insensitive)
    existing_row_idx = None
    for idx, row in enumerate(all_proj):
        if str(row.get("Judul Film", "")).strip().lower() == judul.lower():
            existing_row_idx = idx + 2  # gspread 1-indexed, baris 1 = header
            break

    # Mapping nilai AI → nama kolom yang mungkin dipakai di Sheet
    field_map = {
        "ID Proyek":             "",
        "Judul Film":            data.get("judul_film", ""),
        "Production Partner":    data.get("production_partner", ""),
        "Synopsis":              data.get("short_synopsis", ""),
        "Sinopsis":              data.get("short_synopsis", ""),
        "Short Synopsis":        data.get("short_synopsis", ""),
        "Cast":                  data.get("cast", ""),
        "Producer":              data.get("producer", ""),
        "Produser":              data.get("producer", ""),
        "Director":              data.get("director", ""),
        "Sutradara":             data.get("director", ""),
        "Status Update":         data.get("status_update_project", ""),
        "Status Update Project": data.get("status_update_project", ""),
        "Link Drive":            "",
        "Link Google Drive":     "",
    }

    _UNKNOWN = "belum diketahui"

    if existing_row_idx is None:
        # ── PROYEK BARU: append baris penuh ke Daftar Proyek ─────────────
        new_proj_row = [field_map.get(h, "") for h in proj_headers]
        ws_proj.append_row(new_proj_row, value_input_option="USER_ENTERED")

        # Tambah baris di Budget Tracking dengan nominal 0
        budget_headers = ws_budget.row_values(1)
        budget_map = {"Judul Film": judul, "Total Budget": 0, "Actual Spent": 0}
        new_budget_row = [budget_map.get(h, 0) for h in budget_headers]
        ws_budget.append_row(new_budget_row, value_input_option="USER_ENTERED")

        return "added", f"Proyek baru <strong>{judul}</strong> berhasil ditambahkan ke Google Sheets."

    else:
        # ── PROYEK LAMA: hanya update Status Update; jangan timpa data lama ──
        # Ambil baris lama agar bisa bandingkan sebelum menulis
        existing_record = all_proj[existing_row_idx - 2]

        # Kolom yang BOLEH diperbarui dari MoM baru (tidak merusak data master)
        updatable_status_headers = {"status update", "status update project", "status"}

        # Kolom inti yang TIDAK boleh ditimpa jika AI menghasilkan "Belum Diketahui"
        preserve_headers = {
            "short synopsis", "synopsis", "sinopsis",
            "cast", "producer", "produser",
            "director", "sutradara",
            "production partner",
        }

        updates = {}  # col_idx (1-based) → new_value

        for i, h in enumerate(proj_headers):
            h_lower = h.strip().lower()
            new_val  = field_map.get(h, "")

            if h_lower in updatable_status_headers:
                # Selalu update status jika AI memberikan nilai bukan kosong
                if new_val and new_val.strip().lower() != _UNKNOWN:
                    updates[i + 1] = new_val

            elif h_lower in preserve_headers:
                # Hanya update jika AI punya nilai nyata DAN kolom lama kosong
                old_val = str(existing_record.get(h, "")).strip()
                if (not old_val or old_val.lower() == _UNKNOWN) \
                        and new_val and new_val.strip().lower() != _UNKNOWN:
                    updates[i + 1] = new_val

        if updates:
            for col_idx, val in updates.items():
                ws_proj.update_cell(existing_row_idx, col_idx, val)
            return "updated", f"Status proyek <strong>{judul}</strong> berhasil diperbarui di Google Sheets."
        else:
            return "skipped", f"Proyek <strong>{judul}</strong> ditemukan — tidak ada data baru untuk diperbarui."


# ============================================================
# TAB 3 – AI AUTOMATION CENTER
# ============================================================
def render_ai_center():
    _page_header(
        "AI Automation Center",
        "Tempel atau upload teks MoM rapat — AI akan mengekstrak data dan menyinkronkannya ke Google Sheets.",
    )

    api_key = _get_anthropic_api_key()
    if not api_key:
        st.warning(
            "**ANTHROPIC_API_KEY belum dikonfigurasi.**  \n"
            "Lokal: tambahkan `ANTHROPIC_API_KEY=sk-ant-...` di file `.env`.  \n"
            "Cloud: tambahkan key tersebut di Streamlit Secrets."
        )

    col_input, col_result = st.columns([1, 1], gap="large")

    with col_input:
        _section_label("📋 INPUT MOM")

        uploaded_file = st.file_uploader(
            "Upload file MoM (.txt, .pdf, .docx)",
            type=["txt", "pdf", "docx"],
            label_visibility="collapsed",
        )

        if uploaded_file:
            try:
                mom_text = _read_uploaded_file(uploaded_file)
                st.success(f"✅ File dimuat: **{uploaded_file.name}**")
                with st.expander("👁️ Preview Isi File"):
                    st.text(mom_text[:600] + ("..." if len(mom_text) > 600 else ""))
            except Exception as e:
                st.error(f"❌ Gagal membaca file: {e}")
                mom_text = ""
        else:
            mom_text = st.text_area(
                "Tempel teks MoM",
                height=320,
                placeholder=(
                    "Tempel hasil notulen rapat produksi Anda di sini...\n\n"
                    "Contoh:\nRapat Produksi — Film 'Kuasa Gelap'\n"
                    "Tanggal: 28 Juni 2026\nHadir: Gita Fara (Produser), Kimo Stamboel (Sutradara)...\n\n"
                    "Keputusan:\n- Syuting scene 12 dipindah ke Studio 3, 5 Juli 2026\n- ..."
                ),
                label_visibility="collapsed",
            )

        has_input = bool(mom_text and mom_text.strip())

        st.markdown("<br>", unsafe_allow_html=True)
        proses = st.button(
            "🚀 Ekstrak MoM & Sinkronisasi ke Google Sheets",
            type="primary",
            disabled=(not has_input or not api_key),
            use_container_width=True,
        )
        if not api_key:
            st.caption("⚠️ Atur ANTHROPIC_API_KEY di .env untuk mengaktifkan tombol ini.")
        elif not has_input:
            st.caption("Upload file atau tempel teks MoM terlebih dahulu.")

    # Session state — sekarang mom_extracted adalah list[dict]
    if "mom_extracted" not in st.session_state:
        st.session_state.mom_extracted  = None   # list[dict] | None
        st.session_state.mom_sync_results = None  # list[tuple[str,str]] | None

    if proses and has_input and api_key:
        with col_result:
            with st.spinner("Claude sedang membaca MoM dan mengekstrak data semua proyek..."):
                try:
                    st.session_state.mom_extracted = _extract_mom_with_ai(mom_text)
                    st.session_state.mom_sync_results = None
                except json.JSONDecodeError as e:
                    st.error(f"❌ Gagal mem-parsing JSON dari Claude: {e}")
                    st.session_state.mom_extracted = None
                except Exception as e:
                    st.error("❌ Error saat memanggil Anthropic API")
                    st.exception(e)
                    st.session_state.mom_extracted = None

            if st.session_state.mom_extracted:
                n = len(st.session_state.mom_extracted)
                with st.spinner(f"Menyinkronisasi {n} proyek ke Google Sheets..."):
                    sync_results = []
                    sync_error   = False
                    try:
                        for project_data in st.session_state.mom_extracted:
                            action, msg = _sync_to_sheets(project_data)
                            sync_results.append((action, msg))
                        st.session_state.mom_sync_results = sync_results
                        st.cache_data.clear()
                    except Exception as e:
                        st.error("❌ Error saat menyinkronisasi ke Google Sheets")
                        st.exception(e)
                        sync_error = True

    with col_result:
        _section_label("📊 HASIL EKSTRAKSI AI")

        if st.session_state.mom_extracted:
            projects = st.session_state.mom_extracted
            results  = st.session_state.mom_sync_results or []

            # Ringkasan jumlah proyek
            n_added   = sum(1 for a, _ in results if a == "added")
            n_updated = sum(1 for a, _ in results if a == "updated")
            n_skipped = sum(1 for a, _ in results if a == "skipped")

            summary_parts = []
            if n_added:   summary_parts.append(f"{n_added} proyek baru ditambahkan")
            if n_updated: summary_parts.append(f"{n_updated} proyek diperbarui")
            if n_skipped: summary_parts.append(f"{n_skipped} proyek tidak ada perubahan")

            if summary_parts:
                st.markdown(
                    '<div style="background:#F0FFF4;border-left:4px solid #68D391;'
                    'border-radius:0 8px 8px 0;padding:14px 18px;margin-bottom:20px;">'
                    f'<span style="color:#276749;font-size:14px;font-weight:600;">'
                    f'✅ Sinkronisasi selesai — {" · ".join(summary_parts)}</span></div>',
                    unsafe_allow_html=True,
                )

            # Kartu per proyek
            for i, data in enumerate(projects):
                action, msg = results[i] if i < len(results) else ("pending", "")

                if action == "added":
                    badge = _badge("Proyek Baru", "green")
                elif action == "updated":
                    badge = _badge("Status Diperbarui", "blue")
                elif action == "skipped":
                    badge = _badge("Tidak Ada Perubahan", "gray")
                else:
                    badge = _badge("Belum Disinkronkan", "yellow")

                st.markdown(
                    f'<div style="margin-bottom:6px;">{badge}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    _info_card(
                        f"#{i+1} — {data.get('judul_film', '-')}",
                        [
                            ("Production Partner", data.get("production_partner", "-")),
                            ("Sutradara",          data.get("director", "-")),
                            ("Produser",           data.get("producer", "-")),
                            ("Cast",               data.get("cast", "-")),
                            ("Sinopsis",           data.get("short_synopsis", "-")),
                            ("Status Update",      data.get("status_update_project", "-")),
                        ],
                    ),
                    unsafe_allow_html=True,
                )

            if st.button("🔁 Proses MoM Baru", use_container_width=True):
                st.session_state.mom_extracted    = None
                st.session_state.mom_sync_results = None
                st.rerun()

        else:
            st.markdown(
                '<div style="color:#A0AEC0;padding:32px 0;text-align:center;">'
                '<div style="font-size:32px;margin-bottom:12px;">🤖</div>'
                '<div style="font-size:14px;">Hasil ekstraksi AI akan muncul di sini<br>'
                'setelah MoM diproses.</div>'
                '</div>',
                unsafe_allow_html=True,
            )


# ============================================================
# ROUTER
# ============================================================
if selected_tab == "Dashboard Utama":
    render_dashboard()
elif selected_tab == "Project Tracking":
    render_project_tracking()
elif selected_tab == "AI Automation Center":
    render_ai_center()
