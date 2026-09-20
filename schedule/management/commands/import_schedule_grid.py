import logging
import os
import re
import time
from collections import defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError, OperationalError

from main.models import Group
from schedule.grid_parser import parse_grid_file
from schedule.models import Schedule, Subject

DAY_CHOICES = {d.lower(): d for d, _ in Schedule.DAYS}  # 'понедельник' -> 'Понедельник'
LEADING_DIGITS_RE = re.compile(r"^\d+")

logger = logging.getLogger(__name__)

# Database lock retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds


def retry_on_lock(func, max_retries=MAX_RETRIES):
    """Retry a database operation if it fails due to lock or operational errors."""
    for attempt in range(max_retries):
        try:
            return func()
        except (OperationalError, IntegrityError) as e:
            if attempt < max_retries - 1:
                wait_time = RETRY_DELAY * (2 ** attempt)
                logger.warning(f"Database error (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {str(e)}")
                time.sleep(wait_time)
            else:
                raise


def get_or_create_subject(subject_name, created_subjects, stdout_write=None):
    """Get or create a subject by name, with in-session duplicate prevention."""
    if not subject_name:
        return None

    subject_name = subject_name.strip()
    subject_key = subject_name.lower()

    if subject_key in created_subjects:
        return created_subjects[subject_key]

    try:
        subject, created = Subject.objects.get_or_create(name__iexact=subject_name, defaults={'name': subject_name})
        msg = f'{"✓ Created new" if created else "✓ Found existing"} subject: {subject.name}'
        if stdout_write:
            stdout_write(msg)
        created_subjects[subject_key] = subject
        return subject
    except Subject.MultipleObjectsReturned:
        subject = Subject.objects.filter(name__iexact=subject_name).first()
        msg = f'⚠ Multiple subjects found for "{subject_name}", using first match'
        if stdout_write:
            stdout_write(msg)
        created_subjects[subject_key] = subject
        return subject
    except Exception as e:
        error_msg = f'❌ Error creating subject {subject_name}: {str(e)}'
        if stdout_write:
            stdout_write(error_msg)
        else:
            print(error_msg)
        return None


