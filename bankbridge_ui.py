"""
Next - user interface.

All statement parsing and QBO/CSV generation lives in engine.py, which is
built automatically from your app.py. This file only draws the screen.

WHEN YOU ADD A NEW BANK TO app.py:
  1. add the combination and extractor to DEDICATED_EXTRACTORS in app.py
  2. if it has its own QBO generator, add it in make_qbo() in app.py
"""
import html
import os
import re
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

import engine as eng

APP_VERSION = "1.0"


def installed_build_id():
    entry = Path(sys.executable) if getattr(sys, "frozen", False) else Path(__file__)
    try:
        marker = entry.with_name("BankBridgeNext.build").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    return marker[:7] if re.fullmatch(r"[0-9a-f]{40}", marker) else None

# ---------------------------------------------------------------------------
# Which extract_... function handles each (bank, account type)
# ---------------------------------------------------------------------------
def get_extractor(bank, account_type, *, use_ocr=False, use_fallback=False):
    dedicated = eng.get_dedicated_extractor(bank, account_type)
    if dedicated and not use_fallback:
        return dedicated
    if account_type in eng.UNIVERSAL_DEPOSIT_TYPES or account_type in eng.CREDIT_CARD_SELECTIONS:
        return lambda data: eng.extract_universal_transactions(data, bank, account_type, use_ocr=use_ocr)
    return None


# ---------------------------------------------------------------------------
# Reconciliation (same rules as the original app)
# ---------------------------------------------------------------------------
def reconcile(df, info):
    debit_total = round(float(df["Debit"].sum()), 2)
    credit_total = round(float(df["Credit"].sum()), 2)
    debit_count = int((df["Debit"] > 0).sum())
    credit_count = int((df["Credit"] > 0).sum())
    rows, ok = eng.reconcile_statement(df, info)
    details = []
    if not info.get("universal") and info["statement_type"] == "credit_card":
        s = info.get("summary", {})
        details = [
            ("Previous balance", s.get("previous_balance")),
            ("Purchases & charges (calculated)" if s.get("purchases_derived") else "Purchases & charges",
             s.get("purchases_charges")),
            ("Interest", s.get("interest")),
            ("Fees", s.get("fees")),
            ("Payments & credits", s.get("payments_credits")),
            ("New balance", s.get("new_balance")),
        ]

    return {
        "ok": ok, "rows": rows, "details": details,
        "debit_total": debit_total, "credit_total": credit_total,
        "debit_count": debit_count, "credit_count": credit_count,
        "count": len(df),
    }


# ---------------------------------------------------------------------------
# Look & feel
# ---------------------------------------------------------------------------
LOGO_SVG = """
<svg width="40" height="40" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs><linearGradient id="bbg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#0E3B66"/><stop offset="1" stop-color="#13A89E"/></linearGradient></defs>
  <rect width="64" height="64" rx="14" fill="url(#bbg)"/>
  <g stroke="#fff" stroke-linecap="round" fill="none">
    <path d="M10 44H54" stroke-width="4"/><path d="M22 18V50M42 18V50" stroke-width="4"/>
    <path d="M10 27L22 19Q32 40 42 19L54 27" stroke-width="3" stroke-linejoin="round"/>
    <path d="M27 25.6V44M32 29.5V44M37 25.6V44" stroke-width="2"/>
  </g>
</svg>
"""

