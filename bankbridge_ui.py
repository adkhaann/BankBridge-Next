"""
BankBridge - user interface.

All statement parsing and QBO/CSV generation lives in engine.py, which is
built automatically from your app.py. This file only draws the screen.

WHEN YOU ADD A NEW BANK TO app.py:
  1. add the combination to SUPPORTED_COMBINATIONS in app.py (as before)
  2. add one line to EXTRACTORS below naming its extract_... function
  3. if it has its own QBO generator, add it in make_qbo() below
"""
import html
import os
from datetime import datetime

import pandas as pd
import streamlit as st

import engine as eng

APP_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Which extract_... function handles each (bank, account type)
# ---------------------------------------------------------------------------
_CIBC_DEPOSIT = "extract_cibc_chequing_transactions"
EXTRACTORS = {
    ("TD Canada Trust", "Business Chequing"): "extract_td_chequing_transactions",
    ("TD Canada Trust", "Credit Card"): "extract_td_credit_card_transactions",
    ("RBC Royal Bank", "Business Chequing"): "extract_rbc_business_chequing_transactions",
    ("RBC Royal Bank", "Credit Card"): "extract_rbc_mastercard_transactions",
    ("BMO Bank of Montreal", "Business Chequing"): "extract_bmo_business_chequing_transactions",
    ("BMO Bank of Montreal", "Credit Card"): "extract_bmo_credit_card_transactions",
    ("Scotiabank", "Business Chequing"): "extract_scotiabank_business_chequing_transactions",
    ("CIBC", "Credit Card"): "extract_cibc_credit_card_transactions",
    ("CIBC", "Personal Chequing"): _CIBC_DEPOSIT,
    ("CIBC", "Business Chequing"): _CIBC_DEPOSIT,
    ("CIBC", "Personal Savings"): _CIBC_DEPOSIT,
    ("CIBC", "Business Savings"): _CIBC_DEPOSIT,
}


def get_extractor(bank, account_type):
    if (bank, account_type) not in getattr(eng, "SUPPORTED_COMBINATIONS", set()):
        return None
    name = EXTRACTORS.get((bank, account_type))
    return getattr(eng, name, None) if name else None


def make_qbo(df, info, account_type):
    """Same routing as the original app. Returns (qbo_text, note)."""
    bank = info.get("bank")
    if bank == "CIBC":
        try:
            return eng.generate_cibc_qbo(df, info, account_type), None
        except ValueError as e:
            return None, str(e)

    if info["statement_type"] == "chequing":
        if bank == "RBC Royal Bank":
            return eng.generate_rbc_business_chequing_qbo(
                df, info["account_id"], info.get("branch_id", "00000"),
                info.get("ending_balance")), None
        if bank == "BMO Bank of Montreal":
            return eng.generate_bmo_chequing_qbo(
                df, info["account_id"], info.get("ending_balance")), None
        if bank == "Scotiabank":
            return eng.generate_scotiabank_chequing_qbo(
                df, info["account_id"], info.get("ending_balance")), None
        return eng.generate_td_chequing_qbo(df, info["account_id"]), None

    new_balance = info["summary"].get("new_balance")
    if bank == "BMO Bank of Montreal":
        return eng.generate_bmo_credit_card_qbo(df, info["account_id"], new_balance), None
    if bank == "RBC Royal Bank":
        return eng.generate_rbc_mastercard_qbo(df, info["account_id"], new_balance), None
    return eng.generate_td_credit_card_qbo(df, info["account_id"], new_balance), None


