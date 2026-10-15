"""Extract the pricing oracle from the original XLSX (stdlib only, no app imports).

Usage: python scripts/extract_pricing_reference.py [--check]

The fixture includes the workbook SHA-256, authored formulas, cached values and
independently evaluated scenarios. Only cell references, decimal literals,
+ - * / parentheses and SUM(cell:cell) are supported; unsupported formulas fail
closed. No eval(), JavaScript prices or binary-float monetary arithmetic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from decimal import Decimal, localcontext
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "قیمت نهایی.xlsx"
FIXTURE = ROOT / "frontend/tests/fixtures/pricing-workbook.json"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_cells() -> tuple[dict[str, str], dict[str, str]]:
    with zipfile.ZipFile(WORKBOOK) as archive:
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    values, formulas = {}, {}
    for cell in sheet.findall(".//s:sheetData/s:row/s:c", NS):
        if cell.get("t") in ("s", "inlineStr"):
            continue
        address = cell.attrib["r"]
        value, formula = cell.find("s:v", NS), cell.find("s:f", NS)
        if value is not None and value.text:
            values[address] = value.text
        if formula is not None and formula.text:
            formulas[address] = formula.text
    return values, formulas


def evaluate(values: dict[str, str], formulas: dict[str, str]) -> dict[str, str]:
    cache: dict[str, Decimal] = {}
    active: set[str] = set()

    def cell(address: str) -> Decimal:
        if address in cache:
            return cache[address]
        if address in active:
            raise ValueError(f"cyclic reference: {address}")
        active.add(address)
        result = expression(formulas[address]) if address in formulas else Decimal(values[address])
        active.remove(address)
        cache[address] = result
        return result

    def expression(source: str) -> Decimal:
        def expand_sum(match: re.Match[str]) -> str:
            column, start, end = match.groups()
            return "(" + "+".join(f"{column}{i}" for i in range(int(start), int(end) + 1)) + ")"

        source = re.sub(r"SUM\(([A-Z]+)(\d+):\1(\d+)\)", expand_sum, source)
        tokens = re.findall(r"[A-Z]+\d+|\d+(?:\.\d+)?|[()+*/-]", source)
        if "".join(tokens) != re.sub(r"\s", "", source):
            raise ValueError(f"unsupported formula: {source}")
        index = 0

        def atom() -> Decimal:
            nonlocal index
            token = tokens[index]
            index += 1
            if token == "(":
                result = addition()
                if tokens[index] != ")":
                    raise ValueError("missing closing parenthesis")
                index += 1
                return result
            return cell(token) if token[0].isalpha() else Decimal(token)

        def product() -> Decimal:
            nonlocal index
            result = atom()
            while index < len(tokens) and tokens[index] in ("*", "/"):
                operator = tokens[index]
                index += 1
                rhs = atom()
                result = result * rhs if operator == "*" else result / rhs
            return result

        def addition() -> Decimal:
            nonlocal index
            result = product()
            while index < len(tokens) and tokens[index] in ("+", "-"):
                operator = tokens[index]
                index += 1
                rhs = product()
                result = result + rhs if operator == "+" else result - rhs
            return result

        result = addition()
        if index != len(tokens):
            raise ValueError(f"unconsumed formula: {source}")
        return result

    with localcontext() as context:
        context.prec = 40
        return {address: format(cell(address), "f") for address in formulas}


def reference() -> dict[str, object]:
    values, formulas = read_cells()
    calculated = evaluate(values, formulas)
    for address in formulas:
        if Decimal(calculated[address]) != Decimal(values[address]):
            raise ValueError(f"cached Excel value differs from evaluated formula: {address}")
    cases = [
        ("workbook-example", {}),
        ("quantity-2", {"B15": "2"}),
        ("quantity-10", {"B15": "10"}),
        ("fractional-weight-time", {"B13": "12.5", "B14": "0.75", "B15": "3"}),
        ("zero-weight-time", {"B13": "0", "B14": "0", "B15": "2"}),
        ("unused-constants", {"B2": "99", "B7": "99", "B8": "99999"}),
        ("changed-costs", {"B3": "3250.125", "B6": "1.75", "B9": "9750.5", "B23": "7654.25"}),
    ]
    scenarios = []
    for name, overrides in cases:
        inputs = {k: v for k, v in values.items() if k not in formulas} | overrides
        scenarios.append({"name": name, "inputs": inputs, "expected": evaluate(inputs, formulas)})
    return {
        "source": WORKBOOK.name,
        "sha256": hashlib.sha256(WORKBOOK.read_bytes()).hexdigest(),
        "sheet": "Sheet1",
        "formulas": formulas,
        "cached": {k: values[k] for k in formulas},
        "scenarios": scenarios,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = json.dumps(reference(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not FIXTURE.is_file() or FIXTURE.read_text(encoding="utf-8") != content:
            print("Pricing fixture out of date: run python scripts/extract_pricing_reference.py")
            return 1
        print("Pricing fixture matches the XLSX formulas, cached values and SHA-256.")
    else:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(content, encoding="utf-8")
        print(f"Wrote {FIXTURE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
