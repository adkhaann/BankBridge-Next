import streamlit as st
import pandas as pd
import fitz
import re
import hashlib
from datetime import datetime


# =========================================================
# PAGE SETTINGS
# =========================================================

st.set_page_config(
    page_title="Tax Square PDF to QuickBooks Converter",
    page_icon="📄",
    layout="wide"
)

st.title("PDF to QuickBooks Converter")

st.write(
    "Convert supported Canadian bank and credit-card PDF statements into "
    "QuickBooks Online CSV or QuickBooks Desktop QBO files."
)

st.divider()


# =========================================================
# GENERAL HELPERS
# =========================================================

STATEMENT_CURRENCY_PATTERN = r"(?:Account currency|Currency|Devise du compte|Devise)(?:\s*:\s*|\s+)(.+)"
STATEMENT_CURRENCY_NAMES = {
    "canadian dollar": "CAD", "canadian dollars": "CAD",
    "dollar canadien": "CAD", "dollars canadiens": "CAD",
    "us dollar": "USD", "us dollars": "USD",
    "u.s. dollar": "USD", "u.s. dollars": "USD",
    "dollar américain": "USD", "dollars américains": "USD",
    "euro": "EUR", "euros": "EUR",
    "british pound": "GBP", "british pounds": "GBP",
    "livre sterling": "GBP", "livres sterling": "GBP",
}


def printed_currency_code(line):
    match = re.fullmatch(STATEMENT_CURRENCY_PATTERN, line.strip(), re.IGNORECASE)
    if not match:
        return None
    value = " ".join(match.group(1).casefold().split())
    if re.fullmatch(r"[a-z]{3}", value):
        return value.upper()
    # Accept both "US dollars (USD)" and "USD (US dollars)".
    pair = re.fullmatch(r"([^()]+)\s*\(([^()]+)\)", value)
    if pair:
        first, second = (part.strip() for part in pair.groups())
        code, name = (first, second) if re.fullmatch(r"[a-z]{3}", first) else (second, first)
        named_code = STATEMENT_CURRENCY_NAMES.get(name)
        if named_code and re.fullmatch(r"[a-z]{3}", code):
            if named_code != code.upper():
                raise ValueError("The statement declares conflicting currencies in one label.")
            return named_code
    return STATEMENT_CURRENCY_NAMES.get(value)


def statement_currency(full_text):
    codes = {code for line in full_text.splitlines() if (code := printed_currency_code(line))}
    if len(codes) > 1:
        raise ValueError("The statement declares conflicting currencies.")
    return next(iter(codes), None)


def clean_amount(value):

    if value is None:
        return 0.0

    value = (
        str(value)
        .replace(",", "")
        .replace("$", "")
        .replace("(", "-")
        .replace(")", "")
        .strip()
    )

    try:
        return float(value)
    except:
        return 0.0


def clean_qbo_text(text):

    text = str(text)

    text = text.replace("&", "and")
    text = text.replace("<", "")
    text = text.replace(">", "")
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def qbo_datetime(date_object):

    return (
        date_object.strftime("%Y%m%d")
        + "120000"
    )


def create_fitid(
    prefix,
    date_text,
    description,
    amount,
    occurrence
):

    source = (
        f"{prefix}|"
        f"{date_text}|"
        f"{description}|"
        f"{amount:.2f}|"
        f"{occurrence}"
    )

    digest = hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()

    return digest[:24]


# =========================================================
# TD CHEQUING HELPERS
# =========================================================

def get_chequing_statement_year(text):

    match = re.search(
        r"([A-Z]{3})\s*(\d{1,2})/(\d{2})\s*-\s*"
        r"([A-Z]{3})\s*(\d{1,2})/(\d{2})",
        text,
        re.IGNORECASE
    )

    if match:
        return 2000 + int(match.group(6))

    return datetime.now().year


def parse_chequing_date(
    date_text,
    statement_year
):

    try:

        parsed = datetime.strptime(
            f"{date_text}{statement_year}",
            "%b%d%Y"
        )

        return parsed.strftime(
            "%Y-%m-%d"
        )

    except:
        return date_text


def get_chequing_control_totals(text):

    credit_match = re.search(
        r"Credits\s+(\d+)\s+([\d,]+\.\d{2})",
        text,
        re.IGNORECASE
    )

    debit_match = re.search(
        r"Debits\s+(\d+)\s+([\d,]+\.\d{2})",
        text,
        re.IGNORECASE
    )

    result = {
        "credit_count": None,
        "credit_total": None,
        "debit_count": None,
        "debit_total": None
    }

    if credit_match:

        result["credit_count"] = int(
            credit_match.group(1)
        )

        result["credit_total"] = clean_amount(
            credit_match.group(2)
        )

    if debit_match:

        result["debit_count"] = int(
            debit_match.group(1)
        )

        result["debit_total"] = clean_amount(
            debit_match.group(2)
        )

    return result


def get_chequing_ending_balance(text):

    matches = re.findall(
        r"([\d,]+\.\d{2})\s*(OD)?",
        text,
        re.IGNORECASE
    )

    if not matches:
        return 0.0

    # Ending balance is not required for transaction import.
    # Use zero if we cannot identify it reliably.
    return 0.0


def get_chequing_account_id(text):

    match = re.search(
        r"\b\d{4}\s+\d{4}-(\d{7})\b",
        text
    )

    if match:
        return match.group(1)

    return None


# =========================================================
# TD CHEQUING PARSER
# =========================================================

def extract_td_easyweb_activity(document, full_text):
    """Read TD browser-printed activity and verify printed totals and row balances."""
    period_match = re.search(r"Your transactions for\s+([^\n]+?)\s+to\s+([^\n]+)", full_text, re.IGNORECASE)
    if not period_match:
        raise ValueError("The TD EasyWeb printout is missing the displayed transaction period.")
    period = tuple(universal_statement_date(" ".join(date.split())) for date in period_match.groups())
    rows, balances, source_pages = [], [], []
    totals = []
    boundaries = None
    date_pattern = re.compile(r"^[A-Za-z]{3} \d{1,2}, \d{4}$")
    for page in document:
        lines = page.get_text(sort=True).splitlines()
        for line in lines:
            match = re.fullmatch(r"\s*Total\s*:\s+(\$[\d,]+\.\d{2})\s+(\$[\d,]+\.\d{2})\s*", line, re.IGNORECASE)
            if match:
                totals.append(tuple(universal_money_cents(amount) for amount in match.groups()))
        words = page.get_text("words")
        for date_heading in (word for word in words if word[4].casefold() == "date"):
            nearby = sorted(
                (word for word in words if abs(word[1] - date_heading[1]) <= 2),
                key=lambda word: word[0],
            )
            if [word[4].casefold() for word in nearby] == [
                "date", "transaction", "description", "withdrawals", "deposits", "balance"
            ]:
                _, _, _, withdrawal, deposit, balance = nearby
                boundaries = (withdrawal[0], (withdrawal[2] + deposit[2]) / 2, (deposit[2] + balance[2]) / 2)
                break
        if boundaries is None:
            continue

        for month in sorted((word for word in words if word[0] < page.rect.width * 0.15
                             and re.fullmatch(r"[A-Za-z]{3}", word[4])), key=lambda word: word[1]):
            line = sorted(
                (word for word in words if abs(word[1] - month[1]) <= 2),
                key=lambda word: word[0],
            )
            date = " ".join(word[4] for word in line[:3])
            if not date_pattern.fullmatch(date):
                continue
            fields = [[], [], [], []]
            for word in line[3:]:
                column = sum(word[2] > boundary for boundary in boundaries)
                fields[column].append(word[4])
            description, debit, credit, balance = (" ".join(field) for field in fields)
            if not description or not balance or bool(debit) == bool(credit):
                raise ValueError(f"An EasyWeb transaction has unclear columns on page {page.number + 1}.")
            debit_cents = universal_money_cents(debit) if debit else 0
            credit_cents = universal_money_cents(credit) if credit else 0
            if min(debit_cents, credit_cents) < 0:
                raise ValueError(f"An EasyWeb transaction has an invalid amount on page {page.number + 1}.")
            rows.append((universal_statement_date(date), description, debit_cents, credit_cents))
            balances.append(universal_money_cents(balance))
            source_pages.append(page.number + 1)

    if not rows or len(totals) != 1:
        raise ValueError("Expected EasyWeb activity rows and one printed withdrawal/deposit total.")
    rows.reverse()
    balances.reverse()
    source_pages.reverse()
    dates = [row[0] for row in rows]
    if dates != sorted(dates):
        raise ValueError("The EasyWeb activity table must be printed in newest-first order.")
    opening = balances[0] + rows[0][2] - rows[0][3]
    if not statement_running_balances_match(rows, opening, balances, is_card=False):
        raise ValueError("An EasyWeb printed running balance differs from the calculated balance.")
    # Zero-dollar activity affects neither the ledger nor the CSV import.
    nonzero = [index for index, row in enumerate(rows) if row[2] or row[3]]
    debit, credit = totals[0]
    frame = pd.DataFrame([rows[index] for index in nonzero], columns=["Date", "Description", "Debit", "Credit"])
    frame[["Debit", "Credit"]] = frame[["Debit", "Credit"]] / 100
    return frame, {
        "td_easyweb": True, "statement_type": "chequing", "bank": "TD Canada Trust",
        "currency": statement_currency(full_text), "period": period,
        "control": {"opening": opening / 100, "closing": balances[-1] / 100,
                    "debit": debit / 100, "credit": credit / 100},
        "running_balances": [balances[index] / 100 for index in nonzero],
        "source_pages": [source_pages[index] for index in nonzero],
    }


def extract_td_chequing_transactions(
    pdf_bytes
):

    doc = fitz.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    full_text = ""

    for page in doc:
        full_text += page.get_text("text") + "\n"

    if re.search(r"Your transactions for\s+", full_text, re.IGNORECASE):
        with doc:
            return extract_td_easyweb_activity(doc, full_text)

    statement_year = (
        get_chequing_statement_year(
            full_text
        )
    )

    controls = (
        get_chequing_control_totals(
            full_text
        )
    )

    account_id = (
        get_chequing_account_id(
            full_text
        )
    )

    transactions = []

    # -----------------------------------------------------
    # IMPORTANT:
    #
    # This method reads each dated TD row and then identifies
    # the two transaction amount columns.
    # -----------------------------------------------------

    for page in doc:

        words = page.get_text("words")

        rows = {}

        for word in words:

            x0, y0, x1, y1, text = word[:5]

            row_key = round(
                y0 / 3
            ) * 3

            rows.setdefault(
                row_key,
                []
            )

            rows[row_key].append({
                "x0": x0,
                "x1": x1,
                "text": text
            })

        for row_y in sorted(
            rows.keys()
        ):

            row = sorted(
                rows[row_y],
                key=lambda item: item["x0"]
            )

            row_text = " ".join(
                item["text"]
                for item in row
            )

            date_match = re.search(
                r"\b"
                r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|"
                r"SEP|OCT|NOV|DEC)"
                r"(\d{2})"
                r"\b",
                row_text,
                re.IGNORECASE
            )

            if not date_match:
                continue

            date_token = (
                date_match.group(1).upper()
                +
                date_match.group(2)
            )

            if (
                "BALANCE FORWARD"
                in row_text.upper()
            ):
                continue

            amount_words = []

            for item in row:

                cleaned = (
                    item["text"]
                    .replace("$", "")
                    .replace(",", "")
                    .strip()
                )

                if re.fullmatch(
                    r"\d+\.\d{2}",
                    cleaned
                ):

                    amount_words.append({
                        "x": (
                            item["x0"]
                            +
                            item["x1"]
                        ) / 2,
                        "amount": clean_amount(
                            cleaned
                        )
                    })

            if not amount_words:
                continue

            # -------------------------------------------------
            # The far-right amount is the running balance.
            # Remove it when three amount values are present.
            # -------------------------------------------------

            amount_words = sorted(
                amount_words,
                key=lambda item: item["x"]
            )

            transaction_amounts = (
                amount_words[:-1]
                if len(amount_words) >= 2
                else amount_words
            )

            # -------------------------------------------------
            # Description ends before first transaction amount.
            # -------------------------------------------------

            first_amount_x = min(
                item["x"]
                for item in transaction_amounts
            )

            description_parts = []

            for item in row:

                center_x = (
                    item["x0"]
                    +
                    item["x1"]
                ) / 2

                if center_x < first_amount_x:

                    text = item["text"]

                    if (
                        text.upper()
                        != date_token
                    ):

                        description_parts.append(
                            text
                        )

            description = " ".join(
                description_parts
            ).strip()

            if not description:
                continue

            # -------------------------------------------------
            # TD statement transaction amount columns:
            #
            # left transaction amount = debit
            # right transaction amount = credit
            #
            # When only one transaction amount exists,
            # determine its side from its x position.
            # -------------------------------------------------

            debit = 0.0
            credit = 0.0

            page_width = (
                page.rect.width
            )

            for item in transaction_amounts:

                ratio = (
                    item["x"]
                    /
                    page_width
                )

                if ratio < 0.59:
                    debit = item["amount"]

                else:
                    credit = item["amount"]

            if (
                debit == 0
                and
                credit == 0
            ):
                continue

            transaction_date = (
                parse_chequing_date(
                    date_token,
                    statement_year
                )
            )

            transactions.append({
                "Date": transaction_date,
                "Description": description,
                "Debit": debit,
                "Credit": credit
            })

    doc.close()

    df = pd.DataFrame(
        transactions
    )

    if not df.empty:

        df["Debit"] = pd.to_numeric(
            df["Debit"],
            errors="coerce"
        ).fillna(0)

        df["Credit"] = pd.to_numeric(
            df["Credit"],
            errors="coerce"
        ).fillna(0)

    statement_info = {
        "currency": statement_currency(full_text),
        "statement_type": "chequing",
        "bank": "TD Canada Trust",
        "control": controls,
        "account_id": account_id,
        "ending_balance": 0.0
    }

    return df, statement_info



