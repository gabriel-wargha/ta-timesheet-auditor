"""
generate_data.py - makes fake TA timesheet data.

Creates daily timesheet entries for 50 fake teaching assistants (TAs)
over 7 weekly pay periods and saves them to data/timesheets.csv.

Right now (Block 1) every entry is clean and normal. In Block 2 we plant
problems on purpose (duplicates, late submissions, and so on), so we can
prove later that the audit catches every one of them.

Run it from the project folder:
    python generate_data.py
"""

import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Settings. Change these to get a different amount or shape of fake data.
# ---------------------------------------------------------------------------

# The seed makes the "random" choices come out the same on every run, so the
# CSV is identical each time. That lets our tests expect exact results.
RANDOM_SEED = 42

NUM_TAS = 50
NUM_WEEKS = 7

# Pay periods are weekly, Monday to Sunday. This is the first Monday.
FIRST_PAY_PERIOD_START = date(2026, 9, 14)

# Save next to this script, so it works no matter which folder you run it from.
PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = PROJECT_DIR / "data" / "timesheets.csv"

# Fake names only. Each TA gets a random first name + last name from these.
FIRST_NAMES = [
    "Ava", "Ben", "Chloe", "Daniel", "Emma", "Ethan", "Grace", "Hannah",
    "Isaac", "Jacob", "Kate", "Liam", "Lucy", "Mason", "Mia", "Noah",
    "Olivia", "Owen", "Sophie", "Tyler",
]
LAST_NAMES = [
    "Adams", "Baker", "Carter", "Dixon", "Ellis", "Foster", "Grant", "Hayes",
    "Irwin", "Jensen", "Keller", "Larsen", "Monroe", "Nash", "Ortiz", "Parker",
    "Quinn", "Reyes", "Shaw", "Turner",
]
COURSE_CODES = ["CSE 110", "CSE 111", "CSE 210", "CSE 212", "CSE 340", "CIT 111"]

# Days a TA can work, counted from Monday: 0 = Monday ... 5 = Saturday.
WORKDAY_OFFSETS = [0, 1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# Building the data
# ---------------------------------------------------------------------------

def make_tas():
    """Create the fake TAs. Each one has a regular schedule they mostly keep."""
    all_names = [f"{first} {last}" for first in FIRST_NAMES for last in LAST_NAMES]
    names = random.sample(all_names, NUM_TAS)  # sample() never picks the same name twice

    tas = []
    for number, name in enumerate(names, start=1):
        days_per_week = random.randint(4, 5)
        tas.append({
            "ta_id": f"TA{number:03d}",  # TA001, TA002, ... (:03d pads with zeros)
            "ta_name": name,
            "course_code": random.choice(COURSE_CODES),
            # Which days this TA usually works, e.g. [0, 2, 4] = Mon, Wed, Fri
            "work_days": sorted(random.sample(WORKDAY_OFFSETS, days_per_week)),
            # A typical shift length, so one TA's weeks look alike
            "usual_hours": random.choice([2.0, 2.5, 3.0]),
        })
    return tas


def pay_period_for_week(week_number):
    """Return the (start, end) dates of a pay period. Week 1 is the first one."""
    start = FIRST_PAY_PERIOD_START + timedelta(weeks=week_number - 1)
    end = start + timedelta(days=6)  # Monday + 6 days = Sunday
    return start, end


def make_submission_time(period_end):
    """Pick an on-time submission between Sunday 6:00 PM and Monday 10:59 PM.

    The deadline is Monday 11:59 PM, so every time picked here is on time.
    Late submissions are planted on purpose in Block 2.
    """
    earliest = datetime.combine(period_end, time(18, 0))  # Sunday 6:00 PM
    minutes_later = random.randint(0, 29 * 60 - 1)  # up to 29 hours later
    return earliest + timedelta(minutes=minutes_later)


def make_week_entries(ta, week_number):
    """Create one TA's daily entries for one pay period."""
    period_start, period_end = pay_period_for_week(week_number)
    submitted_at = make_submission_time(period_end)  # one submission per week

    entries = []
    for day_offset in ta["work_days"]:
        # Shifts change a little from week to week, in half-hour steps.
        hours = ta["usual_hours"] + random.choice([-0.5, 0.0, 0.0, 0.5])
        entries.append({
            "ta_id": ta["ta_id"],
            "ta_name": ta["ta_name"],
            "course_code": ta["course_code"],
            "entry_date": period_start + timedelta(days=day_offset),
            "hours": hours,
            "submitted_at": submitted_at,
            "pay_period_start": period_start,
            "pay_period_end": period_end,
        })
    return entries


def make_clean_entries(tas):
    """Create every normal entry: all TAs, all weeks."""
    entries = []
    for week_number in range(1, NUM_WEEKS + 1):
        for ta in tas:
            entries.extend(make_week_entries(ta, week_number))
    return entries


def main():
    random.seed(RANDOM_SEED)

    tas = make_tas()
    entries = make_clean_entries(tas)

    # A DataFrame is pandas' table: one row per entry, one column per field.
    df = pd.DataFrame(entries)

    OUTPUT_FILE.parent.mkdir(exist_ok=True)  # create the data/ folder if it's missing
    df.to_csv(OUTPUT_FILE, index=False)  # index=False: don't save pandas' row numbers

    print(f"Saved {len(df):,} entries for {df['ta_id'].nunique()} TAs to {OUTPUT_FILE}")
    print(f"Dates: {df['entry_date'].min()} to {df['entry_date'].max()}")
    print()
    print(df.head().to_string())


# Run main() only when this file is run directly (python generate_data.py),
# not when another file imports it.
if __name__ == "__main__":
    main()
