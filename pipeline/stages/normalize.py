import csv
import re
from pathlib import Path

from pipeline.config import OPTION_SKU_BASE
from pipeline.model import Order

SO_HEADERS = [
    "Flag", "SONum", "Status", "CustomerName", "CustomerContact",
    "BillToName", "BillToAddress", "BillToCity", "BillToState", "BillToZip",
    "BillToCountry", "ShipToName", "ShipToAddress", "ShipToCity",
    "ShipToState", "ShipToZip", "ShipToCountry", "ShipToResidential",
    "CarrierName", "TaxRateName", "PriorityId", "PONum", "VendorPONum",
    "Date", "Salesman", "ShippingTerms", "PaymentTerms", "FOB", "Note",
    "QuickBooksClassName", "LocationGroupName", "OrderDateScheduled", "URL",
    "CarrierService", "DateExpired", "Phone", "Email", "Category",
    "CF-Bill To Email (AP)", "CF-Ship To Email",
    "CF-Ship To Company/Organization", "CF-Check Ice, Tax, Surcharge, HLA and Total?",
]

ITEM_HEADERS = [
    "Flag", "SOItemTypeID", "ProductNumber", "ProductDescription",
    "ProductQuantity", "UOM", "ProductPrice", "Taxable", "TaxCode", "Note",
    "ItemQuickBooksClassName", "ItemDateScheduled", "ShowItem", "KitItem",
    "RevisionLevel", "CustomerPartNumber",
]

SALESMAN = ""
LOCATION_GROUP = "Main"
SHIPPING_TERMS = "Prepaid & Billed"
PAYMENT_TERMS = "NET 30"
FOB = "Origin"
STATUS = "20"
SO_ITEM_TYPE_SALE = "10"
SO_ITEM_TYPE_KIT = "80"
UOM = "ea"
PRIORITY_ID = "30"
TAX_RATE_NAME = "None"
STATE_ABBREVIATIONS = {
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "ARIZONA": "AZ",
    "ARKANSAS": "AR",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "CONNECTICUT": "CT",
    "DELAWARE": "DE",
    "FLORIDA": "FL",
    "GEORGIA": "GA",
    "HAWAII": "HI",
    "IDAHO": "ID",
    "ILLINOIS": "IL",
    "INDIANA": "IN",
    "IOWA": "IA",
    "KANSAS": "KS",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM",
    "NEW YORK": "NY",
    "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN",
    "TEXAS": "TX",
    "UTAH": "UT",
    "VERMONT": "VT",
    "VIRGINIA": "VA",
    "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI",
    "WYOMING": "WY",
    "DISTRICT OF COLUMBIA": "DC",
}


def order_to_csv(order: Order, out_path: Path) -> Path:
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_pad(SO_HEADERS))
        writer.writerow(_pad(ITEM_HEADERS))
        _write_so_row(writer, order)
        _write_item_rows(writer, order)
    return out_path


def _pad(row: list) -> list:
    return list(row) + [""] * (len(SO_HEADERS) - len(row))


def _write_so_row(writer, order: Order):
    row = [""] * len(SO_HEADERS)
    row[0] = "SO"
    row[1] = ""
    row[2] = STATUS
    row[3] = order.customer_name
    row[4] = order.customer_contact
    row[5] = order.billing.name or order.customer_name
    row[6] = order.billing.street
    row[7] = order.billing.city
    row[8] = _normalize_state(order.billing.state)
    row[9] = order.billing.zip_code
    row[10] = order.billing.country
    row[11] = order.shipping.name or order.customer_name
    row[12] = order.shipping.street
    row[13] = order.shipping.city
    row[14] = _normalize_state(order.shipping.state)
    row[15] = order.shipping.zip_code
    row[16] = order.shipping.country
    row[17] = "FALSE"
    row[18] = order.carrier
    row[19] = TAX_RATE_NAME
    row[20] = PRIORITY_ID
    row[21] = order.order_number
    row[22] = ""
    row[23] = order.date
    row[24] = SALESMAN
    row[25] = SHIPPING_TERMS
    row[26] = PAYMENT_TERMS
    row[27] = FOB
    row[28] = order.note
    row[29] = "None"
    row[30] = LOCATION_GROUP
    row[31] = order.date
    row[32] = ""
    row[33] = ""
    row[34] = ""
    row[35] = order.phone
    row[36] = order.email
    row[37] = ""
    row[38] = order.email
    row[39] = order.email
    row[40] = ""
    row[41] = "Yes - I have checked"
    writer.writerow(row)


def _write_item_rows(writer, order: Order):
    has_kits = _detect_kits(order)
    for idx, line in enumerate(order.lines):
        row = [""] * len(ITEM_HEADERS)
        row[0] = "Item"
        if has_kits and idx == 0:
            row[1] = SO_ITEM_TYPE_KIT
        else:
            row[1] = SO_ITEM_TYPE_SALE
        row[2] = _normalize_sku(line)
        row[3] = line.description
        row[4] = str(line.quantity)
        row[5] = UOM
        row[6] = str(line.unit_price) if line.unit_price > 0 else "0"
        row[7] = "TRUE"
        row[8] = ""
        row[9] = line.note
        row[10] = ""
        row[11] = order.date
        row[12] = "TRUE" if not has_kits or idx == 0 else "FALSE"
        row[13] = "TRUE" if has_kits and idx > 0 else "FALSE"
        row[14] = ""
        row[15] = ""
        writer.writerow(_pad(row))


def _normalize_sku(line) -> str:
    sku = line.sku.strip()
    selected_option = line.selected_option.strip()

    if selected_option:
        match = re.search(r"Cat#\s*([A-Za-z0-9-]+)", selected_option, re.IGNORECASE)
        if match:
            return match.group(1)

    if OPTION_SKU_BASE and sku == OPTION_SKU_BASE:
        if re.search(r"\b24\b", selected_option):
            return f"{OPTION_SKU_BASE}-24"
        if re.search(r"\b48\b", selected_option):
            return f"{OPTION_SKU_BASE}-48"
        if re.search(r"\b96\b", selected_option):
            return f"{OPTION_SKU_BASE}-96"

    parts = sku.split("-")
    if len(parts) > 1 and parts[0] == parts[1]:
        return "-".join(parts[1:])

    return sku


def _detect_kits(order: Order) -> bool:
    return False


def _normalize_state(state: str) -> str:
    value = state.strip()
    if len(value) <= 2:
        return value.upper()
    return STATE_ABBREVIATIONS.get(value.upper(), value)