# ---------------------------------------------------------------------------
# Reconciliation (same rules as the original app)
# ---------------------------------------------------------------------------
def reconcile(df, info):
    debit_total = round(float(df["Debit"].sum()), 2)
    credit_total = round(float(df["Credit"].sum()), 2)
    debit_count = int((df["Debit"] > 0).sum())
    credit_count = int((df["Credit"] > 0).sum())
    rows, details, ok = [], [], False

    if info["statement_type"] == "chequing":
        c = info.get("control", {})
        if c.get("debit_total") is not None:
            rows.append(("Withdrawals / debits (count)", c.get("debit_count"), debit_count, "n"))
            rows.append(("Withdrawals / debits (total)", c["debit_total"], debit_total, "$"))
        if c.get("credit_total") is not None:
            rows.append(("Deposits / credits (count)", c.get("credit_count"), credit_count, "n"))
            rows.append(("Deposits / credits (total)", c["credit_total"], credit_total, "$"))
        if c.get("debit_total") is not None and c.get("credit_total") is not None:
            ok = (
                debit_count == c.get("debit_count")
                and credit_count == c.get("credit_count")
                and abs(debit_total - c["debit_total"]) < 0.01
                and abs(credit_total - c["credit_total"]) < 0.01
            )
    else:
        s = info.get("summary", {})
        prev = s.get("previous_balance")
        purchases = s.get("purchases_charges")
        interest = s.get("interest") or 0.0
        fees = s.get("fees") or 0.0
        payments = s.get("payments_credits")
        new_bal = s.get("new_balance")
        expected = (purchases or 0.0) + interest + fees
        charges_ok = abs(debit_total - expected) < 0.01
        payments_ok = payments is not None and abs(credit_total - payments) < 0.01
        calc, math_ok = None, False
        if None not in (prev, payments, purchases, new_bal):
            calc = prev - payments + purchases + interest + fees
            math_ok = abs(calc - new_bal) < 0.01
        ok = charges_ok and payments_ok and math_ok
        rows.append(("Charges (purchases + interest + fees)", expected, debit_total, "$"))
        rows.append(("Payments & credits", payments, credit_total, "$"))
        rows.append(("New balance (statement vs. calculated)", new_bal, calc, "$"))
        details = [
            ("Previous balance", prev), ("Purchases & charges", purchases),
            ("Interest", interest), ("Fees", fees),
            ("Payments & credits", payments), ("New balance", new_bal),
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
st.set_page_config(page_title="BankBridge", page_icon=_ICON if os.path.exists(_ICON) else "🌉", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)
html_block(
    f"""<div class="bb-appbar">
      <div class="bb-brand">{LOGO_SVG}
        <div><div class="bb-name">BankBridge</div>
        <div class="bb-tag">PDF bank &amp; credit-card statements → QuickBooks, reconciled</div></div>
      </div>
      <div class="bb-pill">🔒 Processed on this computer · nothing is uploaded</div>
    </div>""",
)

ss = st.session_state
has_results = "bb_df" in ss
banks = list(getattr(eng, "CANADIAN_BANKS", sorted({b for b, _ in EXTRACTORS})))
types = list(getattr(eng, "ACCOUNT_TYPES", sorted({t for _, t in EXTRACTORS})))

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
        extractor = get_extractor(bank, account_type)
        if extractor:
            st.markdown(f'<span class="bb-badge ok">● Supported — {html.escape(bank)} · '
                        f'{html.escape(account_type)}</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="bb-badge no">● Coming soon — this statement type is not '
                        'activated yet</span>', unsafe_allow_html=True)

with right:
    with st.container(key="card_upload"):
        step(2, "Upload statement", "PDF downloaded from online banking (not a scan).")
        uploaded = st.file_uploader("Statement PDF", type=["pdf"], key="bb_file",
                                    label_visibility="collapsed")
        go = st.button("Convert statement", type="primary", width="stretch",
                       disabled=(uploaded is None or extractor is None))

if go and uploaded is not None and extractor is not None:
    with st.spinner("Reading statement…"):
        try:
            df, info = extractor(uploaded.getvalue())
            ss["bb_df"], ss["bb_info"] = df, info
            ss["bb_bank_done"], ss["bb_type_done"] = bank, account_type
            ss["bb_file_done"] = uploaded.name
            ss["bb_run"] = ss.get("bb_run", 0) + 1
            ss.pop("bb_error", None)
        except Exception as e:  # show the parser's message nicely
            for k in ("bb_df", "bb_info"):
                ss.pop(k, None)
            ss["bb_error"] = str(e) or e.__class__.__name__
    has_results = "bb_df" in ss

if ss.get("bb_error"):
    st.error(f"**We couldn't read this statement.** {ss['bb_error']}\n\n"
             "Check that the bank and account type match the PDF, then try again.")

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
                edited = st.data_editor(
                    df, key=f"bb_editor_{ss['bb_run']}", width="stretch", hide_index=True,
                    num_rows="dynamic", height=min(420, 38 + 35 * (len(df) + 1)),
                    column_config={
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

            rec = reconcile(edited, info)

            with tab_rec:
                body = ""
                for label, stmt, ext, kind in rec["rows"]:
                    fmt = (lambda v: '<span class="bb-dim">—</span>' if v is None else f"{v:,}") \
                        if kind == "n" else money
                    if stmt is None or ext is None:
                        mark = '<span class="bb-dim">—</span>'
                    elif (kind == "n" and stmt == ext) or (kind == "$" and abs(stmt - ext) < 0.01):
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
                    st.caption("Statement summary as printed on the PDF")
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
                    qbo_data, qbo_note = make_qbo(edited, info, p_type)
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

st.markdown(f'<div class="bb-footer">BankBridge {APP_VERSION} · Tax Square Professional Corporation</div>',
            unsafe_allow_html=True)