CSS = """
<style>
:root{
  --bb-navy:#0E2A47; --bb-ink:#1B2B3F; --bb-muted:#66768A; --bb-line:#E3E8EF;
  --bb-bg:#F3F6FA; --bb-card:#FFFFFF; --bb-blue:#1F6FB2; --bb-teal:#13A89E;
  --bb-green:#12805C; --bb-green-bg:#E8F6EF; --bb-red:#B42318; --bb-red-bg:#FDECEA;
}
html, body, [class*="css"], .stApp, button, input, textarea, select {
  font-family: "Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif !important;
}
.stApp { background: var(--bb-bg); }
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], #MainMenu, footer { display:none !important; }
.block-container, [data-testid="stMainBlockContainer"] { padding-top: 0 !important; padding-bottom: 2rem; max-width: 1240px; }

/* App bar */
.bb-appbar { display:flex; align-items:center; justify-content:space-between; gap:16px;
  margin: -1rem -1rem 22px; padding: 16px 24px; background: var(--bb-navy);
  border-radius: 0 0 18px 18px; box-shadow: 0 6px 20px rgba(14,42,71,.18); }
.bb-brand { display:flex; align-items:center; gap:12px; }
.bb-name { color:#fff; font-size:21px; font-weight:700; letter-spacing:.2px; line-height:1.1; }
.bb-tag { color:#A9BCD3; font-size:12.5px; margin-top:2px; }
.bb-pill { color:#D7E6F5; font-size:12px; background:rgba(255,255,255,.08);
  border:1px solid rgba(255,255,255,.16); padding:6px 12px; border-radius:999px; white-space:nowrap; }

/* Cards (keyed containers) */
div[class*="st-key-card_"] { background: var(--bb-card); border:1px solid var(--bb-line);
  border-radius:16px; padding:20px 22px 18px; box-shadow:0 1px 2px rgba(16,24,40,.04); }
.bb-step { display:flex; align-items:center; gap:10px; margin-bottom:6px; }
.bb-step-n { width:26px; height:26px; border-radius:50%; background:var(--bb-blue); color:#fff;
  font-weight:700; font-size:13px; display:flex; align-items:center; justify-content:center; flex:none; }
.bb-step-n.done { background: var(--bb-teal); }
.bb-step-t { font-size:16px; font-weight:650; color:var(--bb-ink); }
.bb-step-s { color:var(--bb-muted); font-size:13px; margin:0 0 10px 36px; }

/* Badges */
.bb-badge { display:inline-flex; align-items:center; gap:6px; font-size:12.5px; font-weight:600;
  padding:5px 11px; border-radius:999px; }
.bb-badge.ok { color:var(--bb-green); background:var(--bb-green-bg); }
.bb-badge.no { color:#8A5A00; background:#FFF4DB; }

/* Inputs */
div[data-baseweb="select"] > div { border-radius:10px !important; border-color:var(--bb-line) !important; min-height:42px; }
[data-testid="stFileUploaderDropzone"] { border:2px dashed #C9D4E3 !important; border-radius:14px !important;
  background:#F8FAFD !important; padding:22px !important; }
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--bb-blue) !important; background:#F1F6FC !important; }
label p { font-weight:600 !important; color:var(--bb-ink) !important; font-size:13.5px !important; }

/* Buttons */
button[data-testid="stBaseButton-primary"] { background: linear-gradient(135deg,#1F6FB2,#155A93) !important;
  border:0 !important; border-radius:10px !important; min-height:44px; font-weight:650 !important;
  box-shadow:0 4px 12px rgba(31,111,178,.25); }
button[data-testid="stBaseButton-primary"]:disabled { background:#C9D4E3 !important; box-shadow:none; }
[data-testid="stDownloadButton"] button { border-radius:10px !important; min-height:44px; font-weight:650 !important; }

/* KPI tiles */
.bb-kpis { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:14px; margin: 4px 0 16px; }
.bb-kpi { background:var(--bb-card); border:1px solid var(--bb-line); border-radius:14px; padding:14px 16px; }
.bb-kpi-l { color:var(--bb-muted); font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:.5px; }
.bb-kpi-v { color:var(--bb-ink); font-size:24px; font-weight:700; margin-top:4px; font-variant-numeric: tabular-nums; }
.bb-kpi-s { color:var(--bb-muted); font-size:12.5px; margin-top:2px; }
.bb-kpi.status.ok { background:var(--bb-green-bg); border-color:#BFE6D2; }
.bb-kpi.status.ok .bb-kpi-v { color:var(--bb-green); }
.bb-kpi.status.no { background:var(--bb-red-bg); border-color:#F5C2BC; }
.bb-kpi.status.no .bb-kpi-v { color:var(--bb-red); }
@media (max-width: 800px) { .bb-kpis { grid-template-columns: repeat(2, minmax(0,1fr)); } }

/* Reconciliation table */
.bb-table { width:100%; border-collapse:collapse; font-size:14px; border:none !important; }
.bb-table th, .bb-table td { border-left:none !important; border-right:none !important; border-top:none !important; background:transparent !important; }
.bb-table th { text-align:left; color:var(--bb-muted); font-weight:600; font-size:12px; text-transform:uppercase;
  letter-spacing:.4px; padding:10px 12px; border-bottom:1px solid var(--bb-line); }
.bb-table td { padding:11px 12px; border-bottom:1px solid #EEF2F6; color:var(--bb-ink); font-variant-numeric: tabular-nums; }
.bb-table td.num, .bb-table th.num { text-align:right; }
.bb-ok { color:var(--bb-green); font-weight:700; } .bb-no { color:var(--bb-red); font-weight:700; }
.bb-dim { color:#9AA7B6; }

/* Export tiles */
.bb-export-t { font-weight:650; color:var(--bb-ink); font-size:15px; }
.bb-export-s { color:var(--bb-muted); font-size:13px; margin:2px 0 12px; }

/* How it works */
.bb-how { display:grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap:14px; margin-top:18px; }
.bb-how div { background:transparent; border:1px dashed #CDD6E2; border-radius:14px; padding:16px; color:var(--bb-muted); font-size:13.5px; }
.bb-how b { display:block; color:var(--bb-ink); font-size:14px; margin-bottom:4px; }

/* Tabs */
button[data-baseweb="tab"] p { font-weight:600; font-size:14px; }
div[data-baseweb="tab-highlight"] { background-color: var(--bb-blue) !important; }

.bb-footer { text-align:center; color:#9AA7B6; font-size:12px; margin-top:28px; }
</style>
"""