class Command(BaseCommand):
    help = (
        "Import the weekly-grid schedule files (xlsx/pdf, see schedule.grid_parser) "
        "into Group/Subject/Schedule. Defaults to a dry run (parses and reports "
        "counts, writes nothing) - pass --commit to actually write to the database."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dir", type=str, default=None,
            help="Directory of .xlsx/.pdf files to import (default: schedule/schedule_sources/)",
        )
        parser.add_argument("--files", nargs="+", default=None, help="Explicit list of files instead of --dir")
        parser.add_argument("--faculty", type=str, default="ВМК", help="Faculty name for created groups")
        parser.add_argument(
            "--commit", action="store_true",
            help="Actually write to the database. Without this flag, only a summary is printed.",
        )

    def handle(self, *args, **options):
        commit = options["commit"]
        faculty = options["faculty"]

        if options.get("files"):
            files = [os.path.abspath(f) for f in options["files"]]
        else:
            src_dir = options.get("dir") or os.path.join(settings.BASE_DIR, "schedule", "schedule_sources")
            if not os.path.isdir(src_dir):
                self.stderr.write(self.style.ERROR(f"Directory not found: {src_dir}"))
                return
            files = sorted(
                os.path.join(src_dir, f) for f in os.listdir(src_dir)
                if f.lower().endswith((".xlsx", ".xlsm", ".pdf"))
            )

        if not files:
            self.stderr.write(self.style.WARNING("No .xlsx/.pdf files found to import."))
            return

        if not commit:
            self.stdout.write(self.style.WARNING("DRY RUN - no database writes. Pass --commit to apply.\n"))

        all_created_subjects = {}
        group_cache = {}

        total_rows = 0
        imported_rows = 0
        skipped_empty = 0
        truncated_group_labels = set()
        unparsed_detail_rows = []
        errors = []

        for filepath in files:
            filename = os.path.basename(filepath)
            self.stdout.write(f"\n=== {filename} ===")
            try:
                rows = parse_grid_file(filepath)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  Failed to parse {filename}: {e}"))
                errors.append((filename, str(e)))
                continue

            self.stdout.write(f"  parsed {len(rows)} lesson cells")
            total_rows += len(rows)

            # lesson_number = order of first occurrence per (group_label, day), which
            # matches the source's top-to-bottom (i.e. chronological) row order.
            lesson_counters = defaultdict(int)

            for row in rows:
                subject_raw = row["subject_raw"].strip()
                if not subject_raw:
                    skipped_empty += 1
                    continue
                if row["detail_raw"] and not row["teachers"]:
                    unparsed_detail_rows.append((filename, row["group"], row["day"], row["detail_raw"]))

                group_label = row["group"]
                if not group_label.isdigit():
                    # Suffixed labels ("111ио", "541/1") don't fit Group.number
                    # (plain IntegerField) without losing the specialization code -
                    # skip rather than silently collapsing distinct groups together.
                    truncated_group_labels.add(group_label)
                    continue
                group_number = int(group_label)

                day_key = row["day"].strip().lower()
                day_display = DAY_CHOICES.get(day_key)
                if not day_display:
                    errors.append((filename, f"Unknown day '{row['day']}' for group {group_label}"))
                    continue

                lesson_counters[(group_number, day_display)] += 1
                lesson_number = lesson_counters[(group_number, day_display)]

                teachers = row["teachers"]
                primary = teachers[0] if teachers else None
                secondary = teachers[1] if len(teachers) > 1 else None

                classroom = ""
                if primary:
                    classroom = ", ".join(primary["rooms"]) or ", ".join(primary["subgroup"])
                another_classroom = ""
                if secondary:
                    another_classroom = ", ".join(secondary["rooms"]) or ", ".join(secondary["subgroup"])

                imported_rows += 1

                if not commit:
                    continue

                try:
                    if group_number not in group_cache:
                        group, _ = retry_on_lock(lambda: Group.objects.get_or_create(
                            number=group_number,
                            faculty=faculty,
                            defaults={},
                        ))
                        group_cache[group_number] = group
                    group = group_cache[group_number]

                    # Teacher names are entered directly into the schedule as text -
                    # no portal account is created for them.
                    teacher_names = [entry["name"] for entry in (primary, secondary) if entry and entry["name"]]

                    subject = retry_on_lock(lambda: get_or_create_subject(
                        subject_name=subject_raw,
                        created_subjects=all_created_subjects, stdout_write=None,
                    ))

                    if not subject:
                        errors.append((filename, f"Could not create subject '{subject_raw}'"))
                        continue

                    schedule_data = {
                        "faculty": faculty,
                        "time": row["time_start"],
                        "time_end": row["time_end"],
                        "subject": subject,
                        "classroom": classroom,
                        "another_classroom": another_classroom,
                        "first_teacher_id": "",
                        "first_teacher_name": teacher_names[0] if teacher_names else "",
                        "week_parity": "all",
                    }
                    if len(teacher_names) > 1:
                        schedule_data["second_teacher_id"] = ""
                        schedule_data["second_teacher_name"] = teacher_names[1]

                    retry_on_lock(lambda: Schedule.objects.update_or_create(
                        group=group, day=day_display, lesson_number=lesson_number,
                        defaults=schedule_data,
                    ))
                except Exception as e:
                    errors.append((filename, f"group {group_label} {day_display} #{lesson_number}: {e}"))

        self.stdout.write(self.style.SUCCESS(
            f"\n{'IMPORTED' if commit else 'WOULD IMPORT'} {imported_rows}/{total_rows} lesson rows "
            f"({skipped_empty} empty cells skipped)"
        ))
        if truncated_group_labels:
            self.stdout.write(self.style.WARNING(
                f"\n{len(truncated_group_labels)} group label(s) are not plain numbers and were SKIPPED "
                f"(Group.number can't hold a specialization suffix without merging distinct groups):\n  "
                + ", ".join(sorted(truncated_group_labels))
            ))
        if unparsed_detail_rows:
            self.stdout.write(self.style.WARNING(
                f"\n{len(unparsed_detail_rows)} row(s) had detail text that produced no teacher entries "
                f"(check manually), e.g.: {unparsed_detail_rows[0]}"
            ))
        if errors:
            self.stdout.write(self.style.ERROR(f"\n{len(errors)} error(s):"))
            for filename, msg in errors[:20]:
                self.stdout.write(f"  {filename}: {msg}")
        if commit:
            self.stdout.write(self.style.SUCCESS(
                f"\nSubjects created/found: {len(all_created_subjects)}  "
                f"Groups touched: {len(group_cache)}"
            ))

