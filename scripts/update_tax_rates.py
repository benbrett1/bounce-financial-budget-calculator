"""
Scrapes current Australian individual income tax rates from the ATO website
and updates tax-rates.json. Run every July 1 via GitHub Actions.
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ATO_URL = "https://www.ato.gov.au/rates/individual-income-tax-rates/"
OUTPUT = Path(__file__).parent.parent / "tax-rates.json"

# Hardcoded offsets/medicare — these rarely change and need manual review if they do
LITO = {
    "max_offset": 700,
    "phase_out": [
        {"from": 37500, "to": 45000, "rate": 0.05},
        {"from": 45000, "to": 66667, "rate": 0.015}
    ]
}
MEDICARE = {
    "rate": 0.02,
    "low_income_threshold": 26000,
    "shade_in_rate": 0.10,
    "shade_in_ceiling": 32500
}


def parse_dollars(text):
    return int(re.sub(r"[^\d]", "", text)) if re.search(r"\d", text) else None


def parse_rate(text):
    match = re.search(r"([\d.]+)c", text)
    if match:
        return round(float(match.group(1)) / 100, 4)
    match = re.search(r"([\d.]+)%", text)
    if match:
        return round(float(match.group(1)) / 100, 4)
    return 0.0


def scrape_brackets():
    resp = requests.get(ATO_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Find the resident rates table — look for a table containing "18,200" threshold
    tables = soup.find_all("table")
    target = None
    for table in tables:
        if "18,200" in table.get_text():
            target = table
            break

    if not target:
        raise ValueError("Could not find tax bracket table on ATO page")

    brackets = []
    rows = target.find_all("tr")[1:]  # skip header
    for row in rows:
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue

        income_text = cells[0]
        tax_text = cells[1]

        # Parse income range
        numbers = re.findall(r"[\d,]+", income_text)
        if not numbers:
            continue
        min_val = parse_dollars(numbers[0])

        # Parse base tax (e.g. "Nil", "$5,092 plus...")
        base = 0
        base_match = re.search(r"\$([\d,]+)", tax_text)
        if base_match:
            base = parse_dollars(base_match.group(1))

        rate = parse_rate(tax_text)

        brackets.append({"min": min_val, "base": base, "rate": rate})

    # Sort and set max values
    brackets.sort(key=lambda b: b["min"])
    for i, b in enumerate(brackets):
        b["max"] = brackets[i + 1]["min"] if i + 1 < len(brackets) else None

    return brackets


def current_financial_year():
    today = date.today()
    start_year = today.year if today.month >= 7 else today.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def main():
    print(f"Fetching tax rates from {ATO_URL}...")
    try:
        brackets = scrape_brackets()
    except Exception as e:
        print(f"ERROR: Failed to scrape ATO — {e}", file=sys.stderr)
        print("Keeping existing tax-rates.json unchanged.")
        sys.exit(1)

    fy = current_financial_year()
    data = {
        "financial_year": fy,
        "last_updated": date.today().isoformat(),
        "source": ATO_URL,
        "brackets": brackets,
        "lito": LITO,
        "medicare": MEDICARE
    }

    with open(OUTPUT, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Updated tax-rates.json for {fy} with {len(brackets)} brackets:")
    for b in brackets:
        top = f"${b['max']:,}" if b["max"] else "+"
        print(f"  ${b['min']:,} – {top}: base ${b['base']:,} + {b['rate']*100:.1f}c")


if __name__ == "__main__":
    main()