def html_block(markup):
    """Render custom HTML. Lines are flattened so Markdown never treats
    indented HTML as a code block."""
    st.markdown(" ".join(line.strip() for line in markup.splitlines() if line.strip()),
                unsafe_allow_html=True)


def money(v):
    if v is None:
        return '<span class="bb-dim">—</span>'
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def step(n, title, subtitle=None, done=False):
    sub = f'<div class="bb-step-s">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="bb-step"><div class="bb-step-n{" done" if done else ""}">'
        f'{"✓" if done else n}</div><div class="bb-step-t">{title}</div></div>{sub}',
        unsafe_allow_html=True,
    )


def show_statement_preview(uploaded, key, source_pages=None, *, initial_page=None):
    if not st.checkbox("Preview original PDF", key=f"bb_preview_{key}"):
        return
    pdf_bytes = uploaded.getvalue()
    try:
        pages = sorted(set(source_pages)) if source_pages else range(1, eng.statement_page_count(pdf_bytes) + 1)
        if not pages:
            st.warning("The uploaded PDF has no pages to display.")
            return
        default_index = pages.index(initial_page) if initial_page in pages else 0
        page_number = st.selectbox(
            "PDF page to preview", pages, index=default_index, key=f"bb_preview_page_{key}",
        )
        image = eng.render_statement_page(pdf_bytes, page_number)
        st.image(image, caption=f"Original PDF · page {page_number}", width="stretch")
    except ValueError as error:
        st.warning(str(error))
    except RuntimeError:
        st.warning("The uploaded PDF page could not be displayed.")


def apply_detected_selection(pdf_bytes):
    try:
        detected = eng.detect_statement_selection(pdf_bytes)
    except (ValueError, RuntimeError) as error:
        st.session_state["bb_detection"] = f"Could not read statement details. {error}"
        return
    if "bank" in detected:
        st.session_state["bb_bank"] = detected["bank"]
    if "account type" in detected:
        st.session_state["bb_type"] = detected["account type"]
    st.session_state["bb_detection"] = (
        "Review the detected selection. Choose any undetected details manually."
        if detected else "Bank and account type could not be detected. Select the details manually."
    )


def file_stem(df, bank, account_type):
    short = {
        "TD Canada Trust": "TD", "RBC Royal Bank": "RBC", "BMO Bank of Montreal": "BMO",
        "Scotiabank": "Scotiabank", "CIBC": "CIBC",
    }.get(bank, bank.split()[0])
    kind = account_type.replace(" ", "")
    try:
        d = pd.to_datetime(df["Date"])
        return f"{short}_{kind}_{d.min():%Y%m%d}-{d.max():%Y%m%d}"
    except Exception:
        return f"{short}_{kind}_{datetime.now():%Y%m%d}"


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------
_ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "bankbridge.png")
st.set_page_config(page_title="BankBridgeNext", page_icon=_ICON if os.path.exists(_ICON) else "🌉", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)
build_id = installed_build_id()
build_label = f" · Build {build_id}" if build_id else ""
html_block(
    f"""<div class="bb-appbar">
      <div class="bb-brand">{LOGO_SVG}
        <div><div class="bb-name">BankBridgeNext</div>
        <div class="bb-tag">PDF bank &amp; credit-card statements → QuickBooks, reconciled{build_label}</div></div>
      </div>
      <div class="bb-pill">🔒 Processed on this computer · nothing is uploaded</div>
    </div>""",
)

