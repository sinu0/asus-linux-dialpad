#!/usr/bin/env python3
"""Regenerate the README pictures in preview/, keeping files that did not change.

Renders every picture into a temporary directory (the on-screen dial with
tools/render_overlay_preview.js, the settings app with
tools/screenshot_settings.py, which briefly opens a window) and compares
each with the committed one. Rendering is not bit-exact between runs
(blurred and dithered backgrounds differ by a few levels), so a picture only
counts as changed when enough pixels differ by more than a tolerance;
otherwise the committed file stays untouched and git sees no change.

    python3 tools/update_previews.py           # replace the changed pictures
    python3 tools/update_previews.py --check   # only report; exit 1 if any changed

tools/git-hooks/pre-push runs the --check form before every push once
enabled with: git config core.hooksPath tools/git-hooks
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "preview"

# A channel difference above TOLERANCE is a real change; rendering noise
# stays below 8. MIN_PIXELS ignores a handful of anti-aliased edge pixels.
TOLERANCE = 12
MIN_PIXELS = 25


def render(output: Path) -> None:
    subprocess.run(["gjs", "-m", str(ROOT / "tools" / "render_overlay_preview.js"), str(output)],
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(ROOT / "tools" / "screenshot_settings.py"), str(output)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def changed_pixels(old: Path, new: Path) -> int | None:
    """Pixels that differ by more than TOLERANCE; None when the size differs."""
    a = Image.open(old).convert("RGB")
    b = Image.open(new).convert("RGB")
    if a.size != b.size:
        return None
    # The largest channel difference of each pixel, then a threshold.
    difference = ImageChops.difference(a, b)
    largest = ImageChops.lighter(ImageChops.lighter(*difference.split()[:2]), difference.split()[2])
    mask = largest.point(lambda value: 255 if value > TOLERANCE else 0)
    return mask.histogram()[255]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report outdated pictures without writing")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="turnpad-previews-") as directory:
        output = Path(directory)
        render(output)
        outdated = []
        for new in sorted(output.glob("*.png")):
            old = PREVIEW / new.name
            if not old.exists():
                status, differs = "new", True
            else:
                pixels = changed_pixels(old, new)
                differs = pixels is None or pixels >= MIN_PIXELS
                status = "size changed" if pixels is None else f"{pixels} pixels differ"
            if differs:
                outdated.append(new.name)
                if not args.check:
                    shutil.copyfile(new, old)
            print(f"{'changed ' if differs else 'same    '} {new.name} ({status})")

    if args.check and outdated:
        print(f"\n{len(outdated)} picture(s) in preview/ are outdated; run: python3 tools/update_previews.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
