import os
import re

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

SCHEDULE_PAGE_URL = "https://cs.msu.ru/studies/schedule"
BASE_URL = "https://cs.msu.ru"

# Only files matching this pattern share the weekly-grid layout that
# schedule.grid_parser understands. Other schedule-page PDFs (masters
# elective listing, week-parity chart, attendance policy) are different
# documents and are intentionally not auto-downloaded here.
GRID_FILE_RE = re.compile(r"^(\d+_kurs_osen|im_\d+_kurs_osen).*\.pdf$", re.IGNORECASE)


class Command(BaseCommand):
    help = (
        "Download the weekly-grid schedule PDFs published at "
        f"{SCHEDULE_PAGE_URL} (1-4 kurs + integrated masters) into --out-dir. "
        "Does not parse or import them - see import_schedule_grid."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--out-dir", type=str, default=None,
            help="Destination directory (default: schedule/schedule_sources/ under BASE_DIR)",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Re-download even if a file with the same name already exists",
        )

    def handle(self, *args, **options):
        out_dir = options.get("out_dir") or os.path.join(settings.BASE_DIR, "schedule", "schedule_sources")
        os.makedirs(out_dir, exist_ok=True)

        self.stdout.write(f"Fetching {SCHEDULE_PAGE_URL} ...")
        try:
            resp = requests.get(SCHEDULE_PAGE_URL, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            self.stderr.write(self.style.ERROR(f"Failed to fetch schedule page: {e}"))
            return

        hrefs = set(re.findall(r'href="([^"]+\.pdf)"', resp.text))
        grid_links = sorted(h for h in hrefs if GRID_FILE_RE.match(os.path.basename(h)))

        if not grid_links:
            self.stderr.write(self.style.WARNING("No matching grid-schedule PDF links found on the page."))
            return

        self.stdout.write(f"Found {len(grid_links)} grid-schedule file(s):")
        downloaded, skipped, failed = [], [], []

        for href in grid_links:
            url = href if href.startswith("http") else BASE_URL + href
            filename = os.path.basename(href)
            dest = os.path.join(out_dir, filename)

            if os.path.exists(dest) and not options.get("force"):
                self.stdout.write(f"  = {filename} (already exists, skipping)")
                skipped.append(filename)
                continue

            try:
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                with open(dest, "wb") as f:
                    f.write(r.content)
                self.stdout.write(self.style.SUCCESS(f"  + {filename} ({len(r.content):,} bytes)"))
                downloaded.append(filename)
            except requests.RequestException as e:
                self.stderr.write(self.style.ERROR(f"  ! {filename}: {e}"))
                failed.append(filename)

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Downloaded {len(downloaded)}, skipped {len(skipped)}, failed {len(failed)}. "
            f"Files in {out_dir}"
        ))