ss = st.session_state
banks = list(eng.CANADIAN_BANKS)
types = list(eng.ACCOUNT_TYPES)

left, right = st.columns(2, gap="medium")

with left:
    with st.container(key="card_setup"):
        step(1, "Statement type", "Pick the bank and the kind of account on the statement.")
        c1, c2 = st.columns(2)
        bank = c1.selectbox("Bank", banks, key="bb_bank")
        account_type = c2.selectbox(
            "Account type", types,
            index=types.index("Business Chequing") if "Business Chequing" in types else 0,
            key="bb_type",
        )
        dedicated = eng.get_dedicated_extractor(bank, account_type)
        eligible = account_type in eng.UNIVERSAL_DEPOSIT_TYPES or account_type in eng.CREDIT_CARD_SELECTIONS
        use_fallback = st.checkbox("Try experimental statement parser") if dedicated and eligible else False
        universal = eligible and (dedicated is None or use_fallback)
        use_ocr = st.checkbox("Use local OCR for scanned pages", value=False) if universal else False
        extractor = get_extractor(bank, account_type, use_ocr=use_ocr, use_fallback=use_fallback)
        if universal:
            st.info("Experimental parser. CSV available after reconciliation.")
        elif extractor:
            st.markdown(f'<span class="bb-badge ok">● Dedicated parser — {html.escape(bank)} · '
                        f'{html.escape(account_type)}</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="bb-badge no">● Coming soon — this statement type is not '
                        'activated yet</span>', unsafe_allow_html=True)

with right:
    with st.container(key="card_upload"):
        step(2, "Upload statement", "Select the PDF statement to convert.")
        uploaded = st.file_uploader("Statement PDF", type=["pdf"], key="bb_file",
                                    label_visibility="collapsed",
                                    on_change=lambda: ss.pop("bb_detection", None))
        if uploaded is not None:
            st.button("Detect bank and account type", on_click=apply_detected_selection,
                      args=(uploaded.getvalue(),))
            if ss.get("bb_detection"):
                st.caption(ss["bb_detection"])
        go = st.button("Convert statement", type="primary", width="stretch",
                       disabled=(uploaded is None or extractor is None))

current_input = (uploaded.file_id if uploaded else None, bank, account_type, universal, use_ocr)
if ss.get("bb_input") != current_input or go:
    for key in ("bb_df", "bb_info", "bb_bank_done", "bb_type_done", "bb_file_done", "bb_error", "bb_file_error"):
        ss.pop(key, None)
    ss["bb_input"] = current_input

if go and uploaded is not None and extractor is not None:
    with st.spinner("Reading statement…"):
        try:
            df, info = extractor(uploaded.getvalue())
            ss["bb_df"], ss["bb_info"] = df, info
            ss["bb_bank_done"], ss["bb_type_done"] = bank, account_type
            ss["bb_file_done"] = uploaded.name
            ss["bb_run"] = ss.get("bb_run", 0) + 1
        except eng.StatementFileError as error:
            ss["bb_file_error"] = str(error)
        except Exception as e:  # show the parser's message nicely
            ss["bb_error"] = str(e) or e.__class__.__name__

has_results = "bb_df" in ss
if ss.get("bb_file_error"):
    st.error(ss["bb_file_error"])
elif ss.get("bb_error"):
    st.error(f"**We couldn't read this statement.** {ss['bb_error']}\n\n"
             "Check that the bank and account type match the PDF, then try again.")
    if uploaded is not None:
        error_page = re.search(r"(?:\bPDF page|\bon page|^Page) ([0-9]{1,6})\b", ss["bb_error"], re.IGNORECASE)
        show_statement_preview(
            uploaded, "failed", initial_page=int(error_page.group(1)) if error_page else None,
        )


if not has_results:
    html_block(
        """<div class="bb-how">
          <div><b>1 · Choose</b>Select the bank and account type that match your statement.</div>
          <div><b>2 · Convert</b>BankBridge reads every transaction and checks it against the statement totals.</div>
          <div><b>3 · Export</b>Once it reconciles, download a CSV for QuickBooks Online or a QBO file for QuickBooks Desktop.</div>
        </div>""",
    )