# =========================================================
# RBC BUSINESS CHEQUING
# =========================================================
def extract_rbc_business_chequing_transactions(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = "\n".join(p.get_text("text") for p in doc)

    year_m = re.search(r"to\s+\w+\s+\d{1,2},\s+(20\d{2})", full_text, re.I)
    year = int(year_m.group(1)) if year_m else datetime.now().year

    def summary(pattern, group=1, default=None):
        m = re.search(pattern, full_text, re.I)
        return m.group(group) if m else default

    credit_count = summary(r"Total\s+deposits\s*&\s*credits\s*\((\d+)\)")
    credit_total = summary(r"Total\s+deposits\s*&\s*credits\s*\(\d+\)\s*\+\s*([\d,]+\.\d{2})")
    debit_count = summary(r"Total\s+cheques\s*&\s*debits\s*\((\d+)\)")
    debit_total = summary(r"Total\s+cheques\s*&\s*debits\s*\(\d+\)\s*-\s*([\d,]+\.\d{2})")
    closing = summary(r"Closing\s+balance\s+on\s+.*?=\s*\$([\d,]+\.\d{2})")
    acct = re.search(r"Account\s+number:\s*(\d{5})\s+([\d-]+)", full_text, re.I)
    branch_id = acct.group(1) if acct else None
    account_id = acct.group(2).replace("-", "") if acct else None

    transactions, current_date, pending = [], None, []

    for page in doc:
        words = page.get_text("words")
        headers = [w for w in words if w[4].strip().lower() == "description"]
        if not headers:
            continue
        start_y = max(w[1] for w in headers) + 10
        rows = {}
        for w in words:
            if w[1] >= start_y:
                rows.setdefault(round(w[1] / 2) * 2, []).append(w)

        for y in sorted(rows):
            row = sorted(rows[y], key=lambda w: w[0])
            row_text = " ".join(w[4] for w in row).strip()
            if re.search(r"\bClosing\s+balance\b|\bAccount\s+Fees\b", row_text, re.I):
                pending = []
                break

            dm = re.match(r"^(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", row_text, re.I)
            if dm:
                current_date = datetime.strptime(
                    f"{dm.group(2)} {dm.group(1)} {year}", "%b %d %Y"
                ).strftime("%Y-%m-%d")

            debit = credit = 0.0
            for w in row:
                s = w[4].replace("$", "").replace(",", "").strip()
                if re.fullmatch(r"\d+\.\d{2}", s):
                    xr = ((w[0] + w[2]) / 2) / page.rect.width
                    if 0.50 <= xr < 0.68:
                        debit = clean_amount(s)
                    elif 0.68 <= xr < 0.82:
                        credit = clean_amount(s)

            parts = []
            for w in row:
                xr = ((w[0] + w[2]) / 2) / page.rect.width
                if 0.10 <= xr < 0.50:
                    parts.append(w[4].strip())
            desc = " ".join(parts).strip()

            if debit == 0 and credit == 0:
                if desc and "opening balance" not in desc.lower():
                    pending.append(desc)
                continue

            if current_date:
                full_desc = " ".join(pending + [desc]).strip() or "RBC transaction"
                pending = []
                transactions.append({
                    "Date": current_date, "Description": full_desc,
                    "Debit": debit, "Credit": credit
                })

    doc.close()
    df = pd.DataFrame(transactions)
    if not df.empty:
        df["Debit"] = pd.to_numeric(df["Debit"], errors="coerce").fillna(0)
        df["Credit"] = pd.to_numeric(df["Credit"], errors="coerce").fillna(0)

    controls = {
        "credit_count": int(credit_count) if credit_count else None,
        "credit_total": clean_amount(credit_total) if credit_total else None,
        "debit_count": int(debit_count) if debit_count else None,
        "debit_total": clean_amount(debit_total) if debit_total else None
    }
    return df, {
        "currency": statement_currency(full_text),
        "statement_type": "chequing", "bank": "RBC Royal Bank",
        "control": controls, "account_id": account_id,
        "branch_id": branch_id,
        "ending_balance": clean_amount(closing) if closing else None
    }


def generate_rbc_business_chequing_qbo(df, account_id, branch_id, ending_balance):
    if not isinstance(account_id, str) or not re.fullmatch(r"[0-9]+", account_id):
        raise ValueError("The RBC statement must show the full account number for QBO export.")
    if not isinstance(branch_id, str) or not re.fullmatch(r"[0-9]{5}", branch_id) or ending_balance is None:
        raise ValueError("The RBC statement must show its transit and closing balance for QBO export.")
    working_df = df.copy()
    working_df["DateObject"] = pd.to_datetime(working_df["Date"])
    first_date, last_date = working_df["DateObject"].min(), working_df["DateObject"].max()
    start_date, end_date = qbo_datetime(first_date), qbo_datetime(last_date)
    server_time = datetime.now().strftime("%Y%m%d%H%M%S")
    blocks, duplicate_counter = [], {}

    for _, row in working_df.iterrows():
        amount = float(row["Credit"]) - float(row["Debit"])
        d = row["DateObject"]
        date_text = d.strftime("%Y%m%d")
        desc = clean_qbo_text(row["Description"])
        key = (date_text, desc, f"{amount:.2f}")
        duplicate_counter[key] = duplicate_counter.get(key, 0) + 1
        fitid = create_fitid("RBCCHEQ", date_text, desc, amount, duplicate_counter[key])
        trntype = "DEBIT" if amount < 0 else "CREDIT"
        blocks.append(
            "<STMTTRN>\n"
            f"<TRNTYPE>{trntype}\n<DTPOSTED>{qbo_datetime(d)}\n"
            f"<TRNAMT>{amount:.2f}\n<FITID>{fitid}\n"
            f"<NAME>{desc[:32]}\n<MEMO>{desc[:255]}\n</STMTTRN>"
        )

    transaction_text = "\n".join(blocks)
    bal = float(ending_balance or 0)
    return f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<STATUS>
<CODE>0
<SEVERITY>INFO
</STATUS>
<DTSERVER>{server_time}
<LANGUAGE>ENG
<INTU.BID>00015
</SONRS>
</SIGNONMSGSRSV1>
<BANKMSGSRSV1>
<STMTTRNRS>
<TRNUID>1
<STATUS>
<CODE>0
<SEVERITY>INFO
</STATUS>
<STMTRS>
<CURDEF>CAD
<BANKACCTFROM>
<BANKID>026005092
<BRANCHID>{branch_id}
<ACCTID>{account_id}
<ACCTTYPE>CHECKING
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>{start_date}
<DTEND>{end_date}
{transaction_text}
</BANKTRANLIST>
<LEDGERBAL>
<BALAMT>{bal:.2f}
<DTASOF>{end_date}
</LEDGERBAL>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""



# =========================================================
# RBC BUSINESS MASTERCARD
# =========================================================

def get_rbc_mastercard_summary(full_text):
    """Read RBC Mastercard statement control totals."""

    summary = {
        "previous_balance": None,
        "payments_credits": None,
        "purchases_charges": None,
        "interest": 0.0,
        "fees": 0.0,
        "new_balance": None,
        "statement_year": datetime.now().year,
        "account_id": full_card_account_id(full_text)
    }

    period_match = re.search(
        r"STATEMENT\s+FROM\s+[A-Z]{3}\s+\d{1,2}\s+TO\s+"
        r"[A-Z]{3}\s+\d{1,2},\s+(20\d{2})",
        full_text,
        re.IGNORECASE
    )
    if period_match:
        summary["statement_year"] = int(period_match.group(1))

    patterns = {
        "previous_balance":
            r"Previous\s+Statement\s+Balance\s+\$([\d,]+\.\d{2})",
        "payments_credits":
            r"Payments\s*&\s*credits\s+-\$([\d,]+\.\d{2})",
        "purchases_charges":
            r"Purchases\s*&\s*debits\s+\$([\d,]+\.\d{2})",
        "interest":
            r"Interest\s+\$([\d,]+\.\d{2})",
        "fees":
            r"Fees\s+\$([\d,]+\.\d{2})",
        "new_balance":
            r"NEW\s+BALANCE\s+\$([\d,]+\.\d{2})"
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            summary[key] = clean_amount(match.group(1))

    return summary


def extract_rbc_mastercard_transactions(pdf_bytes):
    """
    Parse RBC Business Cash Back Mastercard statements.

    RBC transaction rows contain:
    transaction date | posting date | description | amount.

    Purchases are positive on the PDF and become Debit values in the app.
    Payments are printed as negative amounts and become Credit values.
    """

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    full_text = "\n".join(
        page.get_text("text") for page in doc
    )

    summary = get_rbc_mastercard_summary(full_text)
    statement_year = summary["statement_year"]

    month_numbers = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
        "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
        "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
    }

    transactions = []

    for page in doc:

        rows = {}

        for word in page.get_text("words"):
            x0, y0, x1, y1, text = word[:5]

            # Transaction table is on the left side of RBC card pages.
            if x0 >= 370:
                continue

            row_key = round(y0, 1)
            rows.setdefault(row_key, []).append(word)

        for row_y in sorted(rows):

            row = sorted(
                rows[row_y],
                key=lambda item: item[0]
            )

            texts = [
                item[4].strip()
                for item in row
                if item[4].strip()
            ]

            if len(texts) < 5:
                continue

            # A real RBC transaction row begins:
            # APR 14 APR 16 ...
            if (
                texts[0].upper() not in month_numbers
                or not re.fullmatch(r"\d{1,2}", texts[1])
                or texts[2].upper() not in month_numbers
                or not re.fullmatch(r"\d{1,2}", texts[3])
            ):
                continue

            amount = None

            for word in row:
                # A dollar value in the description is not the transaction amount.
                if word[0] < 305:
                    continue
                text = word[4].replace(",", "").strip()

                if re.fullmatch(
                    r"-?\$\d+(?:\.\d{2})",
                    text
                ):
                    amount = float(
                        text.replace("$", "")
                    )

            if amount is None:
                continue

            transaction_month = month_numbers[
                texts[0].upper()
            ]
            transaction_day = int(texts[1])

            # Handle statements crossing Dec/Jan.
            transaction_year = statement_year
            if (
                transaction_month == 12
                and
                re.search(
                    r"TO\s+JAN\s+\d{1,2},\s+"
                    + str(statement_year),
                    full_text,
                    re.IGNORECASE
                )
            ):
                transaction_year -= 1

            date_object = datetime(
                transaction_year,
                transaction_month,
                transaction_day
            )

            # Description words sit between posting date and amount.
            description_words = []

            for word in row:
                x0, y0, x1, y1, text = word[:5]

                if 120 <= x0 < 305:
                    description_words.append(
                        text.strip()
                    )

            description = " ".join(
                description_words
            ).strip()

            if not description:
                description = "RBC Mastercard transaction"

            # PDF convention:
            # positive = purchase/debit
            # negative = payment/credit
            if amount < 0:
                debit = 0.0
                credit = abs(amount)
            else:
                debit = amount
                credit = 0.0

            transactions.append({
                "Date": date_object.strftime("%Y-%m-%d"),
                "Description": description,
                "Debit": debit,
                "Credit": credit
            })

    doc.close()

    df = pd.DataFrame(transactions)

    if not df.empty:
        df["Debit"] = pd.to_numeric(
            df["Debit"],
            errors="coerce"
        ).fillna(0.0)

        df["Credit"] = pd.to_numeric(
            df["Credit"],
            errors="coerce"
        ).fillna(0.0)

        df = df.sort_values(
            by=["Date"],
            kind="stable"
        ).reset_index(drop=True)

    statement_info = {
        "currency": statement_currency(full_text),
        "statement_type": "credit_card",
        "bank": "RBC Royal Bank",
        "account_id": summary["account_id"],
        "summary": summary
    }

    return df, statement_info


def generate_rbc_mastercard_qbo(
    df,
    account_id,
    new_balance
):
    """
    Generate RBC Mastercard QuickBooks Desktop Web Connect QBO.

    Structure mirrors the genuine RBC QBO supplied for this account:
    INTU.BID 00015
    CREDITCARDMSGSRSV1 / CCSTMTRS
    CCACCTFROM
    ACCTID 10000003
    """

    working_df = df.copy()
    working_df["DateObject"] = pd.to_datetime(
        working_df["Date"]
    )

    first_date = working_df["DateObject"].min()
    last_date = working_df["DateObject"].max()

    def rbc_ofx_dt(value):
        return (
            value.strftime("%Y%m%d")
            + "130000.000[-4]"
        )

    start_date = rbc_ofx_dt(first_date)
    end_date = rbc_ofx_dt(last_date)

    server_time = (
        datetime.now().strftime("%Y%m%d%H%M%S")
        + ".000[-4]"
    )

    transaction_blocks = []
    duplicate_counter = {}

    for _, row in working_df.iterrows():

        debit = float(row["Debit"])
        credit = float(row["Credit"])

        # Credit-card OFX:
        # purchase = negative
        # payment/refund = positive
        amount = credit - debit

        date_object = row["DateObject"]
        date_text = date_object.strftime("%Y%m%d")
        description = clean_qbo_text(
            row["Description"]
        )

        duplicate_key = (
            date_text,
            description,
            f"{amount:.2f}"
        )

        duplicate_counter[duplicate_key] = (
            duplicate_counter.get(
                duplicate_key,
                0
            )
            + 1
        )

        fitid = create_fitid(
            "RBCMC",
            date_text,
            description,
            amount,
            duplicate_counter[
                duplicate_key
            ]
        )

        trntype = (
            "DEBIT"
            if amount < 0
            else "CREDIT"
        )

        transaction_blocks.append(
            "<STMTTRN>\n"
            f"<TRNTYPE>{trntype}\n"
            f"<DTPOSTED>{rbc_ofx_dt(date_object)}\n"
            f"<TRNAMT>{amount:.2f}\n"
            f"<FITID>{fitid}\n"
            f"<NAME>{description[:32]}\n"
            f"<MEMO>{description[:255]}\n"
            "</STMTTRN>"
        )

    transactions_text = "\n".join(
        transaction_blocks
    )

    # Genuine RBC Mastercard QBO uses 0.00 here.
    ledger_balance = 0.00

    return f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<STATUS>
<CODE>0
<SEVERITY>INFO
<MESSAGE>OK
</STATUS>
<DTSERVER>{server_time}
<LANGUAGE>ENG
<INTU.BID>00015
</SONRS>
</SIGNONMSGSRSV1>
<CREDITCARDMSGSRSV1>
<CCSTMTTRNRS>
<TRNUID>0
<STATUS>
<CODE>0
<SEVERITY>INFO
<MESSAGE>OK
</STATUS>
<CCSTMTRS>
<CURDEF>CAD
<CCACCTFROM>
<ACCTID>{account_id}
</CCACCTFROM>
<BANKTRANLIST>
<DTSTART>{start_date}
<DTEND>{end_date}
{transactions_text}
</BANKTRANLIST>
<LEDGERBAL>
<BALAMT>{ledger_balance:.2f}
<DTASOF>{end_date}
</LEDGERBAL>
</CCSTMTRS>
</CCSTMTTRNRS>
</CREDITCARDMSGSRSV1>
</OFX>
"""



# =========================================================
# BMO BUSINESS CHEQUING + BUSINESS MASTERCARD
# =========================================================

def get_bmo_chequing_summary(full_text):
    result = {
        "statement_year": datetime.now().year,
        "opening_balance": None,
        "closing_balance": None,
        "debit_total": None,
        "credit_total": None,
        "debit_count": None,
        "credit_count": None,
        "account_id": None
    }

    period = re.search(
        r"period\s+ending\s+([A-Za-z]+)\s+\d{1,2},\s+(20\d{2})",
        full_text,
        re.IGNORECASE
    )
    if period:
        result["statement_year"] = int(period.group(2))

    summary_row = re.search(
        r"#\s*\d{4}\s+[\d-]+\s+([\d,]+\.\d{2})\s+"
        r"([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})",
        full_text
    )
    if summary_row:
        result["opening_balance"] = clean_amount(summary_row.group(1))
        result["debit_total"] = clean_amount(summary_row.group(2))
        result["credit_total"] = clean_amount(summary_row.group(3))
        result["closing_balance"] = clean_amount(summary_row.group(4))

    items = re.search(
        r"Number\s+of\s+items\s+processed.*?(\d+)",
        full_text,
        re.IGNORECASE
    )
    if items:
        total_items = int(items.group(1))
        # The statement does not split the item count by debit/credit.
        result["item_count"] = total_items

    return result


def extract_bmo_business_chequing_transactions(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = "\n".join(page.get_text("text") for page in doc)
    info = get_bmo_chequing_summary(full_text)

    transactions = []
    month_map = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
        "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
        "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
    }

    for page in doc:
        rows = {}
        for word in page.get_text("words"):
            x0, y0, x1, y1, text = word[:5]
            row_key = round(y0, 1)
            rows.setdefault(row_key, []).append(word)

        for row_y in sorted(rows):
            row = sorted(rows[row_y], key=lambda w: w[0])
            texts = [w[4].strip() for w in row if w[4].strip()]

            if len(texts) < 3:
                continue

            if texts[0] not in month_map or not re.fullmatch(r"\d{1,2}", texts[1]):
                continue

            row_text = " ".join(texts)
            if "Opening balance" in row_text or "Closing totals" in row_text:
                continue

            debit = 0.0
            credit = 0.0

            for w in row:
                x0, y0, x1, y1, text = w[:5]
                cleaned = text.replace("$", "").replace(",", "").strip()
                if not re.fullmatch(r"\d+\.\d{2}", cleaned):
                    continue
                amount = float(cleaned)

                # BMO statement columns:
                # debit around x=350, credit around x=440, balance around x=515.
                if 300 <= x0 < 390:
                    debit = amount
                elif 390 <= x0 < 485:
                    credit = amount

            if debit == 0 and credit == 0:
                continue

            description = " ".join(
                w[4].strip()
                for w in row
                if 95 <= w[0] < 300
            ).strip()

            month = month_map[texts[0]]
            day = int(texts[1])
            year = info["statement_year"]

            date_obj = datetime(year, month, day)

            transactions.append({
                "Date": date_obj.strftime("%Y-%m-%d"),
                "Description": description or "BMO transaction",
                "Debit": debit,
                "Credit": credit
            })

    doc.close()
    df = pd.DataFrame(transactions)

    if not df.empty:
        df["Debit"] = pd.to_numeric(df["Debit"], errors="coerce").fillna(0.0)
        df["Credit"] = pd.to_numeric(df["Credit"], errors="coerce").fillna(0.0)

    controls = {key: info.get(key) for key in (
        "debit_count", "credit_count", "debit_total", "credit_total", "item_count"
    )}

    return df, {
        "currency": statement_currency(full_text),
        "statement_type": "chequing",
        "bank": "BMO Bank of Montreal",
        "control": controls,
        "account_id": info["account_id"],
        "opening_balance": info["opening_balance"],
        "ending_balance": info["closing_balance"],
    }


def reconcile_dedicated_deposit(frame, info):
    """Compare extracted transactions with the statement's printed controls."""
    if info.get("td_easyweb"):
        return reconcile_universal_transactions(frame, info)
    if info.get("bank") in ("BMO Bank of Montreal", "CIBC"):
        return reconcile_deposit_balances(frame, info)
    control = info.get("control", {})
    rows = []
    for column, key, label in (
        ("Debit", "debit", "Debits"),
        ("Credit", "credit", "Credits"),
    ):
        amounts = frame[column]
        rows.extend([
            (f"{label} (count)", control.get(f"{key}_count"), int((amounts > 0).sum()), "n"),
            (f"{label} (total)", control.get(f"{key}_total"), round(float(amounts.sum()), 2), "$"),
        ])
    dates = pd.to_datetime(frame["Date"], format="%Y-%m-%d", errors="coerce")
    return rows, bool(valid_transaction_rows(frame, dates) and all(
        expected == actual for _, expected, actual, _ in rows
    ))


def reconcile_deposit_balances(frame, info):
    control = info["control"]
    printed = {
        "opening": info.get("opening_balance"),
        "closing": info.get("ending_balance"),
        "debit": control.get("debit_total"),
        "credit": control.get("credit_total"),
    }
    if any(value is None for value in printed.values()):
        return [], False
    if control.get("item_count") is not None:
        printed["transaction_count"] = control["item_count"]
    return reconcile_universal_transactions(frame, {
        "control": printed, "running_balances": info.get("running_balances", []),
    })



def get_bmo_credit_card_summary(full_text):
    summary = {
        "previous_balance": None,
        "payments_credits": None,
        "purchases_charges": None,
        "interest": 0.0,
        "fees": 0.0,
        "new_balance": None,
        "statement_year": datetime.now().year,
        "account_id": full_card_account_id(full_text)
    }

    patterns = {
        "previous_balance":
            r"Previous\s+total\s+balance[^\n\r]*?\$?\s*([\d,]+\.\d{2})",
        "payments_credits":
            r"Payments\s+and\s+credits\s+-?\$?([\d,]+\.\d{2})",
        "purchases_charges":
            r"Purchases\s+and\s+other\s+charges\s+\$?([\d,]+\.\d{2})",
        "interest":
            r"Total\s+interest\s+charges\s+\+?\$?([\d,]+\.\d{2})",
        "fees":
            r"Fees\s+\$?([\d,]+\.\d{2})",
        "new_balance":
            r"(?m)^[ \t]*Total\s+balance\s+\$([\d,]+\.\d{2})"
    }

    for key, pattern in patterns.items():
        m = re.search(pattern, full_text, re.IGNORECASE)
        if m:
            summary[key] = clean_amount(m.group(1))

    # BMO fallback: PDF text extraction can split the previous-balance line
    # differently from the other summary lines.
    if summary["previous_balance"] is None:
        m = re.search(
            r"Previous\s+total\s+balance[\s\S]{0,80}?([0-9]{1,3}(?:,[0-9]{3})*\.\d{2})",
            full_text,
            re.IGNORECASE
        )
        if m:
            summary["previous_balance"] = clean_amount(m.group(1))

    year_match = re.search(
        r"Statement\s+date\s+([A-Za-z]{3})\.?\s+\d{1,2},\s+(20\d{2})",
        full_text,
        re.IGNORECASE
    )
    if year_match:
        summary["statement_year"] = int(year_match.group(2))
        try:
            summary["statement_month"] = datetime.strptime(year_match.group(1), "%b").month
        except ValueError:
            pass

    return summary


def extract_bmo_credit_card_transactions(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = "\n".join(page.get_text("text") for page in doc)
    summary = get_bmo_credit_card_summary(full_text)

    month_map = {
        "Jan.": 1, "Feb.": 2, "Mar.": 3, "Apr.": 4,
        "May": 5, "Jun.": 6, "Jul.": 7, "Aug.": 8,
        "Sep.": 9, "Oct.": 10, "Nov.": 11, "Dec.": 12,
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
        "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9,
        "Oct": 10, "Nov": 11, "Dec": 12
    }

    transactions = []

    for page in doc:
        rows = {}
        for word in page.get_text("words"):
            row_key = round(word[1], 1)
            rows.setdefault(row_key, []).append(word)

        for row_y in sorted(rows):
            row = sorted(rows[row_y], key=lambda w: w[0])
            texts = [w[4].strip() for w in row if w[4].strip()]

            if len(texts) < 5:
                continue

            if (
                texts[0] not in month_map
                or not re.fullmatch(r"\d{1,2}", texts[1])
                or texts[2] not in month_map
                or not re.fullmatch(r"\d{1,2}", texts[3])
            ):
                continue

            amount = None
            for index, w in enumerate(row):
                if w[0] >= 350:
                    cleaned = w[4].replace("$", "").replace(",", "").strip()
                    if re.fullmatch(r"-?\d+\.\d{2}", cleaned):
                        amount = float(cleaned)
                        if index + 1 < len(row) and row[index + 1][4].upper() == "CR":
                            amount = -abs(amount)

            if amount is None:
                continue

            description = " ".join(
                w[4].strip()
                for w in row
                if 130 <= w[0] < 350
            ).strip()

            month = month_map[texts[0]]
            day = int(texts[1])
            year = summary["statement_year"] - int(month > summary.get("statement_month", 12))

            date_obj = datetime(year, month, day)

            # BMO statement transaction amounts are charges unless printed negative.
            if amount < 0:
                debit = 0.0
                credit = abs(amount)
            else:
                debit = amount
                credit = 0.0

            transactions.append({
                "Date": date_obj.strftime("%Y-%m-%d"),
                "Description": description or "BMO Mastercard transaction",
                "Debit": debit,
                "Credit": credit
            })

    doc.close()
    df = pd.DataFrame(transactions)

    if not df.empty:
        df["Debit"] = pd.to_numeric(df["Debit"], errors="coerce").fillna(0.0)
        df["Credit"] = pd.to_numeric(df["Credit"], errors="coerce").fillna(0.0)

    return df, {
        "currency": statement_currency(full_text),
        "statement_type": "credit_card",
        "bank": "BMO Bank of Montreal",
        "account_id": summary["account_id"],
        "summary": summary
    }


def generate_bmo_chequing_qbo(df, account_id, ending_balance):
    working_df = df.copy()
    working_df["DateObject"] = pd.to_datetime(working_df["Date"])

    def bmo_dt(value):
        return value.strftime("%Y%m%d") + "000000.000[-5:EDT]"

    now_text = datetime.now().strftime("%Y%m%d%H%M%S") + ".000[-5:EDT]"
    first_date = working_df["DateObject"].min()
    last_date = working_df["DateObject"].max()

    blocks = []
    duplicate_counter = {}

    for _, row in working_df.iterrows():
        amount = float(row["Credit"]) - float(row["Debit"])
        date_obj = row["DateObject"]
        desc = clean_qbo_text(row["Description"])
        key = (date_obj.strftime("%Y%m%d"), desc, f"{amount:.2f}")
        duplicate_counter[key] = duplicate_counter.get(key, 0) + 1
        fitid = create_fitid(
            "BMOCHEQ", key[0], desc, amount, duplicate_counter[key]
        )
        trntype = "DEBIT" if amount < 0 else "CREDIT"

        blocks.append(
            "<STMTTRN>\n"
            f"<TRNTYPE>{trntype}\n"
            f"<DTPOSTED>{bmo_dt(date_obj)}\n"
            f"<TRNAMT>{amount:.2f}\n"
            f"<FITID>{fitid}\n"
            f"<NAME>{desc[:32]}\n"
            f"<MEMO>{desc[:255]}\n"
            "</STMTTRN>"
        )

    tx_text = "\n".join(blocks)
    bal = float(ending_balance or 0.0)

    return f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<STATUS>
<CODE>0
<SEVERITY>INFO
<MESSAGE>OK
</STATUS>
<DTSERVER>{now_text}
<LANGUAGE>ENG
<INTU.BID>00001
</SONRS>
</SIGNONMSGSRSV1>
<BANKMSGSRSV1>
<STMTTRNRS>
<TRNUID>1
<STATUS>
<CODE>0
<SEVERITY>INFO
<MESSAGE>OK
</STATUS>
<STMTRS>
<CURDEF>CAD
<BANKACCTFROM>
<BANKID>200000100
<ACCTID>{account_id}
<ACCTTYPE>CHECKING
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>{bmo_dt(first_date)}
<DTEND>{bmo_dt(last_date)}
{tx_text}
</BANKTRANLIST>
<LEDGERBAL>
<BALAMT>{bal:.2f}
<DTASOF>{bmo_dt(last_date)}
</LEDGERBAL>
<AVAILBAL>
<BALAMT>{bal:.2f}
<DTASOF>{bmo_dt(last_date)}
</AVAILBAL>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""


def generate_bmo_credit_card_qbo(df, account_id, new_balance):
    working_df = df.copy()
    working_df["DateObject"] = pd.to_datetime(working_df["Date"])

    def bmo_dt(value):
        return value.strftime("%Y%m%d") + "000000.000[-5:EDT]"

    now_text = datetime.now().strftime("%Y%m%d%H%M%S") + ".000[-5:EDT]"
    first_date = working_df["DateObject"].min()
    last_date = working_df["DateObject"].max()

    blocks = []
    duplicate_counter = {}

    for _, row in working_df.iterrows():
        amount = float(row["Credit"]) - float(row["Debit"])
        date_obj = row["DateObject"]
        desc = clean_qbo_text(row["Description"])
        key = (date_obj.strftime("%Y%m%d"), desc, f"{amount:.2f}")
        duplicate_counter[key] = duplicate_counter.get(key, 0) + 1
        fitid = create_fitid(
            "BMOCC", key[0], desc, amount, duplicate_counter[key]
        )
        trntype = "DEBIT" if amount < 0 else "CREDIT"

        blocks.append(
            "<STMTTRN>\n"
            f"<TRNTYPE>{trntype}\n"
            f"<DTPOSTED>{bmo_dt(date_obj)}\n"
            f"<TRNAMT>{amount:.2f}\n"
            f"<FITID>{fitid}\n"
            f"<NAME>{desc[:32]}\n"
            "</STMTTRN>"
        )

    tx_text = "\n".join(blocks)

    # Genuine BMO credit-card QBO reports liability balance as negative.
    bal = -float(new_balance or 0.0)

    return f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE
<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<STATUS>
<CODE>0
<SEVERITY>INFO
<MESSAGE>OK
</STATUS>
<DTSERVER>{now_text}
<LANGUAGE>ENG
<INTU.BID>00017
</SONRS>
</SIGNONMSGSRSV1>
<CREDITCARDMSGSRSV1>
<CCSTMTTRNRS>
<TRNUID>1
<STATUS>
<CODE>0
<SEVERITY>INFO
<MESSAGE>OK
</STATUS>
<CCSTMTRS>
<CURDEF>CAD
<CCACCTFROM>
<ACCTID>{account_id}
</CCACCTFROM>
<BANKTRANLIST>
<DTSTART>{bmo_dt(first_date)}
<DTEND>{bmo_dt(last_date)}
{tx_text}
</BANKTRANLIST>
<LEDGERBAL>
<BALAMT>{bal:.2f}
<DTASOF>{now_text}
</LEDGERBAL>
<AVAILBAL>
<BALAMT>{bal:.2f}
<DTASOF>{now_text}
</AVAILBAL>
</CCSTMTRS>
</CCSTMTTRNRS>
</CREDITCARDMSGSRSV1>
</OFX>
"""



# =========================================================
# SCOTIABANK BUSINESS CHEQUING
# =========================================================

def get_scotiabank_business_chequing_summary(full_text):
    result = {
        "statement_year": datetime.now().year,
        "debit_count": None,
        "debit_total": None,
        "credit_count": None,
        "credit_total": None,
        "ending_balance": None,
        "account_id": None
    }

    period_match = re.search(
        r"Business\s+Account\s+\d+\s+\d+\s+\d+\s+"
        r"[A-Za-z]+\s+\d{1,2}\s+(20\d{2})\s+"
        r"[A-Za-z]+\s+\d{1,2}\s+(20\d{2})",
        full_text,
        re.IGNORECASE
    )
    if period_match:
        result["statement_year"] = int(period_match.group(2))

    controls = re.search(
        r"No\.\s+of\s+Debits\s+Total\s+Amount\s*-\s*Debits\s+"
        r"No\.\s+of\s+Credits\s+Total\s+Amount\s*-\s*Credits\s+"
        r"(\d+)\s+\$([\d,]+\.\d{2})\s+(\d+)\s+\$([\d,]+\.\d{2})",
        full_text,
        re.IGNORECASE
    )
    if controls:
        result["debit_count"] = int(controls.group(1))
        result["debit_total"] = clean_amount(controls.group(2))
        result["credit_count"] = int(controls.group(3))
        result["credit_total"] = clean_amount(controls.group(4))

    # Last balance on a real transaction row is the statement ending balance.
    balance_matches = re.findall(
        r"\d{2}/\d{2}/20\d{2}\s+.+?\s+"
        r"([\d,]+\.\d{2}-?)\s*$",
        full_text,
        re.MULTILINE
    )
    if balance_matches:
        raw = balance_matches[-1]
        negative = raw.endswith("-")
        value = clean_amount(raw.rstrip("-"))
        result["ending_balance"] = -value if negative else value

    return result


def extract_scotiabank_business_chequing_transactions(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = "\n".join(page.get_text("text") for page in doc)
    info = get_scotiabank_business_chequing_summary(full_text)

    transactions = []

    for page in doc:
        rows = {}
        for word in page.get_text("words"):
            row_key = round(word[1], 1)
            rows.setdefault(row_key, []).append(word)

        for row_y in sorted(rows):
            row = sorted(rows[row_y], key=lambda w: w[0])
            texts = [w[4].strip() for w in row if w[4].strip()]
            if len(texts) < 3:
                continue

            date_match = re.fullmatch(
                r"\d{2}/\d{2}/20\d{2}",
                texts[0]
            )
            if not date_match:
                continue

            row_text = " ".join(texts)
            if "BALANCE FORWARD" in row_text.upper():
                continue

            debit = 0.0
            credit = 0.0

            # Use column position rather than relying on text order.
            for w in row:
                x0, y0, x1, y1, text = w[:5]
                cleaned = text.replace("$", "").replace(",", "").replace("-", "").strip()

                if not re.fullmatch(r"\d+\.\d{2}", cleaned):
                    continue

                amount = float(cleaned)
                x_ratio = ((x0 + x1) / 2) / page.rect.width

                # Scotiabank PDF table:
                # Description | Withdrawals/Debits | Deposits/Credits | Balance
                if 0.48 <= x_ratio < 0.66:
                    debit = amount
                elif 0.66 <= x_ratio < 0.82:
                    credit = amount

            if debit == 0 and credit == 0:
                continue

            description = " ".join(
                w[4].strip()
                for w in row
                if 0.15 <= (((w[0] + w[2]) / 2) / page.rect.width) < 0.48
            ).strip()

            date_obj = datetime.strptime(texts[0], "%m/%d/%Y")

            transactions.append({
                "Date": date_obj.strftime("%Y-%m-%d"),
                "Description": description or "Scotiabank transaction",
                "Debit": debit,
                "Credit": credit
            })

    doc.close()

    df = pd.DataFrame(transactions)

    if not df.empty:
        df["Debit"] = pd.to_numeric(df["Debit"], errors="coerce").fillna(0.0)
        df["Credit"] = pd.to_numeric(df["Credit"], errors="coerce").fillna(0.0)
        df = df.reset_index(drop=True)

    controls = {
        "debit_count": info["debit_count"],
        "debit_total": info["debit_total"],
        "credit_count": info["credit_count"],
        "credit_total": info["credit_total"]
    }

    return df, {
        "currency": statement_currency(full_text),
        "statement_type": "chequing",
        "bank": "Scotiabank",
        "control": controls,
        "account_id": info["account_id"],
        "ending_balance": info["ending_balance"]
    }


def generate_scotiabank_chequing_qbo(df, account_id, ending_balance):
    """
    Scotiabank Business Chequing QBO.
    Institution/account structure mirrors the genuine QBO supplied by user.
    """
    working_df = df.copy()
    working_df["DateObject"] = pd.to_datetime(working_df["Date"])

    def scotia_dt(value):
        return value.strftime("%Y%m%d") + "120000.000[-5:EST]"

    first_date = working_df["DateObject"].min()
    last_date = working_df["DateObject"].max()
    server_time = datetime.now().strftime("%Y%m%d%H%M%S") + ".000[-5:EST]"

    blocks = []
    duplicate_counter = {}

    for _, row in working_df.iterrows():
        debit = float(row["Debit"])
        credit = float(row["Credit"])
        amount = credit - debit
        date_obj = row["DateObject"]
        date_text = date_obj.strftime("%Y%m%d")
        desc = clean_qbo_text(row["Description"])

        key = (date_text, desc, f"{amount:.2f}")
        duplicate_counter[key] = duplicate_counter.get(key, 0) + 1

        fitid = create_fitid(
            "SCOTIACHEQ",
            date_text,
            desc,
            amount,
            duplicate_counter[key]
        )

        trntype = "DEBIT" if amount < 0 else "CREDIT"

        blocks.append(
            "<STMTTRN>\n"
            f"<TRNTYPE>{trntype}\n"
            f"<DTPOSTED>{scotia_dt(date_obj)}\n"
            f"<TRNAMT>{amount:.2f}\n"
            f"<FITID>{fitid}\n"
            f"<NAME>{desc[:32]}\n"
            f"<MEMO>{desc[:255]}\n"
            "</STMTTRN>"
        )

    transaction_text = "\n".join(blocks)
    balance = float(ending_balance or 0.0)

    return f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<STATUS>
<CODE>0
<SEVERITY>INFO
<MESSAGE>OK
</STATUS>
<DTSERVER>{server_time}
<LANGUAGE>ENG
<INTU.BID>00025
</SONRS>
</SIGNONMSGSRSV1>
<BANKMSGSRSV1>
<STMTTRNRS>
<TRNUID>1
<STATUS>
<CODE>0
<SEVERITY>INFO
<MESSAGE>OK
</STATUS>
<STMTRS>
<CURDEF>CAD
<BANKACCTFROM>
<BANKID>170000100
<ACCTID>{account_id}
<ACCTTYPE>CHECKING
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>{scotia_dt(first_date)}
<DTEND>{scotia_dt(last_date)}
{transaction_text}
</BANKTRANLIST>
<LEDGERBAL>
<BALAMT>{balance:.2f}
<DTASOF>{scotia_dt(last_date)}
</LEDGERBAL>
<AVAILBAL>
<BALAMT>{balance:.2f}
<DTASOF>{scotia_dt(last_date)}
</AVAILBAL>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""


# =========================================================
# CREDIT CARD SUMMARY
# =========================================================

def get_credit_card_summary(
    full_text
):

    summary = {
        "previous_balance": None,
        "payments_credits": None,
        "purchases_charges": None,
        "interest": None,
        "fees": None,
        "new_balance": None
    }

    patterns = {

        "previous_balance": [
            r"Previous\s+Balance[\s:$]*"
            r"\$?\s*([\d,]+\.\d{2})"
        ],

        "payments_credits": [
            r"Payments\s*&\s*Credits[\s:$-]*"
            r"\$?\s*([\d,]+\.\d{2})",

            r"Payments\s+and\s+Credits[\s:$-]*"
            r"\$?\s*([\d,]+\.\d{2})"
        ],

        "purchases_charges": [
            r"Purchases\s*&\s*Other\s+Charges"
            r"[\s:$]*\$?\s*([\d,]+\.\d{2})",

            r"Purchases\s+and\s+Other\s+Charges"
            r"[\s:$]*\$?\s*([\d,]+\.\d{2})"
        ],

        "interest": [
            r"Interest[\s:$]*"
            r"\$?\s*([\d,]+\.\d{2})"
        ],

        "fees": [
            r"Fees[\s:$]*"
            r"\$?\s*([\d,]+\.\d{2})"
        ],

        "new_balance": [
            r"NEW\s+BALANCE[\s:$]*"
            r"\$?\s*([\d,]+\.\d{2})"
        ]
    }

    for key, pattern_list in patterns.items():

        for pattern in pattern_list:

            match = re.search(
                pattern,
                full_text,
                re.IGNORECASE
            )

            if match:

                summary[key] = (
                    clean_amount(
                        match.group(1)
                    )
                )

                break

    # -----------------------------------------------------
    # If TD splits Purchases & Other Charges across PDF
    # blocks, calculate it from the statement equation.
    # -----------------------------------------------------

    if (
        summary["purchases_charges"]
        is None
        and
        summary["previous_balance"]
        is not None
        and
        summary["payments_credits"]
        is not None
        and
        summary["new_balance"]
        is not None
    ):

        interest = (
            summary["interest"]
            or 0.0
        )

        fees = (
            summary["fees"]
            or 0.0
        )

        summary["purchases_derived"] = True
        summary["purchases_charges"] = round(

            summary["new_balance"]

            -

            summary["previous_balance"]

            +

            summary["payments_credits"]

            -

            interest

            -

            fees,

            2
        )

    return summary


# =========================================================
# CREDIT CARD HELPERS
# =========================================================

def get_td_card_statement_year_month(text):

    match = re.search(
        r"STATEMENT DATE:\s*"
        r"(January|February|March|April|May|June|July|"
        r"August|September|October|November|December)"
        r"\s+\d{1,2},\s*(20\d{2})",
        text,
        re.IGNORECASE
    )

    if match:
        return int(match.group(2)), datetime.strptime(match.group(1), "%B").month

    match = re.search(
        r"\b(20\d{2})\b",
        text
    )

    if match:
        return int(match.group(1)), 12

    return datetime.now().year, 12


def full_card_account_id(text):
    """Read a full card ID only from an explicit account-number label."""
    candidates = set()
    for match in re.finditer(r"^\s*(?:account|card)\s+number\s*:?\s*([0-9][0-9 -]*)$",
                             text, re.IGNORECASE | re.MULTILINE):
        digits = re.sub(r"[ -]", "", match.group(1))
        if 13 <= len(digits) <= 19:
            candidates.add(digits)
    return next(iter(candidates)) if len(candidates) == 1 else None


# =========================================================
# TD CREDIT CARD TRANSACTION PARSER
# =========================================================

def extract_td_credit_card_transactions(
    pdf_bytes
):

    doc = fitz.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    full_text = ""

    for page in doc:
        full_text += page.get_text("text") + "\n"

    statement_year, statement_month = get_td_card_statement_year_month(full_text)

    summary = (
        get_credit_card_summary(
            full_text
        )
    )

    account_id = (
        full_card_account_id(
            full_text
        )
    )

    transactions = []

    valid_months = {
        "JAN", "FEB", "MAR", "APR",
        "MAY", "JUN", "JUL", "AUG",
        "SEP", "OCT", "NOV", "DEC"
    }

    for page in doc:

        words = page.get_text("words")

        if not words:
            continue

        for date_word in words:

            x0, y0, x1, y1, month_text = (
                date_word[:5]
            )

            month_text = (
                month_text
                .strip()
                .upper()
            )

            if month_text not in valid_months:
                continue

            if not (
                40 <= x0 <= 60
            ):
                continue

            date_center_y = (
                y0 + y1
            ) / 2

            row_words = []

            for word in words:

                wx0, wy0, wx1, wy1, text = (
                    word[:5]
                )

                word_center_y = (
                    wy0 + wy1
                ) / 2

                if abs(
                    word_center_y
                    -
                    date_center_y
                ) <= 3.5:

                    if wx0 < 360:

                        row_words.append(
                            word
                        )

            row_words.sort(
                key=lambda item: item[0]
            )

            day = None

            for word in row_words:

                wx0, wy0, wx1, wy1, text = (
                    word[:5]
                )

                if (
                    55 <= wx0 <= 80
                    and
                    re.fullmatch(
                        r"\d{1,2}",
                        text.strip()
                    )
                ):

                    day = int(
                        text.strip()
                    )

                    break

            if day is None:
                continue

            amount_text = None

            for word in row_words:

                wx0, wy0, wx1, wy1, text = (
                    word[:5]
                )

                cleaned = text.strip()

                if (
                    295 <= wx0 <= 355
                    and
                    re.fullmatch(
                        r"-?\$[\d,]+\.\d{2}",
                        cleaned
                    )
                ):

                    amount_text = cleaned

                    break

            if amount_text is None:
                continue

            description_parts = []

            for word in row_words:

                wx0, wy0, wx1, wy1, text = (
                    word[:5]
                )

                if (
                    130 <= wx0 < 295
                ):

                    description_parts.append(
                        text.strip()
                    )

            description = " ".join(
                description_parts
            ).strip()

            if not description:
                continue

            numeric_amount = (
                clean_amount(
                    amount_text
                )
            )

            debit = 0.0
            credit = 0.0

            if numeric_amount < 0:

                credit = abs(
                    numeric_amount
                )

            else:

                debit = numeric_amount

            transaction_date = parse_statement_month_day(f"{month_text} {day}", statement_year, statement_month)

            transactions.append({
                "Date": transaction_date,
                "Description": description,
                "Debit": debit,
                "Credit": credit
            })

    doc.close()

    df = pd.DataFrame(
        transactions
    )

    if not df.empty:

        df["Debit"] = pd.to_numeric(
            df["Debit"],
            errors="coerce"
        ).fillna(0)

        df["Credit"] = pd.to_numeric(
            df["Credit"],
            errors="coerce"
        ).fillna(0)

    statement_info = {
        "currency": statement_currency(full_text),
        "statement_type": "credit_card",
        "summary": summary,
        "account_id": account_id
    }

    return df, statement_info


# =========================================================
# QUICKBOOKS ONLINE CSV
# =========================================================

def reconcile_statement(frame, info):
    if info.get("universal"):
        return reconcile_universal_transactions(frame, info)
    if info["statement_type"] == "chequing":
        return reconcile_dedicated_deposit(frame, info)
    return reconcile_credit_card(frame, info)


def generate_statement_iif(frame, info, register_account, clearing_account):
    """Create a transaction-only IIF from reconciled deposit or card rows."""
    statement_type = info.get("statement_type")
    if statement_type not in ("chequing", "credit_card"):
        raise ValueError("IIF requires a bank or credit card statement.")
    if info.get("currency") not in (None, "CAD"):
        raise ValueError("IIF currently supports CAD statements.")
    if not reconcile_statement(frame, info)[1]:
        raise ValueError("Reconcile the statement before exporting IIF.")

    register_account = register_account.strip()
    clearing_account = clearing_account.strip()
    for name in (register_account, clearing_account):
        if not re.fullmatch(r'[ -!#-~]+', name):
            raise ValueError("Enter both QuickBooks account names using printable ASCII without double quotes.")
    if register_account.casefold() == clearing_account.casefold():
        raise ValueError("Choose a different account for the clearing entry.")

    is_card = statement_type == "credit_card"
    columns = "TRNSTYPE\tDATE\tACCNT\tAMOUNT\tMEMO"
    cleared_field = "" if is_card else "\tN"
    if not is_card:
        columns += "\tCLEAR"
    lines = [f"!TRNS\t{columns}", f"!SPL\t{columns}", "!ENDTRNS"]
    for number, row in enumerate(frame.itertuples(index=False), 1):
        date = datetime.strptime(row.Date, "%Y-%m-%d").strftime("%m/%d/%Y")
        memo = " ".join(row.Description.split()).replace('"', "'")
        if not re.fullmatch(r"[ -~]+", memo):
            raise ValueError(f"Transaction {number} contains characters outside ASCII. Edit its description for IIF export.")
        amount = row.Credit - row.Debit
        if is_card:
            kind = "GENERAL JOURNAL"
        else:
            kind = "DEPOSIT" if amount > 0 else "CHECK"
        lines.extend((
            f"TRNS\t{kind}\t{date}\t{register_account}\t{amount:.2f}\t{memo}{cleared_field}",
            f"SPL\t{kind}\t{date}\t{clearing_account}\t{-amount:.2f}\t{memo}{cleared_field}",
            "ENDTRNS",
        ))
    return ("\r\n".join(lines) + "\r\n").encode("ascii")


def make_qbo(df, info, account_type):
    """Route QBO only when the statement provides the required account data."""
    if info.get("td_easyweb"):
        return None, "QBO is unavailable for TD EasyWeb activity printouts."
    if info.get("universal"):
        return None, "QBO requires a verified institution and account mapping."
    currency = info.get("currency")
    if currency and currency != "CAD":
        return None, f"QuickBooks Desktop export is unavailable for {currency}. Import the CSV into an account in the same currency."
    bank = info.get("bank", "TD Canada Trust")
    account_id = info.get("account_id")
    try:
        if bank == "CIBC":
            return generate_cibc_qbo(df, info, account_type), None
        if info["statement_type"] == "chequing":
            if bank == "RBC Royal Bank":
                return generate_rbc_business_chequing_qbo(
                    df, account_id, info.get("branch_id"), info.get("ending_balance")
                ), None
            return None, "QBO requires a confirmed Web Connect account mapping and printed ledger balance."
        if not isinstance(account_id, str) or not re.fullmatch(r"[0-9]{13,19}", account_id):
            return None, "QBO requires a full card account number printed on the statement."
        new_balance = info["summary"].get("new_balance")
        if new_balance is None:
            return None, "QBO requires a printed closing balance."
        if bank == "BMO Bank of Montreal":
            return generate_bmo_credit_card_qbo(df, account_id, new_balance), None
        if bank == "RBC Royal Bank":
            return generate_rbc_mastercard_qbo(df, account_id, new_balance), None
        if bank == "TD Canada Trust":
            return generate_td_credit_card_qbo(df, account_id, new_balance), None
        return None, "QBO requires a compatible institution and account type."
    except ValueError as error:
        return None, str(error)


def generate_quickbooks_csv(
    df
):

    export_df = df.copy()

    export_df["Amount"] = (
        export_df["Credit"]
        -
        export_df["Debit"]
    )

    export_df = export_df[
        [
            "Date",
            "Description",
            "Amount"
        ]
    ]

    export_df["Date"] = (
        pd.to_datetime(
            export_df["Date"]
        )
        .dt.strftime(
            "%d/%m/%Y"
        )
    )

    return export_df.to_csv(
        index=False
    )


# =========================================================
# CHEQUING QBO
#
# KEEPING BANK QBO SEPARATE FROM CREDIT CARD.
# =========================================================

def generate_td_chequing_qbo(
    df,
    account_id
):

    working_df = df.copy()

    working_df["DateObject"] = (
        pd.to_datetime(
            working_df["Date"]
        )
    )

    first_date = (
        working_df["DateObject"]
        .min()
    )

    last_date = (
        working_df["DateObject"]
        .max()
    )

    start_date = (
        qbo_datetime(
            first_date
        )
    )

    end_date = (
        qbo_datetime(
            last_date
        )
    )

    server_time = (
        datetime.now()
        .strftime(
            "%Y%m%d%H%M%S"
        )
    )

    blocks = []

    duplicate_counter = {}

    for _, row in working_df.iterrows():

        debit = float(
            row["Debit"]
        )

        credit = float(
            row["Credit"]
        )

        amount = (
            credit - debit
        )

        date_object = (
            row["DateObject"]
        )

        date_text = (
            date_object.strftime(
                "%Y%m%d"
            )
        )

        description = clean_qbo_text(
            row["Description"]
        )

        key = (
            date_text,
            description,
            f"{amount:.2f}"
        )

        duplicate_counter[key] = (
            duplicate_counter.get(
                key,
                0
            )
            + 1
        )

        fitid = create_fitid(
            "TDCHEQ",
            date_text,
            description,
            amount,
            duplicate_counter[key]
        )

        trntype = (
            "DEBIT"
            if amount < 0
            else "CREDIT"
        )

        blocks.append(
            "<STMTTRN>\n"
            f"<TRNTYPE>{trntype}\n"
            f"<DTPOSTED>{qbo_datetime(date_object)}\n"
            f"<TRNAMT>{amount:.2f}\n"
            f"<FITID>{fitid}\n"
            f"<NAME>{description[:32]}\n"
            f"<MEMO>{description[:255]}\n"
            "</STMTTRN>"
        )

    transaction_text = "\n".join(
        blocks
    )

    return f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<STATUS>
<CODE>0
<SEVERITY>INFO
</STATUS>
<DTSERVER>{server_time}
<LANGUAGE>ENG
<FI>
<ORG>TD Canada Trust
<FID>004
</FI>
</SONRS>
</SIGNONMSGSRSV1>
<BANKMSGSRSV1>
<STMTTRNRS>
<TRNUID>1
<STATUS>
<CODE>0
<SEVERITY>INFO
</STATUS>
<STMTRS>
<CURDEF>CAD
<BANKACCTFROM>
<BANKID>004
<BRANCHID>00000
<ACCTID>{account_id}
<ACCTTYPE>CHECKING
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>{start_date}
<DTEND>{end_date}
{transaction_text}
</BANKTRANLIST>
<LEDGERBAL>
<BALAMT>0.00
<DTASOF>{end_date}
</LEDGERBAL>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""


# =========================================================
# CREDIT CARD QBO
#
# IMPORTANT FIX:
#
# This version uses a conservative OFX 1.02 Web Connect
# credit-card structure.
#
# It intentionally avoids bank-only fields such as:
# BANKID
# BRANCHID
# ACCTTYPE
#
# Credit card uses CCACCTFROM only.
# =========================================================

def generate_td_credit_card_qbo(
    df,
    account_id,
    new_balance
):
    """
    Generate a QuickBooks Desktop Web Connect (.QBO) file
    for a TD Canada Trust credit-card statement.

    Key points:
    - Credit-card OFX wrapper: CREDITCARDMSGSRSV1 / CCSTMTRS
    - Charges are negative; payments/credits are positive
    - Uses TD Canada Trust's Intuit branding ID in addition to FI/FID
    - Adds OFX date timezone suffixes expected by QuickBooks Web Connect
    """

    working_df = df.copy()
    working_df["DateObject"] = pd.to_datetime(working_df["Date"])

    first_date = working_df["DateObject"].min()
    last_date = working_df["DateObject"].max()

    def ofx_dt(value):
        return value.strftime("%Y%m%d") + "120000[0:GMT]"

    start_date = ofx_dt(first_date)
    end_date = ofx_dt(last_date)
    server_time = datetime.now().strftime("%Y%m%d%H%M%S") + "[0:GMT]"

    transaction_blocks = []
    duplicate_counter = {}

    for _, row in working_df.iterrows():
        debit = float(row["Debit"])
        credit = float(row["Credit"])

        # Credit-card OFX convention:
        # purchase/charge = negative
        # payment/refund = positive
        amount = credit - debit

        date_object = row["DateObject"]
        date_text = date_object.strftime("%Y%m%d")
        description = clean_qbo_text(row["Description"])

        duplicate_key = (
            date_text,
            description,
            f"{amount:.2f}"
        )

        duplicate_counter[duplicate_key] = (
            duplicate_counter.get(duplicate_key, 0) + 1
        )

        fitid = create_fitid(
            "TDCC",
            date_text,
            description,
            amount,
            duplicate_counter[duplicate_key]
        )

        trntype = "DEBIT" if amount < 0 else "CREDIT"

        transaction_blocks.append(
            "<STMTTRN>\n"
            f"<TRNTYPE>{trntype}\n"
            f"<DTPOSTED>{ofx_dt(date_object)}\n"
            f"<TRNAMT>{amount:.2f}\n"
            f"<FITID>{fitid}\n"
            f"<NAME>{description[:32]}\n"
            f"<MEMO>{description[:255]}\n"
            "</STMTTRN>"
        )

    transactions_text = "\n".join(transaction_blocks)

    # Credit-card liability balance is negative in OFX.
    ledger_balance = (
        0.00
        if new_balance is None
        else -abs(float(new_balance))
    )

    # TD Canada Trust Web Connect branding.
    # INTU.BID is intentionally included because QuickBooks validates
    # Web Connect files against its Financial Institutions Directory.
    td_org = "TD Canada Trust"
    td_fid = "004"
    td_intu_bid = "0002"

    qbo = f"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<STATUS>
<CODE>0
<SEVERITY>INFO
</STATUS>
<DTSERVER>{server_time}
<LANGUAGE>ENG
<FI>
<ORG>{td_org}
<FID>{td_fid}
</FI>
<INTU.BID>{td_intu_bid}
</SONRS>
</SIGNONMSGSRSV1>
<CREDITCARDMSGSRSV1>
<CCSTMTTRNRS>
<TRNUID>1
<STATUS>
<CODE>0
<SEVERITY>INFO
<MESSAGE>Success
</STATUS>
<CCSTMTRS>
<CURDEF>CAD
<CCACCTFROM>
<ACCTID>{account_id}
</CCACCTFROM>
<BANKTRANLIST>
<DTSTART>{start_date}
<DTEND>{end_date}
{transactions_text}
</BANKTRANLIST>
<LEDGERBAL>
<BALAMT>{ledger_balance:.2f}
<DTASOF>{end_date}
</LEDGERBAL>
</CCSTMTRS>
</CCSTMTTRNRS>
</CREDITCARDMSGSRSV1>
</OFX>
"""

    return qbo


# =========================================================
# USER INTERFACE
# =========================================================


# =========================================================
# CIBC CREDIT CARD AND CHEQUING (CSV VERIFIED; QBO PENDING)
# =========================================================

def cibc_money(raw):
    value = clean_amount(raw.replace('CR', '').replace(' ', ''))
    return -value if 'CR' in raw.upper() else value


def parse_statement_month_day(month_day, statement_year, statement_month):
    date = datetime.strptime(f"{month_day} {statement_year}", "%b %d %Y")
    if date.month > statement_month:
        date = datetime.strptime(f"{month_day} {statement_year-1}", "%b %d %Y")
    return date.strftime('%Y-%m-%d')


def cibc_signed(raw):
    raw = str(raw).strip()
    negative = raw.startswith('-') or raw.upper().endswith('CR')
    value = clean_amount(raw.replace('-', '').replace('CR', '').replace('$', ''))
    return -value if negative else value


def cibc_bank_identifier(full_text):
    transit = re.search(r'Branch transit number\s+(\d{5})', full_text)
    acct = re.search(r'Account number\s+(\d{2}-\d{5})', full_text)
    if not transit or not acct:
        raise ValueError('CIBC transit/account identifiers not found in PDF.')
    return transit.group(1) + ' ' + acct.group(1)


def extract_cibc_credit_card_transactions(pdf_bytes):
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        if len(doc) < 2:
            raise ValueError("CIBC credit-card transaction page missing.")
        text = doc[0].get_text("text")
        transaction_pages = [page.get_text("text") for page in doc if page.number > 0]

    if "Your account at a glance" not in text or "Visa" not in text:
        raise ValueError("Not a supported CIBC Visa statement.")
    date_match = re.search(r"Statement Date\s+([A-Za-z]+)\s+(\d{1,2}),\s+(20\d{2})", text)
    card_match = re.search(r"Account number\s+\d{4}\s+XXXX\s+XXXX\s+\d{4}", text)
    account_id = full_card_account_id(text)
    if not date_match or not (card_match or account_id):
        raise ValueError("CIBC statement date or card number missing.")
    year = int(date_match.group(3))
    month = datetime.strptime(date_match.group(1), "%B").month

    def summary_amount(label):
        match = re.search(
            r"(?m)^" + re.escape(label) + r"\s*\n(?:[+\-=]\s*\n)?\s*(-?\$?[\d,]+\.\d{2}(?:[ \t]*CR)?)",
            text, re.IGNORECASE,
        )
        if not match:
            raise ValueError(f"CIBC credit-card summary missing: {label}.")
        return cibc_signed(match.group(1).upper())

    total_charges = summary_amount("Total charges")
    total_credits = abs(summary_amount("Total credits"))
    previous = summary_amount("Previous balance")
    closing = summary_amount("Total balance")
    if round(previous + total_charges - total_credits, 2) != closing:
        raise ValueError("CIBC credit-card printed balance does not match the statement totals.")

    headings = {
        "Your payments": "payments",
        "Your interest": "interest",
        "Your new charges and credits": "charges",
    }
    totals = ("Total payments", "Total interest this period", "Total for ")
    date_re = re.compile(r"[A-Z][a-z]{2}\s+\d{1,2}$")
    posting_re = re.compile(r"^[A-Z][a-z]{2}\s+\d{1,2}\b")
    money_re = re.compile(r"-?\$?[\d,]+\.\d{2}(?:\s*CR)?", re.IGNORECASE)
    section = None
    transactions = []
    for page_text in transaction_pages:
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        for i, line in enumerate(lines):
            if line in headings:
                section = headings[line]
            elif line.startswith(totals):
                section = None
            if section is None or not date_re.fullmatch(line) or i + 2 >= len(lines):
                continue
            posting = posting_re.match(lines[i + 1])
            if not posting:
                continue
            description = lines[i + 1][posting.end():].lstrip("QÝ ").strip()
            for field in lines[i + 2:i + 8]:
                if field in headings or field.startswith(totals) or posting_re.match(field):
                    break
                if money_re.fullmatch(field):
                    amount = cibc_signed(field.upper())
                    if amount and description:
                        is_credit = section == "payments" or (section == "charges" and amount < 0)
                        transactions.append({
                            "Date": parse_statement_month_day(line, year, month),
                            "Description": description,
                            "Debit": 0.0 if is_credit else abs(amount),
                            "Credit": abs(amount) if is_credit else 0.0,
                        })
                    break
                if not description:
                    description = field.lstrip("QÝ ").strip()

    frame = pd.DataFrame(transactions, columns=["Date", "Description", "Debit", "Credit"])
    debits, credits = round(frame.Debit.sum(), 2), round(frame.Credit.sum(), 2)
    if (debits, credits) != (total_charges, total_credits):
        raise ValueError(
            f"CIBC credit-card transaction totals mismatch: debits {debits:.2f} vs {total_charges:.2f}; "
            f"credits {credits:.2f} vs {total_credits:.2f}."
        )
    return frame, {
        "statement_type": "credit_card",
        "bank": "CIBC",
        "currency": statement_currency("\n".join([text, *transaction_pages])),
        "summary": {
            "previous_balance": previous, "payments_credits": total_credits,
            "purchases_charges": total_charges, "interest": 0.0, "fees": 0.0,
            "new_balance": closing,
        },
        "account_id": account_id,
    }


def extract_cibc_chequing_transactions(pdf_bytes):
    doc=fitz.open(stream=pdf_bytes,filetype='pdf')
    page_texts = [page.get_text("text") for page in doc]
    first = page_texts[0]
    if 'CIBC Account Statement' not in first or 'Transaction details' not in first:
        raise ValueError('Not a supported CIBC bank account statement.')
    m=re.search(r'For\s+([A-Za-z]+)\s+\d+\s+to\s+([A-Za-z]+)\s+\d+,\s+(20\d{2})',first)
    if not m:raise ValueError('CIBC statement period missing.')
    year=int(m.group(3));month=datetime.strptime(m.group(2),'%b').month
    def ctl(label):
        x=re.search(r'(?m)^'+re.escape(label)+r'[^\n]*\n(?:[+\-=]\s*\n)?\s*(-?\$?[\d,]+\.\d{2})',first)
        if not x:raise ValueError('CIBC summary missing: '+label)
        return cibc_signed(x.group(1))
    opening=ctl('Opening balance on');closing=ctl('Closing balance on')
    debit_total=ctl('Withdrawals');credit_total=ctl('Deposits')
    acct=cibc_bank_identifier(first)
    transactions=[];running_balances=[];previous=opening;date=None
    money_re=re.compile(r'^-?\$?[\d,]+\.\d{2}$')
    date_re=re.compile(r'^[A-Z][a-z]{2}\s+\d{1,2}$')
    for page_text in page_texts:
        lines=[x.strip() for x in page_text.splitlines()]
        start=next((i for i,x in enumerate(lines) if x.startswith('Transaction details')),None)
        if start is None:continue
        end=next((i for i in range(start+1,len(lines)) if lines[i].startswith(('Important:','(continued on next page)'))),len(lines))
        seg=lines[start:end];i=0
        while i<len(seg):
            line=seg[i]
            if date_re.fullmatch(line):
                date=parse_statement_month_day(line,year,month);i+=1;continue
            if line.lower() in ('opening balance','balance forward','closing balance'):
                i+=1
                if i<len(seg) and money_re.fullmatch(seg[i]):i+=1
                continue
            if not date or line in ('Date','Description','Withdrawals ($)','Deposits ($)','Balance ($)'):
                i+=1;continue
            j=i;desc=[];amounts=[]
            while j<len(seg):
                t=seg[j]
                if date_re.fullmatch(t) or t.lower() in ('closing balance','balance forward'):break
                if money_re.fullmatch(t):
                    amounts.append(cibc_signed(t))
                    if len(amounts)==2:j+=1;break
                else:desc.append(t)
                j+=1
            if len(amounts)==2 and desc:
                amount,running=amounts;amount=abs(amount)
                delta=round(running-previous,2)
                if abs(delta) != amount:
                    raise ValueError(f'CIBC running balance mismatch near {desc[0]}: {previous:.2f} to {running:.2f}, transaction {amount:.2f}')
                transactions.append({'Date':date,'Description':' '.join(desc),
                                     'Debit':amount if delta<0 else 0.0,'Credit':amount if delta>0 else 0.0})
                running_balances.append(running)
                previous=running;i=j
            else:i+=1
    doc.close()
    df=pd.DataFrame(transactions,columns=['Date','Description','Debit','Credit'])
    if (previous, round(df.Debit.sum(), 2), round(df.Credit.sum(), 2)) != (closing, debit_total, credit_total):
        raise ValueError(f'CIBC chequing/savings control mismatch: ending {previous:.2f}/{closing:.2f}; debits {df.Debit.sum():.2f}/{debit_total:.2f}; credits {df.Credit.sum():.2f}/{credit_total:.2f}')
    return df,{'statement_type':'chequing','bank':'CIBC',
               'control':{'debit_total':debit_total,'credit_total':credit_total},
               'account_id':acct,'opening_balance':opening,'ending_balance':closing,
               'currency':statement_currency("\n".join(page_texts)),
               'running_balances':running_balances,'qbo_verified':True}


def generate_cibc_qbo(df, info, account_type):
    # Institution, account types and identifiers verified against genuine CIBC QBO exports.
    import hashlib
    is_card = account_type in CREDIT_CARD_SELECTIONS
    if is_card:
        acct = info.get("account_id")
        if not isinstance(acct, str) or not re.fullmatch(r"[0-9]{13,19}", acct):
            raise ValueError("The CIBC statement must show the full card account number for QBO export.")
        acct_tag=f'<CCACCTFROM><ACCTID>{acct}<ACCTTYPE>CREDITLINE</CCACCTFROM>'
        outer='CREDITCARDMSGSRSV1';response='CCSTMTTRNRS';statement='CCSTMTRS'
        ending=-(info['summary']['new_balance'])
    else:
        acct=info['account_id']
        if not isinstance(acct, str) or not re.fullmatch(r'\d{5} \d{2}-\d{5}', acct):
            raise ValueError('CIBC transit/account identifier missing or invalid. CSV only.')
        account_types = {'Personal Chequing': 'CHECKING', 'Business Chequing': 'CHECKING',
                         'Personal Savings': 'SAVINGS', 'Business Savings': 'SAVINGS'}
        if account_type not in account_types:
            raise ValueError('Select a CIBC chequing or savings account type.')
        acct_tag=f'<BANKACCTFROM><BANKID>600000100<ACCTID>{acct}<ACCTTYPE>{account_types[account_type]}</BANKACCTFROM>'
        outer='BANKMSGSRSV1';response='STMTTRNRS';statement='STMTRS'
        ending=info['ending_balance']
    dates=pd.to_datetime(df.Date)
    start=dates.min().strftime('%Y%m%d')+'120000';end=dates.max().strftime('%Y%m%d')+'120000'
    now=datetime.now().strftime('%Y%m%d%H%M%S')
    tx=[];seen={}
    for _,r in df.iterrows():
        date=pd.to_datetime(r['Date']).strftime('%Y%m%d')
        amount=round(float(r['Credit'])-float(r['Debit']),2)
        name=clean_qbo_text(str(r['Description']))
        key=f'{acct}|{date}|{amount:.2f}|{name}'
        seen[key]=seen.get(key,0)+1
        fitid=hashlib.sha256(f'{key}|{seen[key]}'.encode()).hexdigest()[:28].upper()
        typ='DEBIT' if amount<0 else 'CREDIT'
        tx.append(f'<STMTTRN><TRNTYPE>{typ}<DTPOSTED>{date}120000.000[-5:EST]<TRNAMT>{amount:.2f}<FITID>{fitid}<NAME>{name[:32]}<MEMO>{name[:255]}</STMTTRN>')
    return ('OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\nSECURITY:NONE\nENCODING:USASCII\nCHARSET:1252\nCOMPRESSION:NONE\nOLDFILEUID:NONE\nNEWFILEUID:NONE\n\n'
            f'<OFX><SIGNONMSGSRSV1><SONRS><STATUS><CODE>0<SEVERITY>INFO<MESSAGE>OK</STATUS><DTSERVER>{now}<LANGUAGE>ENG<INTU.BID>00005</SONRS></SIGNONMSGSRSV1>'
            f'<{outer}><{response}><TRNUID>{now}<STATUS><CODE>0<SEVERITY>INFO<MESSAGE>OK</STATUS><{statement}><CURDEF>CAD{acct_tag}'
            f'<BANKTRANLIST><DTSTART>{start}<DTEND>{end}'+''.join(tx)+'</BANKTRANLIST>'
            f'<LEDGERBAL><BALAMT>{ending:.2f}<DTASOF>{now}</LEDGERBAL></{statement}></{response}></{outer}></OFX>')

# =========================================================
# BANK / ACCOUNT SELECTION
#
# IMPORTANT:
# Adding a bank to the dropdown does NOT activate a parser.
# Only combinations in SUPPORTED_COMBINATIONS can process
# statements. This protects the working TD logic.
# =========================================================

UNIVERSAL_DEPOSIT_TYPES = (
    "Personal Chequing", "Business Chequing", "Joint Chequing",
    "Personal Savings", "Business Savings", "Joint Savings",
    "High-Interest Savings", "Cash Management Account",
)


STATEMENT_AMOUNT_SYMBOLS = {"€": "EUR", "£": "GBP"}


def universal_money_cents(value, *, amount_currencies=None):
    """Parse a printed amount without binary rounding or currency assumptions."""
    original = value
    value = value.strip().replace("\u00a0", " ").replace("\u202f", " ").replace("−", "-")
    if value.startswith("(") and value.endswith(")"):
        negative = True
        value = value[1:-1].strip()
    elif value.endswith("-"):
        negative = True
        value = value[:-1].rstrip()
    else:
        negative = value.startswith("-")
        if value.startswith(("-", "+")):
            value = value[1:]

    currency_code = None
    if amount_currencies is not None:
        prefix = re.fullmatch(r"([A-Z]{3}) +(.+)", value, re.IGNORECASE | re.ASCII)
        suffix = re.fullmatch(r"(.+) +([A-Z]{3})", value, re.IGNORECASE | re.ASCII)
        if prefix:
            currency_code, value = prefix.groups()
        elif suffix:
            value, currency_code = suffix.groups()
            value = value.rstrip()

    allowed_symbols = ("$", *STATEMENT_AMOUNT_SYMBOLS) if amount_currencies is not None else ("$",)
    symbol = None
    if value.startswith(allowed_symbols):
        symbol, value = value[0], value[1:].lstrip()
    elif value.endswith(allowed_symbols):
        symbol, value = value[-1], value[:-1].rstrip()
    symbol_currency = STATEMENT_AMOUNT_SYMBOLS.get(symbol)
    if currency_code:
        currency_code = currency_code.upper()
        if (symbol_currency and currency_code != symbol_currency
                or symbol == "$" and currency_code in STATEMENT_AMOUNT_SYMBOLS.values()):
            raise ValueError("The currency symbol conflicts with the currency code on the same amount.")

    match = re.fullmatch(r"(\d+|\d{1,3}(?:,\d{3})+|\d{1,3}(?: \d{3})+)\.(\d{2})", value)
    if not match:
        match = re.fullmatch(r"(\d+|\d{1,3}(?: \d{3})+|\d{1,3}(?:\.\d{3})+),(\d{2})", value)
    if not match:
        raise ValueError(f"Unrecognized amount: {original!r}.")
    if currency_code or symbol_currency:
        amount_currencies.add(currency_code or symbol_currency)
    whole, fraction = match.groups()
    cents = int(re.sub(r"[., ]", "", whole)) * 100 + int(fraction)
    return -cents if negative else cents



UNIVERSAL_DATE_FORMATS = {
    "DD/MM/YYYY": "%d/%m/%Y",
    "MM/DD/YYYY": "%m/%d/%Y",
    "JJ/MM/AAAA": "%d/%m/%Y",
    "DD-MM-YYYY": "%d-%m-%Y",
    "MM-DD-YYYY": "%m-%d-%Y",
    "JJ-MM-AAAA": "%d-%m-%Y",
    "YYYY/MM/DD": "%Y/%m/%d",
    "YYYY-MM-DD": "%Y-%m-%d",
    "AAAA/MM/JJ": "%Y/%m/%d",
    "AAAA-MM-JJ": "%Y-%m-%d",
    "DD.MM.YYYY": "%d.%m.%Y",
    "MM.DD.YYYY": "%m.%d.%Y",
    "JJ.MM.AAAA": "%d.%m.%Y",
    "YYYY.MM.DD": "%Y.%m.%d",
    "AAAA.MM.JJ": "%Y.%m.%d",
}


ENGLISH_STATEMENT_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)


FRENCH_STATEMENT_MONTHS = {
    name: month
    for month, names in enumerate((
        ("janvier", "janv"), ("février", "févr"), ("mars",), ("avril", "avr"),
        ("mai",), ("juin",), ("juillet", "juill"), ("août",),
        ("septembre", "sept"), ("octobre", "oct"), ("novembre", "nov"), ("décembre", "déc"),
    ), 1)
    for name in names
}


def universal_statement_date(value, declared_format=None):
    normalized = re.sub(rf"\b({ENGLISH_STATEMENT_MONTH})\.(?=\s)", r"\1", value, flags=re.IGNORECASE)
    formats = (
        "%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y",
        "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y",
    )
    if declared_format:
        formats += (declared_format,)
    for fmt in formats:
        try:
            return datetime.strptime(normalized, fmt).date().isoformat()
        except ValueError:
            continue
    french_date = re.fullmatch(r"(1er|\d{1,2})\s+([^\W\d_]+)\.?\s+(\d{4})", value.casefold())
    if french_date and french_date.group(2) in FRENCH_STATEMENT_MONTHS:
        day, month, year = french_date.groups()
        try:
            return datetime(int(year), FRENCH_STATEMENT_MONTHS[month], int(day.removesuffix("er"))).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Unrecognized or ambiguous transaction date: {value!r}.")


def universal_transaction_date(value, declared_format, period):
    day_first = re.fullmatch(r"(?:1er|\d{1,2})\s+[^\W\d_]+\.?", value, re.IGNORECASE)
    month_first = re.fullmatch(rf"{ENGLISH_STATEMENT_MONTH}\.?\s+\d{{1,2}}", value, re.IGNORECASE)
    numeric = re.fullmatch(r"\d{1,2}([/.-])\d{1,2}", value)
    if not (day_first or month_first or numeric):
        return universal_statement_date(value, declared_format)
    if numeric:
        separator = numeric.group(1)
        if declared_format not in (f"%d{separator}%m{separator}%Y", f"%m{separator}%d{separator}%Y"):
            raise ValueError(f"A matching printed day/month or month/day format is required for {value!r}.")
    else:
        separator = ", " if month_first else " "
    if period is None:
        raise ValueError(f"A printed statement period is required for a date without a year: {value!r}.")

    start, end = period
    candidates = []
    for year in range(int(start[:4]), int(end[:4]) + 1):
        try:
            date = universal_statement_date(
                f"{value}{separator}{year:04d}", declared_format if numeric else None,
            )
        except ValueError:
            continue
        if start <= date <= end:
            candidates.append(date)
            if len(candidates) > 1:
                break
    if len(candidates) != 1:
        raise ValueError(f"The date {value!r} must identify exactly one day in the printed statement period.")
    return candidates[0]


STATEMENT_BANK_ALIASES = {
    "td": "TD Canada Trust",
    "rbc": "RBC Royal Bank",
    "rbc banque royale": "RBC Royal Bank",
    "bmo": "BMO Bank of Montreal",
    "bmo banque de montréal": "BMO Bank of Montreal",
    "bank of montreal": "BMO Bank of Montreal",
    "banque de montréal": "BMO Bank of Montreal",
    "banque scotia": "Scotiabank",
    "banque nationale du canada": "National Bank of Canada",
    "banque laurentienne du canada": "Laurentian Bank of Canada",
    "tangerine": "Tangerine Bank",
}

STATEMENT_ACCOUNT_ALIASES = {
    "compte-chèques personnel": "Personal Chequing",
    "compte-chèques d’entreprise": "Business Chequing",
    "compte d’épargne personnel": "Personal Savings",
    "compte d’épargne d’entreprise": "Business Savings",
    "carte de crédit": "Credit Card",
    "carte de crédit d’entreprise": "Business Credit Card",
}

STATEMENT_PRODUCT_HEADINGS = {
    "td business cash back visa": ("TD Canada Trust", "Business Credit Card"),
    "your no fee chequing account": ("Simplii Financial", "Personal Chequing"),
}


def detect_statement_selection(pdf_bytes):
    """Recognize explicit metadata and exact headings on the first page."""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        if not len(document):
            return {}
        lines = [
            " ".join(line.casefold().replace("'", "’").split())
            for line in document[0].get_text(sort=True).splitlines() if line.strip()
        ]
    banks = {name.casefold(): name for name in CANADIAN_BANKS} | STATEMENT_BANK_ALIASES
    accounts = {name.casefold(): name for name in ACCOUNT_TYPES} | STATEMENT_ACCOUNT_ALIASES
    labels = {
        "bank": "bank", "banque": "bank",
        "account type": "account type", "type de compte": "account type",
    }
    choices = {"bank": banks, "account type": accounts}
    matches = {key: set() for key in choices}
    for line in lines:
        label, separator, value = line.partition(":")
        category = labels.get(label.strip())
        if separator and category:
            match = choices[category].get(value.strip())
            if match:
                matches[category].add(match)
    for line in lines[:8]:
        if line in banks:
            matches["bank"].add(banks[line])
    for line in lines:
        if product := STATEMENT_PRODUCT_HEADINGS.get(line):
            bank, account = product
            matches["bank"].add(bank)
            matches["account type"].add(account)
    if len(matches["bank"]) > 1:
        return {}
    return {key: next(iter(values)) for key, values in matches.items() if len(values) == 1}


def statement_page_count(pdf_bytes):
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        return len(document)


def render_statement_page(pdf_bytes, page_number):
    """Render a bounded, in-memory preview of one 1-based PDF page."""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        if not 1 <= page_number <= len(document):
            raise ValueError("The selected PDF page is unavailable.")
        page = document[page_number - 1]
        longest_side = max(page.rect.width, page.rect.height)
        if longest_side <= 0:
            raise ValueError("The selected PDF page has no visible area.")
        scale = min(2, 1600 / longest_side)
        return page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes("png")


def marked_amount_cents(value, *, amount_currencies=None):
    marker = re.fullmatch(r"(.+?)\s*(DR|CR)", value.strip(), re.IGNORECASE)
    if not marker:
        return None
    amount, direction = marker.groups()
    amount = amount.strip().replace("−", "-")
    if amount.startswith(("+", "-", "(")) or amount.endswith("-"):
        raise ValueError("An amount with DR or CR must not include a separate sign.")
    cents = universal_money_cents(amount, amount_currencies=amount_currencies)
    return -cents if direction.upper() == "DR" else cents


def printed_balance_cents(value, *, is_card, amount_currencies=None):
    marked = marked_amount_cents(value, amount_currencies=amount_currencies)
    if marked is None:
        return universal_money_cents(value, amount_currencies=amount_currencies)
    # A credit balance increases deposits but reduces the amount owed on a card.
    return -marked if is_card else marked


def split_column_amount_cents(value, *, debit, is_card, amount_currencies=None):
    if value in ("-", "—"):
        return 0
    if is_card and not debit:
        # Card credit columns historically allow negative amounts and a spaced CR suffix.
        value = re.sub(r"\s+CR$", "", value, flags=re.IGNORECASE)
    marked = marked_amount_cents(value, amount_currencies=amount_currencies)
    if marked is not None:
        if marked and (marked < 0) != debit:
            raise ValueError("The DR or CR marker conflicts with its transaction column.")
        return abs(marked)
    amount = universal_money_cents(value, amount_currencies=amount_currencies)
    return abs(amount) if is_card and not debit else amount


def fixed_width_column_starts(line, columns):
    starts = []
    offset = 0
    for column in columns:
        start = line.index(column, offset)
        starts.append(start)
        offset = start + len(column)
    return starts


def fill_blank_amount_cell(line, columns, header_starts, header_ends, has_running_balance, amount_index):
    starts = fixed_width_column_starts(line, columns)
    if starts[:amount_index] != header_starts[:amount_index]:
        return columns

    def aligns(value_index, heading_index):
        left = starts[value_index]
        right = left + len(columns[value_index])
        return left == header_starts[heading_index] or right == header_ends[heading_index]

    if has_running_balance and not aligns(-1, -1):
        return columns
    matches = [index for index in (amount_index, amount_index + 1) if aligns(amount_index, index)]
    if len(matches) != 1:
        return columns
    blank_index = amount_index + 1 if matches[0] == amount_index else amount_index
    return [*columns[:blank_index], "-", *columns[blank_index:]]


def simplii_positioned_lines(words):
    """Build table lines using a consistent horizontal scale for every PDF row."""
    rows = {}
    for x0, y0, x1, y1, word, *_ in words:
        baseline = round(y1 / 2) * 2
        rows.setdefault(baseline, []).append((x0, x1, word))

    lines = []
    for _, words_on_row in sorted(rows.items()):
        groups = []
        for left, right, word in sorted(words_on_row):
            if groups and left - groups[-1][0] <= 8:
                _, text = groups[-1]
                groups[-1] = (right, f"{text} {word}")
            else:
                groups.append((right, word))
        line = ""
        for right, text in groups:
            start = round(right / 2) - len(text)
            gap = max(2 if line else 0, start - len(line))
            line += " " * gap + text
        lines.append(line)
    return lines


def normalize_simplii_chequing_table(lines, page_number):
    """Adapt the two-date Simplii table while retaining printed balance and amounts."""
    heading = re.compile(
        r"^\s*trans\.?\s+(?:date\s+)?eff\.?\s+(?:date\s+)?transaction\s+"
        r"(funds\s+out)\s+(funds\s+in)\s+(balance)\s*$", re.IGNORECASE
    )
    transaction = re.compile(r"^\s*([A-Za-z]{3} \d{1,2}) {2,}[A-Za-z]{3} \d{1,2} {2,}(.+)$")
    header_ends = None
    previous_balance = None
    seen_transaction = False
    normalized = []
    for line in lines:
        header = heading.fullmatch(line)
        if header:
            header_ends = [header.end(index) for index in (1, 2, 3)]
            normalized.append("Date  Description  Debit  Credit  Balance")
            continue
        row = transaction.fullmatch(line.rstrip()) if header_ends else None
        if not row:
            normalized.append(line)
            continue
        date, details = row.groups()
        fields = re.split(r" {2,}", details)
        if not 2 <= len(fields) <= 4:
            raise ValueError(f"Could not identify the Simplii transaction columns on page {page_number}.")
        description, *amounts = fields
        ends = [row.start(2) + start + len(field)
                for start, field in zip(fixed_width_column_starts(details, fields), fields)]
        columns = ["-", "-", "-"]
        for amount, end in zip(amounts, ends[1:]):
            distances = [abs(end - anchor) for anchor in header_ends]
            column = distances.index(min(distances))
            gap = min(abs(anchor - header_ends[column]) for i, anchor in enumerate(header_ends) if i != column)
            if distances[column] * 2 >= gap or columns[column] != "-":
                raise ValueError(f"Could not align a Simplii amount with its column on page {page_number}.")
            columns[column] = amount
        if columns[2] == "-":
            raise ValueError(f"A Simplii row is missing its printed running balance on page {page_number}.")
        if description.casefold() == "balance forward":
            if columns[:2] != ["-", "-"] or previous_balance is not None or seen_transaction:
                raise ValueError(f"Unexpected Simplii balance-forward row on page {page_number}.")
            previous_balance = columns[2]
            if page_number == 1:
                normalized.append(f"Opening balance: {previous_balance}")
            continue
        seen_transaction = True
        normalized.append("  ".join([date, description, *columns]))
    return (normalized if header_ends else None), previous_balance


def statement_running_balances_match(rows, opening, running_balances, *, is_card):
    balance = opening
    for (_, _, debit, credit), printed in zip(rows, running_balances):
        balance += debit - credit if is_card else credit - debit
        if balance != printed:
            return False
    return True


def mismatched_balance_forward_page(rows, opening, carried_balances, *, is_card):
    calculated = opening
    previous_row_count = 0
    for row_count, page_number, printed in carried_balances:
        calculated += sum(
            debit - credit if is_card else credit - debit
            for _, _, debit, credit in rows[previous_row_count:row_count]
        )
        if printed != calculated:
            return page_number
        previous_row_count = row_count
    return None


def classify_signed_card_rows(rows, controls, running_balances, marked_rows, carried_balances):
    reversed_rows = [
        row if index in marked_rows else (row[0], row[1], row[3], row[2])
        for index, row in enumerate(rows)
    ]
    candidates = (rows,) if reversed_rows == rows else (rows, reversed_rows)
    matches = []
    failed_page = None
    for candidate in candidates:
        charges = sum(debit for _, _, debit, _ in candidate)
        credits = sum(credit for _, _, _, credit in candidate)
        if (charges, credits) != (controls["debit"], controls["credit"]):
            continue
        if any(key in controls and controls[key] != count for key, count in (
            ("debit_count", sum(debit > 0 for _, _, debit, _ in candidate)),
            ("credit_count", sum(credit > 0 for _, _, _, credit in candidate)),
            ("transaction_count", len(candidate)),
        )):
            continue
        if controls["opening"] + charges - credits != controls["closing"]:
            continue
        if not statement_running_balances_match(candidate, controls["opening"], running_balances, is_card=True):
            continue
        page = mismatched_balance_forward_page(candidate, controls["opening"], carried_balances, is_card=True)
        if page is None:
            matches.append(candidate)
        else:
            failed_page = page
    if not matches:
        if failed_page is not None:
            raise ValueError(f"The printed balance forward on page {failed_page} differs from the calculated balance.")
        raise ValueError("The signed card amounts do not match the printed totals, transaction counts, or balances.")
    if len(matches) != 1:
        raise ValueError("The signed card amounts are ambiguous. Both sign conventions match the printed controls.")
    return matches[0]


def extract_universal_transactions(pdf_bytes, bank, account_type, *, use_ocr=False):
    """Read explicit transaction tables and independently printed statement controls."""
    is_card = account_type in CREDIT_CARD_SELECTIONS
    if not is_card and account_type not in UNIVERSAL_DEPOSIT_TYPES:
        raise ValueError("The experimental parser supports deposit and credit-card statements.")
    labels = {
        "opening balance": "opening", "beginning balance": "opening",
        "closing balance": "closing", "ending balance": "closing",
        "total withdrawals": "debit", "total debits": "debit",
        "total deposits": "credit", "total credits": "credit",
        "number of withdrawals": "debit_count", "number of debits": "debit_count",
        "number of deposits": "credit_count", "number of credits": "credit_count",
        "transaction count": "transaction_count", "number of transactions": "transaction_count",
        "solde d'ouverture": "opening", "solde de clôture": "closing",
        "total des débits": "debit", "total des retraits": "debit",
        "total des crédits": "credit", "total des dépôts": "credit",
        "nombre de débits": "debit_count", "nombre de retraits": "debit_count",
        "nombre de crédits": "credit_count", "nombre de dépôts": "credit_count",
        "nombre de transactions": "transaction_count",
    }
    debit_first_headers = {
        ("date", "description", "debit", "credit"),
        ("date", "description", "withdrawals", "deposits"),
        ("date", "description", "débit", "crédit"),
        ("date", "description", "retraits", "dépôts"),
    }
    if bank == "Simplii Financial" and not is_card:
        labels.update({"total funds out": "debit", "total funds in": "credit"})
    if is_card:
        labels = {
            "previous balance": "opening", "opening balance": "opening",
            "new balance": "closing", "closing balance": "closing",
            "total charges": "debit", "total payments and credits": "credit",
            "total payments & credits": "credit", "total credits": "credit",
            "number of charges": "debit_count", "number of payments and credits": "credit_count",
            "transaction count": "transaction_count", "number of transactions": "transaction_count",
            "solde précédent": "opening", "nouveau solde": "closing",
            "total des frais": "debit", "total des achats et autres frais": "debit",
            "total des paiements et crédits": "credit",
            "nombre d'achats et autres frais": "debit_count",
            "nombre de paiements et crédits": "credit_count",
            "nombre de transactions": "transaction_count",
        }
        debit_first_headers = {
            ("date", "description", "charges", "payments and credits"),
            ("date", "description", "charges", "payments & credits"),
            ("date", "description", "charges", "credits"),
            ("date", "description", "frais", "paiements et crédits"),
            ("date", "description", "achats et autres frais", "paiements et crédits"),
        }
    credit_first_headers = {
        (*heading[:2], heading[3], heading[2]) for heading in debit_first_headers
    }
    signed_headers = {
        ("date", "description", "amount"),
        ("date", "description", "montant"),
    }
    heading_aliases = {
        "transaction description": "description",
        "description de la transaction": "description",
        "running balance": "balance",
    }
    if is_card:
        heading_aliases.update({
            "purchases and other charges": "charges",
            "purchases & other charges": "charges",
        })
    secondary_date_headings = ("posting date", "posted date", "date de comptabilisation")
    if not is_card:
        secondary_date_headings += ("effective date", "date d'effet", "date d’effet")
    controls = {}
    rows = []
    running_balances = []
    carried_balances = []
    source_pages = []
    posting_dates = []
    marked_rows = set()
    layout = None
    currencies = set()
    amount_currencies = set()
    printed_periods = []
    date_format = None
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for page in document:
            header_starts = header_ends = None
            text_page = None
            lines = page.get_text(sort=True).splitlines()
            if not any(line.strip() for line in lines):
                if not use_ocr:
                    raise ValueError(f"Page {page.number + 1} has no readable text. Enable local OCR or use a text PDF.")
                try:
                    text_page = page.get_textpage_ocr(dpi=300, full=True)
                except (RuntimeError, ValueError) as error:
                    raise ValueError("Local OCR is unavailable. Install Tesseract and configure TESSDATA_PREFIX.") from error
                lines = page.get_text(sort=True, textpage=text_page).splitlines()
                if not any(line.strip() for line in lines):
                    raise ValueError(f"Local OCR found no readable text on page {page.number + 1}.")
            if bank == "Simplii Financial" and not is_card:
                positioned = simplii_positioned_lines(page.get_text("words", textpage=text_page))
                table_lines, forward = normalize_simplii_chequing_table(positioned, page.number + 1)
                if table_lines is not None:
                    lines = table_lines
                if forward is not None and page.number > 0:
                    preceding_balance = running_balances[-1] if running_balances else controls.get("opening")
                    forward_balance = printed_balance_cents(
                        forward, is_card=False, amount_currencies=amount_currencies,
                    )
                    if forward_balance != preceding_balance:
                        raise ValueError(f"Simplii balance forward differs from the preceding balance on page {page.number + 1}.")
            last_transaction_line = None
            for line_number, raw_line in enumerate(lines):
                line = raw_line.strip()
                currency = printed_currency_code(line)
                if currency:
                    currencies.add(currency)
                    continue
                label, separator, value = line.replace("’", "'").partition(":")
                label = " ".join(label.split())
                normalized_label = label.strip().casefold()
                if normalized_label in ("date format", "format de date"):
                    declared = UNIVERSAL_DATE_FORMATS.get(value.strip().upper())
                    if declared is None:
                        raise ValueError("The statement declares an unsupported date format.")
                    if date_format is not None and date_format != declared:
                        raise ValueError("The statement declares conflicting date formats.")
                    date_format = declared
                    continue
                period_line = re.fullmatch(
                    r"(?:statement\s+period|période\s+du\s+relevé)(?:\s*:\s*(.*)|\s+((?:from|du)\s+.+))",
                    line, re.IGNORECASE,
                )
                if period_line:
                    period_text = period_line.group(1) if period_line.group(1) is not None else period_line.group(2)
                    period_text = re.sub(r"^(?:from|du)\s+", "", period_text.strip(), flags=re.IGNORECASE)
                    dates = re.split(r"\s+(?:to|au|[-–—])\s+", period_text, flags=re.IGNORECASE)
                    if len(dates) != 2:
                        raise ValueError("Expected a statement period with a start and end date.")
                    printed_periods.append(dates)
                    continue
                if not separator:
                    summary = re.fullmatch(
                        r"(" + "|".join(labels) + r")\s+(.+)", label, re.IGNORECASE
                    )
                    if summary:
                        label, value = summary.groups()
                key = labels.get(label.strip().lower())
                if key:
                    value = value.strip()
                    if key.endswith("_count"):
                        if not re.fullmatch(r"[0-9]+", value):
                            raise ValueError(f"Unrecognized printed {label.lower()}.")
                        recorded = int(value)
                    elif key in ("opening", "closing"):
                        recorded = printed_balance_cents(
                            value, is_card=is_card, amount_currencies=amount_currencies,
                        )
                    else:
                        marked = marked_amount_cents(value, amount_currencies=amount_currencies)
                        if marked is not None:
                            if marked and (marked < 0) != (key == "debit"):
                                raise ValueError(f"The DR or CR marker conflicts with the printed {label.lower()}.")
                            recorded = abs(marked)
                        else:
                            recorded = universal_money_cents(value, amount_currencies=amount_currencies)
                            if is_card and key == "credit":
                                recorded = abs(recorded)
                    if key in controls and controls[key] != recorded:
                        raise ValueError(f"Conflicting printed {label.lower()}.")
                    controls[key] = recorded
                    continue
                carried = re.fullmatch(
                    r"(?:balance forward|balance (?:brought|carried) forward|solde reporté|solde à reporter)"
                    r"(?:\s*:\s*|\s{2,})(.+)",
                    line, re.IGNORECASE,
                )
                if carried:
                    balance = printed_balance_cents(
                        carried.group(1), is_card=is_card, amount_currencies=amount_currencies,
                    )
                    carried_balances.append((len(rows), page.number + 1, balance))
                    continue
                columns = re.split(r"\t+| {2,}", line)
                headings = tuple(" ".join(column.casefold().split()) for column in columns)
                headings = tuple(heading_aliases.get(heading, heading) for heading in headings)
                running = headings[-1] in ("balance", "solde")
                base_headings = headings[:-1] if running else headings
                transaction_date_heading = base_headings[:1] in (("transaction date",), ("date de transaction",))
                has_posting_date = (
                    transaction_date_heading and len(base_headings) > 1
                    and base_headings[1] in secondary_date_headings
                )
                if transaction_date_heading:
                    base_headings = ("date", *base_headings[1 + has_posting_date:])
                credit_first = base_headings in credit_first_headers
                if credit_first or base_headings in debit_first_headers or base_headings in signed_headers:
                    current_layout = (len(base_headings), running, credit_first, has_posting_date)
                    if layout is not None and current_layout != layout:
                        raise ValueError("Transaction headings changed between pages.")
                    layout = current_layout
                    header_starts = header_ends = None
                    if "\t" not in raw_line:
                        header_starts = fixed_width_column_starts(raw_line, columns)
                        header_ends = [start + len(column) for start, column in zip(header_starts, columns)]
                    continue
                if not re.match(
                    rf"(?:\d{{1,4}}[-/. ]|1er\s+|{ENGLISH_STATEMENT_MONTH}\.?\s+\d{{1,2}}(?:,| \d{{4}}(?= {{2,}}|\t)|(?= {{2,}}|\t)))",
                    line, re.IGNORECASE,
                ):
                    if (last_transaction_line == line_number - 1 and header_starts is not None
                            and len(columns) == 1 and line and "\t" not in raw_line):
                        description_column = 2 if layout[3] else 1
                        start = len(raw_line) - len(raw_line.lstrip(" "))
                        end = len(raw_line.rstrip())
                        if (start == header_starts[description_column]
                                and end <= header_starts[description_column + 1]):
                            date, description, debit, credit = rows[-1]
                            rows[-1] = (date, f"{description} {line}", debit, credit)
                            last_transaction_line = line_number
                    continue
                if layout is None:
                    raise ValueError(f"Missing transaction headings on page {page.number + 1}.")
                transaction_columns, has_running_balance, credit_first, has_posting_date = layout
                description_index = 2 if has_posting_date else 1
                amount_index = description_index + 1
                expected_columns = transaction_columns + has_running_balance + has_posting_date
                if (transaction_columns == 4 and len(columns) == expected_columns - 1
                        and header_starts is not None and "\t" not in raw_line):
                    columns = fill_blank_amount_cell(
                        raw_line, columns, header_starts, header_ends, has_running_balance, amount_index,
                    )
                if len(columns) != expected_columns:
                    raise ValueError(f"Unrecognized transaction columns on page {page.number + 1}.")
                date, description = columns[0], columns[description_index]
                if has_posting_date:
                    posting_dates.append(columns[1])
                if transaction_columns == 3:
                    amount = columns[amount_index]
                    signed = marked_amount_cents(amount, amount_currencies=amount_currencies)
                    if signed is None:
                        signed = universal_money_cents(amount, amount_currencies=amount_currencies)
                    elif is_card:
                        marked_rows.add(len(rows))
                    debit_cents, credit_cents = max(-signed, 0), max(signed, 0)
                else:
                    amounts = columns[amount_index:amount_index + 2]
                    debit, credit = amounts[::-1] if credit_first else amounts
                    debit_cents = split_column_amount_cents(
                        debit, debit=True, is_card=is_card, amount_currencies=amount_currencies,
                    )
                    credit_cents = split_column_amount_cents(
                        credit, debit=False, is_card=is_card, amount_currencies=amount_currencies,
                    )
                if not description.strip() or min(debit_cents, credit_cents) < 0 or bool(debit_cents) == bool(credit_cents):
                    raise ValueError(f"Expected one positive debit or credit on page {page.number + 1}.")
                rows.append((date, description, debit_cents, credit_cents))
                last_transaction_line = line_number
                source_pages.append(page.number + 1)
                if has_running_balance:
                    balance = printed_balance_cents(
                        columns[-1], is_card=is_card, amount_currencies=amount_currencies,
                    )
                    running_balances.append(balance)
    if not rows or not {"opening", "closing", "debit", "credit"} <= controls.keys():
        if is_card:
            raise ValueError("Expected card transaction rows and printed previous balance, new balance, total charges and total credits.")
        raise ValueError("Expected transaction rows and printed opening balance, closing balance, total debits and total credits.")
    if len(currencies) > 1:
        raise ValueError("The statement declares conflicting currencies.")
    if amount_currencies and not currencies:
        raise ValueError("Currency symbols or codes on amounts require an explicit statement currency.")
    if not amount_currencies.issubset(currencies):
        raise ValueError("A currency symbol or code on an amount conflicts with the declared statement currency.")
    period = None
    for dates in printed_periods:
        printed_period = tuple(universal_statement_date(date, date_format) for date in dates)
        if printed_period[0] > printed_period[1] or (period and period != printed_period):
            raise ValueError("The printed statement period is reversed or conflicts between pages.")
        period = printed_period
    for posting_date in posting_dates:
        try:
            universal_transaction_date(posting_date, date_format, period)
        except ValueError as error:
            label = "card posting date" if is_card else "deposit posting or effective date"
            raise ValueError(f"Invalid {label}: {error}") from error
    rows = [
        (universal_transaction_date(date, date_format, period), description, debit, credit)
        for date, description, debit, credit in rows
    ]
    if is_card and layout[0] == 3:
        rows = classify_signed_card_rows(rows, controls, running_balances, marked_rows, carried_balances)
    else:
        if not statement_running_balances_match(rows, controls["opening"], running_balances, is_card=is_card):
            raise ValueError("A printed running balance differs from the calculated balance.")
        page = mismatched_balance_forward_page(rows, controls["opening"], carried_balances, is_card=is_card)
        if page is not None:
            raise ValueError(f"The printed balance forward on page {page} differs from the calculated balance.")
    carried_checks = [(count, page, printed / 100) for count, page, printed in carried_balances]
    frame = pd.DataFrame(rows, columns=["Date", "Description", "Debit", "Credit"])
    frame[["Debit", "Credit"]] = frame[["Debit", "Credit"]] / 100
    return frame, {
        "bank": bank, "account_type": account_type,
        "statement_type": "credit_card" if is_card else "chequing",
        "currency": next(iter(currencies), None), "account_id": None, "universal": True,
        "control": {key: value if key.endswith("_count") else value / 100
                    for key, value in controls.items()},
        "running_balances": [balance / 100 for balance in running_balances],
        "carried_balances": carried_checks,
        "period": period,
        "source_pages": source_pages,
    }


def valid_transaction_rows(frame, dates):
    amounts = frame[["Debit", "Credit"]]
    return (
        not frame.empty
        and dates.notna().all()
        and frame["Description"].fillna("").str.strip().ne("").all()
        and ((frame["Debit"] > 0) ^ (frame["Credit"] > 0)).all()
        and (amounts >= 0).all().all()
        and amounts.eq(amounts.round(2)).all().all()
        and (amounts < float("inf")).all().all()
    )


def reconcile_credit_card(frame, info):
    summary = info.get("summary", {})
    previous = summary.get("previous_balance")
    purchases = summary.get("purchases_charges")
    payments = summary.get("payments_credits")
    closing = summary.get("new_balance")
    interest = summary.get("interest") or 0.0
    fees = summary.get("fees") or 0.0
    charges = None if purchases is None else round(purchases + interest + fees, 2)
    debits = round(float(frame["Debit"].sum()), 2)
    credits = round(float(frame["Credit"].sum()), 2)
    calculated = None if previous is None else round(previous + debits - credits, 2)
    charge_label = "Charges implied by printed balances" if summary.get("purchases_derived") else "Charges (purchases + interest + fees)"
    rows = [
        (charge_label, charges, debits, "$"),
        ("Payments & credits", payments, credits, "$"),
        ("Closing balance", closing, calculated, "$"),
    ]
    dates = pd.to_datetime(frame["Date"], format="%Y-%m-%d", errors="coerce")
    ok = valid_transaction_rows(frame, dates) and all(
        expected is not None and expected == actual for _, expected, actual, _ in rows
    )
    return rows, bool(ok)


def reconcile_universal_transactions(frame, info):
    control = info["control"]
    debits = frame["Debit"]
    credits = frame["Credit"]
    debit_total = round(float(debits.sum()), 2)
    credit_total = round(float(credits.sum()), 2)
    is_card = info.get("statement_type") == "credit_card"
    changes = debits - credits if is_card else credits - debits
    calculated = round(control["opening"] + float(changes.sum()), 2)
    rows = [
        ("Total charges" if is_card else "Total debits", control["debit"], debit_total, "$"),
        ("Payments & credits" if is_card else "Total credits", control["credit"], credit_total, "$"),
        ("Closing balance", control["closing"], calculated, "$"),
    ]
    for key, label, actual in (
        ("debit_count", "Debit count", int((debits > 0).sum())),
        ("credit_count", "Credit count", int((credits > 0).sum())),
        ("transaction_count", "Transaction count", len(frame)),
    ):
        if key in control:
            rows.append((label, control[key], actual, "n"))
    for row_count, page_number, expected in info.get("carried_balances", []):
        actual = round(control["opening"] + float(changes.iloc[:row_count].sum()), 2)
        if row_count > len(frame):
            actual = None
        rows.append((f"Balance forward on page {page_number}", expected, actual, "$"))
    balances = info.get("running_balances", [])
    if balances:
        calculated_balances = (control["opening"] + changes.cumsum()).round(2)
        matches = sum(expected == actual for expected, actual in zip(balances, calculated_balances))
        rows.append(("Running balances matched", len(balances), matches, "n"))
        rows.append(("Rows with printed balances", len(balances), len(frame), "n"))

    dates = pd.to_datetime(frame["Date"], format="%Y-%m-%d", errors="coerce")
    if info.get("period"):
        start, end = (pd.Timestamp(date) for date in info["period"])
        rows.append(("Transactions within statement period", len(frame), int(dates.between(start, end).sum()), "n"))
    return rows, bool(valid_transaction_rows(frame, dates) and all(
        expected == actual for _, expected, actual, _ in rows
    ))



CANADIAN_BANKS = [
    "TD Canada Trust",
    "RBC Royal Bank",
    "Scotiabank",
    "BMO Bank of Montreal",
    "CIBC",
    "National Bank of Canada",
    "Desjardins",
    "Tangerine Bank",
    "Simplii Financial",
    "EQ Bank",
    "ATB Financial",
    "Laurentian Bank of Canada",
    "Canadian Western Bank",
    "Manulife Bank",
    "PC Financial",
    "Wealthsimple",
    "Motusbank",
    "Home Trust",
    "First Nations Bank of Canada",
    "Coast Capital Savings",
    "Meridian Credit Union",
    "Vancity",
    "Servus Credit Union",
    "Other Canadian Bank / Credit Union"
]

ACCOUNT_TYPES = [
    "Personal Chequing",
    "Business Chequing",
    "Joint Chequing",
    "Personal Savings",
    "Business Savings",
    "Joint Savings",
    "High-Interest Savings",
    "Credit Card",
    "Personal Credit Card",
    "Business Credit Card",
    "Corporate Credit Card",
    "Secured Credit Card",
    "Prepaid Credit Card",
    "Line of Credit",
    "Personal Line of Credit",
    "Business Line of Credit",
    "Home Equity Line of Credit (HELOC)",
    "Student Line of Credit",
    "Personal Loan",
    "Business Loan",
    "Vehicle Loan",
    "Mortgage",
    "Equipment Financing",
    "Non-Registered Investment Account",
    "TFSA",
    "RRSP",
    "RRIF",
    "RESP",
    "FHSA",
    "RDSP",
    "LIRA",
    "LIF",
    "Corporate Investment Account",
    "Trust Account",
    "Cash Management Account",
    "GIC and Term Deposit",
    "Digital Banking Account",
    "Other Account Type"
]

CREDIT_CARD_SELECTIONS = (
    "Credit Card", "Personal Credit Card", "Business Credit Card",
    "Corporate Credit Card", "Secured Credit Card",
)

DEDICATED_EXTRACTORS = {
    ("TD Canada Trust", "Business Chequing"): extract_td_chequing_transactions,
    ("TD Canada Trust", "Credit Card"): extract_td_credit_card_transactions,
    ("RBC Royal Bank", "Business Chequing"): extract_rbc_business_chequing_transactions,
    ("RBC Royal Bank", "Credit Card"): extract_rbc_mastercard_transactions,
    ("BMO Bank of Montreal", "Business Chequing"): extract_bmo_business_chequing_transactions,
    ("BMO Bank of Montreal", "Credit Card"): extract_bmo_credit_card_transactions,
    ("Scotiabank", "Business Chequing"): extract_scotiabank_business_chequing_transactions,
    ("CIBC", "Credit Card"): extract_cibc_credit_card_transactions,
    ("CIBC", "Personal Chequing"): extract_cibc_chequing_transactions,
    ("CIBC", "Business Chequing"): extract_cibc_chequing_transactions,
    ("CIBC", "Personal Savings"): extract_cibc_chequing_transactions,
    ("CIBC", "Business Savings"): extract_cibc_chequing_transactions,
}

SUPPORTED_COMBINATIONS = set(DEDICATED_EXTRACTORS)


def get_dedicated_extractor(bank, account_type):
    if account_type in CREDIT_CARD_SELECTIONS:
        account_type = "Credit Card"
    return DEDICATED_EXTRACTORS.get((bank, account_type))


col1, col2 = st.columns(2)

with col1:

    bank = st.selectbox(
        "Bank",
        CANADIAN_BANKS
    )

with col2:

    account_type = st.selectbox(
        "Account Type",
        ACCOUNT_TYPES,
        index=1
    )


extractor = get_dedicated_extractor(bank, account_type)

if extractor:
    st.info(f"Dedicated parser available for compatible {bank} statement layouts.")
else:

    st.info(
        f"{bank} - {account_type} is listed but not activated yet. "
        "A sample PDF statement must be tested before this combination "
        "is enabled."
    )


uploaded_file = st.file_uploader(
    "Upload Bank PDF Statement",
    type=["pdf"]
)


process = False
if uploaded_file is not None:
    st.success(f"Uploaded: {uploaded_file.name}")
    process = st.button("Process Statement", type="primary", disabled=extractor is None)

current_input = (uploaded_file.file_id if uploaded_file else None, bank, account_type)
if st.session_state.get("statement_input") != current_input or process:
    for key in ("transactions", "statement_info", "processed_account_type"):
        st.session_state.pop(key, None)
    st.session_state["statement_input"] = current_input

if process and uploaded_file is not None and extractor is not None:
    try:
        df, statement_info = extractor(uploaded_file.getvalue())
        st.session_state["transactions"] = df
        st.session_state["statement_info"] = statement_info
        st.session_state["processed_account_type"] = account_type
        st.session_state["statement_run"] = st.session_state.get("statement_run", 0) + 1
    except Exception as error:
        st.error(f"Unable to process statement: {error}")


# =========================================================
# RESULTS
# =========================================================

if "transactions" in st.session_state:

    df = st.session_state[
        "transactions"
    ]

    statement_info = (
        st.session_state[
            "statement_info"
        ]
    )

    st.divider()

    st.header(
        "Transaction Review"
    )
    if statement_info.get("currency"):
        st.caption(f"Statement currency: {statement_info['currency']}. Import CSV into an account in the same currency.")

    if df.empty:

        st.error(
            "No transactions were detected."
        )

    else:

        edited_df = st.data_editor(
            df,
            key=f"statement_editor_{st.session_state['statement_run']}",
            width="stretch",
            hide_index=True,
            num_rows="dynamic",
            column_config={

                "Date":
                    st.column_config.TextColumn(
                        "Date"
                    ),

                "Description":
                    st.column_config.TextColumn(
                        "Description"
                    ),

                "Debit":
                    st.column_config.NumberColumn(
                        "Debit",
                        format="$%.2f"
                    ),

                "Credit":
                    st.column_config.NumberColumn(
                        "Credit",
                        format="$%.2f"
                    )
            }
        )

        debit_total = round(
            float(
                edited_df[
                    "Debit"
                ].sum()
            ),
            2
        )

        credit_total = round(
            float(
                edited_df[
                    "Credit"
                ].sum()
            ),
            2
        )

        debit_count = int(
            (
                edited_df[
                    "Debit"
                ] > 0
            ).sum()
        )

        credit_count = int(
            (
                edited_df[
                    "Credit"
                ] > 0
            ).sum()
        )

        transaction_count = (
            len(edited_df)
        )

        st.divider()

        st.header(
            "Statement Control"
        )

        col1, col2, col3 = (
            st.columns(3)
        )

        col1.metric(
            "Transactions",
            transaction_count
        )

        col2.metric(
            "Total Debits",
            f"${debit_total:,.2f}"
        )

        col3.metric(
            "Total Credits",
            f"${credit_total:,.2f}"
        )

        st.write(
            f"Extracted Debits: "
            f"{debit_count} transactions"
        )

        st.write(
            f"Extracted Credits: "
            f"{credit_count} transactions"
        )

        reconciled = False


        # =================================================
        # STATEMENT RECONCILIATION
        # =================================================

        if statement_info["statement_type"] == "chequing":
            checks, reconciled = reconcile_dedicated_deposit(edited_df, statement_info)
        else:
            checks, reconciled = reconcile_credit_card(edited_df, statement_info)
        if checks:
            st.table(pd.DataFrame(
                [(label, expected, actual) for label, expected, actual, _ in checks],
                columns=["Check", "Statement", "BankBridge"],
            ))
        if reconciled:
            st.success("Statement reconciles.")
        else:
            st.error("Transactions must match the printed statement controls before export.")

        # =================================================
        # DOWNLOADS
        # =================================================

        st.divider()

        st.header(
            "Download QuickBooks Files"
        )

        if reconciled:

            st.success(
                "Statement verified. "
                "Choose your QuickBooks format."
            )

            csv_data = (
                generate_quickbooks_csv(
                    edited_df
                )
            )

            qbo_data, note = make_qbo(edited_df, statement_info, st.session_state.get("processed_account_type"))
            if note:
                st.info(note)

            col1, col2 = (
                st.columns(2)
            )

            with col1:

                st.download_button(
                    label=(
                        "Download QuickBooks CSV"
                    ),
                    data=csv_data,
                    file_name=(
                        "quickbooks_transactions.csv"
                    ),
                    mime="text/csv",
                    use_container_width=True
                )

            with col2:

                if qbo_data is not None:
                    st.download_button(
                        label="Download QuickBooks QBO",
                        data=qbo_data.encode("cp1252", errors="replace"),
                        file_name="quickbooks_webconnect.qbo",
                        mime="application/x-ofx",
                        use_container_width=True
                    )
                else:
                    st.button("Download QuickBooks QBO (CIBC pending)", disabled=True, use_container_width=True)

        else:

            st.warning(
                "Downloads are disabled until "
                "the statement reconciles."
            )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "Tax Square Professional Corporation"
)
