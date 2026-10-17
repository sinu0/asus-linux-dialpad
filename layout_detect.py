"""Which layout fits this laptop, for a driver started without one.

Packages cannot ask which laptop they run on, so their service starts the
driver with the layout ``auto``. The answer comes from the same table the
installer uses (``laptop_touchpad_dialpad_layouts.csv``): first the laptop's
product name, then the touchpad's vendor and product id. Unknown laptops get
``FALLBACK`` and are measured with the guided calibration.
"""

import csv
import re
from pathlib import Path

AUTO = "auto"
FALLBACK = "proartp16"
TABLE = Path(__file__).resolve().parent / "laptop_touchpad_dialpad_layouts.csv"


def choose_layout(rows, product_name, touchpads, available):
    """Pick a layout from table rows.

    ``rows`` are dicts with the CSV columns, ``touchpads`` (vendor, product)
    hex pairs of the touchpads present, ``available`` the layout names that
    exist. Among several matching rows the one reported most often wins.
    Returns ``None`` when nothing matches.
    """
    def best(matching):
        matching = [row for row in matching if row.get("Base layout") in available]
        if not matching:
            return None
        return max(matching, key=lambda row: int(row.get("Event count") or 0))["Base layout"]

    product_name = (product_name or "").strip()
    by_name = best(row for row in rows if product_name and row.get("Laptop", "").strip() == product_name)
    if by_name:
        return by_name
    ids = {(vendor.lower(), product.lower()) for vendor, product in touchpads}
    return best(
        row for row in rows
        if (row.get("Vendor ID", "").lower(), row.get("Product ID", "").lower()) in ids
    )


def touchpad_ids(devices_text):
    """(vendor, product) of every touchpad listed in /proc/bus/input/devices."""
    ids = []
    for block in devices_text.split("\n\n"):
        name = re.search(r'^N: Name="([^"]*)"', block, re.M)
        info = re.search(r"^I: .*Vendor=([0-9a-fA-F]+) Product=([0-9a-fA-F]+)", block, re.M)
        if name and info and "touchpad" in name.group(1).lower():
            ids.append((info.group(1), info.group(2)))
    return ids


def detect_layout(layouts_dir):
    """The layout for this laptop, or FALLBACK."""
    return find_layout(layouts_dir) or FALLBACK


def find_layout(layouts_dir):
    """The layout the table lists for this laptop, or ``None``."""
    available = {path.stem for path in Path(layouts_dir).glob("*.py") if not path.stem.startswith("_")}

    def read(path):
        try:
            return Path(path).read_text(errors="ignore")
        except OSError:
            return ""

    try:
        with open(TABLE, newline="") as table:
            rows = list(csv.DictReader(table))
    except OSError:
        rows = []
    return choose_layout(
        rows,
        read("/sys/devices/virtual/dmi/id/product_name"),
        touchpad_ids(read("/proc/bus/input/devices")),
        available,
    )


if __name__ == "__main__":
    # Used by install_layout_auto_suggestion.sh; prints nothing when unknown.
    print(find_layout(Path(__file__).resolve().parent / "layouts") or "")