else:
    df, info = ss["bb_df"], ss["bb_info"]
    p_bank, p_type = ss["bb_bank_done"], ss["bb_type_done"]
    if info.get("td_easyweb"):
        st.caption("TD EasyWeb activity printout. Reconciliation uses the printed totals and running balances for the displayed period.")
    if info.get("currency") or info.get("universal"):
        st.caption(f"Statement currency: {info.get('currency') or 'Undetected'}. Import CSV into an account in the same currency.")

    st.write("")
    kpi_slot = st.empty()  # summary tiles appear above the table
    with st.container(key="card_review"):
        step(3, "Review & reconcile",
             f"{html.escape(ss.get('bb_file_done', ''))} · {html.escape(p_bank)} · {html.escape(p_type)}"
             " — edit any cell below; totals update instantly.")

        if df.empty:
            st.error("No transactions were found in this PDF.")
            edited = df
            rec = None
        else:
            tab_tx, tab_rec = st.tabs(["Transactions", "Reconciliation detail"])
            with tab_tx:
                review_frame = df
                if "source_pages" in info:
                    review_frame = df.assign(SourcePage=pd.array(info["source_pages"], dtype="Int64"))
                edited = st.data_editor(
                    review_frame, key=f"bb_editor_{ss['bb_run']}", width="stretch", hide_index=True,
                    num_rows="dynamic", height=min(420, 38 + 35 * (len(df) + 1)),
                    column_config={
                        "SourcePage": st.column_config.NumberColumn(
                            "PDF page", help="Page of the original PDF containing this extracted row.",
                            disabled=True, format="%d", width="small",
                        ),
                        "Date": st.column_config.TextColumn("Date", width="small"),
                        "Description": st.column_config.TextColumn("Description", width="large"),
                        "Debit": st.column_config.NumberColumn("Debit", format="dollar", min_value=0.0),
                        "Credit": st.column_config.NumberColumn("Credit", format="dollar", min_value=0.0),
                    },
                )
                edited = edited.dropna(how="all").copy()
                edited["Debit"] = pd.to_numeric(edited["Debit"], errors="coerce").fillna(0.0)
                edited["Credit"] = pd.to_numeric(edited["Credit"], errors="coerce").fillna(0.0)
                edited["Description"] = edited["Description"].fillna("").astype(str)
                if info.get("source_pages") and uploaded is not None:
                    show_statement_preview(uploaded, ss["bb_run"], info["source_pages"])

            rec = reconcile(edited, info)

            with tab_rec:
                body = ""
                for label, stmt, ext, kind in rec["rows"]:
                    fmt = (lambda v: '<span class="bb-dim">—</span>' if v is None else f"{v:,}") \
                        if kind == "n" else money
                    if stmt is None or ext is None:
                        mark = '<span class="bb-dim">—</span>'
                    elif stmt == ext:
                        mark = '<span class="bb-ok">✓ Match</span>'
                    else:
                        mark = '<span class="bb-no">✕ Differs</span>'
                    body += (f"<tr><td>{label}</td><td class='num'>{fmt(stmt)}</td>"
                             f"<td class='num'>{fmt(ext)}</td><td>{mark}</td></tr>")
                st.markdown(
                    "<table class='bb-table'><tr><th>Check</th><th class='num'>Statement</th>"
                    f"<th class='num'>BankBridge</th><th>Result</th></tr>{body}</table>",
                    unsafe_allow_html=True,
                )
                if rec["details"]:
                    st.write("")
                    st.caption("Statement summary")
                    st.markdown(
                        "<table class='bb-table'>" + "".join(
                            f"<tr><td>{k}</td><td class='num'>{money(v)}</td></tr>"
                            for k, v in rec["details"]) + "</table>",
                        unsafe_allow_html=True,
                    )

    if rec is not None:
        status_cls, status_txt, status_sub = (
            ("ok", "Reconciled", "Matches the statement totals") if rec["ok"]
            else ("no", "Not reconciled", "See Reconciliation detail")
        )
        with kpi_slot.container():
          html_block(
            f"""<div class="bb-kpis">
              <div class="bb-kpi"><div class="bb-kpi-l">Transactions</div>
                <div class="bb-kpi-v">{rec['count']}</div>
                <div class="bb-kpi-s">{rec['debit_count']} debits · {rec['credit_count']} credits</div></div>
              <div class="bb-kpi"><div class="bb-kpi-l">Total debits</div>
                <div class="bb-kpi-v">${rec['debit_total']:,.2f}</div><div class="bb-kpi-s">Money out / charges</div></div>
              <div class="bb-kpi"><div class="bb-kpi-l">Total credits</div>
                <div class="bb-kpi-v">${rec['credit_total']:,.2f}</div><div class="bb-kpi-s">Money in / payments</div></div>
              <div class="bb-kpi status {status_cls}"><div class="bb-kpi-l">Status</div>
                <div class="bb-kpi-v">{'✓ ' if rec['ok'] else '✕ '}{status_txt}</div>
                <div class="bb-kpi-s">{status_sub}</div></div>
            </div>""",
        )

        with st.container(key="card_export"):
            step(4, "Export to QuickBooks", done=False)
            if not rec["ok"]:
                st.warning("Downloads unlock once the statement reconciles. Check the "
                           "**Reconciliation detail** tab, fix any wrong rows above, and the "
                           "totals will update automatically.")
            else:
                stem = file_stem(edited, p_bank, p_type)
                csv_data = eng.generate_quickbooks_csv(edited)
                try:
                    qbo_data, qbo_note = eng.make_qbo(edited, info, p_type)
                except Exception as e:
                    qbo_data, qbo_note = None, f"QBO file could not be created: {e}"

                e1, e2 = st.columns(2, gap="medium")
                with e1:
                    st.markdown('<div class="bb-export-t">QuickBooks Online</div>'
                                '<div class="bb-export-s">CSV (Date, Description, Amount) for '
                                'Banking → Upload transactions.</div>', unsafe_allow_html=True)
                    st.download_button("Download CSV", data=csv_data, file_name=f"{stem}.csv",
                                       mime="text/csv", width="stretch", type="primary")
                with e2:
                    st.markdown('<div class="bb-export-t">QuickBooks Desktop</div>'
                                '<div class="bb-export-s">Web Connect (.QBO) file — double-click it '
                                'or use File → Utilities → Import.</div>', unsafe_allow_html=True)
                    if qbo_data is not None:
                        st.download_button("Download QBO", data=qbo_data.encode("cp1252", errors="replace"),
                                           file_name=f"{stem}.qbo", mime="application/x-ofx",
                                           width="stretch", type="primary")
                    else:
                        st.button("QBO not available for this account", disabled=True, width="stretch")
                        if qbo_note:
                            st.caption(qbo_note)

            with st.expander("QuickBooks Desktop IIF"):
                if not rec["ok"] or info.get("currency") not in (None, "CAD"):
                    reason = ("Reconcile the statement to enable IIF."
                              if not rec["ok"] else "IIF currently supports CAD statements.")
                    st.caption(reason)
                    st.button("Download IIF for QuickBooks Desktop", disabled=True, width="stretch")
                else:
                    st.info("IIF posts directly to your QuickBooks registers. "
                            "Import into a test company first and check for duplicates before importing.")
                    st.caption(
                        f"{rec['count']} transactions · {money(rec['debit_total'])} debits · "
                        f"{money(rec['credit_total'])} credits. Use the full names of two existing "
                        "QuickBooks accounts, including any parent accounts."
                    )
                    iif_key = f"bb_iif_{ss['bb_run']}"
                    register_label = ("QuickBooks credit card account" if info["statement_type"] == "credit_card"
                                      else "QuickBooks bank account")
                    register_account = st.text_input(register_label, key=f"{iif_key}_register")
                    clearing_account = st.text_input("QuickBooks clearing account", key=f"{iif_key}_clearing")
                    confirmed = st.checkbox(
                        "I confirmed the statement and both QuickBooks accounts use CAD.",
                        key=f"{iif_key}_confirm",
                    )
                    iif_data = None
                    if register_account.strip() and clearing_account.strip() and confirmed:
                        try:
                            iif_data = eng.generate_statement_iif(edited, info, register_account, clearing_account)
                        except ValueError as error:
                            st.warning(str(error))
                    st.download_button(
                        "Download IIF for QuickBooks Desktop", data=iif_data or b"",
                        file_name=f"{stem}.iif", mime="application/octet-stream",
                        disabled=iif_data is None, width="stretch",
                    )

st.markdown(f'<div class="bb-footer">BankBridge {APP_VERSION} · Tax Square Professional Corporation</div>',
            unsafe_allow_html=True)
