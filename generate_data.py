"""
generate_data.py - makes fake TA timesheet data.

Creates daily timesheet entries for 50 fake teaching assistants (TAs)
over 7 weekly pay periods and saves them to data/timesheets.csv.

It works in two steps:
  1. Build clean, normal entries for every TA and every week.
  2. Plant known problems on purpose (duplicates, late submissions, and so
     on) and list each one in data/planted_issues.csv. Because we know
     exactly what we planted, we can later prove the audit catches it all.

Each planted problem goes to a different TA, so problems never overlap
and every one can be checked on its own.

Run it from the project folder:
    python generate_data.py
"""

import math
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
PLANTED_FILE = PROJECT_DIR / "data" / "planted_issues.csv"

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


# ---------------------------------------------------------------------------
# Helpers for planting problems
# ---------------------------------------------------------------------------

def week_rows(df, ta_id, week):
    """Return a mask: True for this TA's rows in this week, False for the rest.

    A mask is a Series of True/False, one per row. df[mask] or df.loc[mask]
    keeps only the True rows.
    """
    period_start, _ = pay_period_for_week(week)
    return (df["ta_id"] == ta_id) & (df["pay_period_start"] == period_start)


def week_hours(df, ta_id, week):
    """Total hours one TA logged in one week."""
    return df.loc[week_rows(df, ta_id, week), "hours"].sum()


# Problems that add hours only go into weeks 5 to 7. A spike earlier on,
# followed by normal weeks, would look like "hours dropping 3 weeks in a
# row", another problem we never planted.
LATE_WEEKS = range(5, NUM_WEEKS + 1)


def lightest_week(df, ta_id):
    """The TA's week with the fewest hours, out of weeks 5 to 7.

    Problems that add hours go into this week, so they don't also push the
    week over 20 hours by accident. That would plant a second problem we
    never wrote down.
    """
    return min(LATE_WEEKS, key=lambda week: week_hours(df, ta_id, week))


def random_row(df, ta_id, week):
    """Pick the row label of one random entry from this TA's week."""
    return random.choice(list(df.index[week_rows(df, ta_id, week)]))


def record(planted, ta_id, week, issue, details):
    """Write down one planted problem, so the tests can check it later."""
    planted.append({"ta_id": ta_id, "week": week, "issue": issue, "details": details})


# ---------------------------------------------------------------------------
# Planted problems. Each function takes the table, changes it, records what
# it did in `planted`, and returns the changed table.
# ---------------------------------------------------------------------------

def plant_duplicate(df, planted, ta_id):
    """Problem 1: the same entry saved twice (an exact copy of one row)."""
    week = lightest_week(df, ta_id)
    row = random_row(df, ta_id, week)
    copy = df.loc[[row]]  # double brackets keep it a one-row DataFrame
    df = pd.concat([df, copy], ignore_index=True)
    record(planted, ta_id, week, "Duplicate entry",
           f"{copy['entry_date'].iloc[0]} entered twice")
    return df


def plant_bad_hours(df, planted, ta_id, bad_value):
    """Problem 2: zero or negative hours (a typo such as -2 instead of 2)."""
    week = random.randint(2, NUM_WEEKS)
    row = random_row(df, ta_id, week)
    df.loc[row, "hours"] = bad_value
    record(planted, ta_id, week, "Zero or negative hours",
           f"{df.loc[row, 'entry_date']} logged {bad_value} hours")
    return df


def plant_long_day_single(df, planted, ta_id):
    """Problem 3a: one entry with more than 8 hours in a single day."""
    week = lightest_week(df, ta_id)
    row = random_row(df, ta_id, week)
    df.loc[row, "hours"] = 10.0
    record(planted, ta_id, week, "Over 8 hours in a day",
           f"{df.loc[row, 'entry_date']}: one entry of 10.0 hours")
    return df


def plant_long_day_split(df, planted, ta_id):
    """Problem 3b: two entries on the same date that add up to 9 hours.

    Neither entry is over 8 on its own, so the audit only catches this if it
    adds up each TA's hours per date first.
    """
    week = lightest_week(df, ta_id)
    row = random_row(df, ta_id, week)
    extra = df.loc[[row]].copy()
    extra["hours"] = 9.0 - df.loc[row, "hours"]  # the two entries total 9.0
    df = pd.concat([df, extra], ignore_index=True)
    record(planted, ta_id, week, "Over 8 hours in a day",
           f"{df.loc[row, 'entry_date']}: two entries totalling 9.0 hours")
    return df


def plant_long_week(df, planted, ta_id):
    """Problem 4: more than 20 hours in one week, with no single day over 8."""
    week = random.choice(LATE_WEEKS)
    mask = week_rows(df, ta_id, week)
    days = mask.sum()  # True counts as 1, so this counts the TA's entries
    # Spread about 22 hours over the days, rounded up to the next half hour.
    per_day = math.ceil(22 / days * 2) / 2
    df.loc[mask, "hours"] = per_day
    record(planted, ta_id, week, "Over 20 hours in a week",
           f"{days} days x {per_day} hours = {days * per_day} hours")
    return df


def plant_outside_period(df, planted, ta_id):
    """Problem 5: an entry dated outside its pay period.

    It moves to the Sunday before the period starts. Nobody works Sundays
    in this data, so it can't land on top of a real entry.
    """
    week = random.randint(2, NUM_WEEKS)
    row = random_row(df, ta_id, week)
    old_date = df.loc[row, "entry_date"]
    new_date = df.loc[row, "pay_period_start"] - timedelta(days=1)
    df.loc[row, "entry_date"] = new_date
    record(planted, ta_id, week, "Date outside pay period",
           f"{old_date} changed to {new_date}, before the period starts")
    return df


def plant_late(df, planted, ta_id, week, days_late):
    """Problem 6: the week was submitted after the Monday 11:59 PM deadline."""
    mask = week_rows(df, ta_id, week)
    _, period_end = pay_period_for_week(week)
    # Monday (period_end + 1) is the deadline day, so add days_late on top.
    late_time = datetime.combine(period_end + timedelta(days=1 + days_late), time(9, 15))
    df.loc[mask, "submitted_at"] = late_time
    record(planted, ta_id, week, "Late submission", f"submitted {late_time}")
    return df


def plant_missing_week(df, planted, ta_id, week):
    """Problem 7: a TA has no entries at all for one week."""
    df = df[~week_rows(df, ta_id, week)]  # ~ flips the mask: keep everything else
    record(planted, ta_id, week, "Missing week", "no entries this week")
    return df


def plant_name_typo(df, planted, ta_id, week):
    """Problem 8: one ta_id appears with two spellings of the name.

    For one week the last two letters of the last name are swapped, the kind
    of typo a person makes when typing their own name.
    """
    mask = week_rows(df, ta_id, week)
    right = df.loc[mask, "ta_name"].iloc[0]
    first, last = right.split(" ")
    wrong = f"{first} {last[:-2]}{last[-1]}{last[-2]}"  # Hayes -> Hayse
    df.loc[mask, "ta_name"] = wrong
    record(planted, ta_id, week, "Name spelled two ways", f"'{right}' and '{wrong}'")
    return df


# ---------------------------------------------------------------------------
# Planted trend patterns (found later by trends.py, not by the audit rules)
# ---------------------------------------------------------------------------

def plant_dropping_hours(df, planted, ta_id):
    """Trend 1: hours drop three weeks in a row (weeks 4, 5 and 6).

    The clean data already has a few small drops by chance (at most about
    25% overall), so this drop is made big: down to about 30% of week 3.
    """
    totals = [week_hours(df, ta_id, 3)]
    for week, share in [(4, 0.75), (5, 0.5), (6, 0.3)]:
        mask = week_rows(df, ta_id, week)
        per_day = totals[0] * share / mask.sum()
        per_day = max(0.5, round(per_day * 2) / 2)  # nearest half hour, at least 0.5
        df.loc[mask, "hours"] = per_day
        totals.append(week_hours(df, ta_id, week))

    # Make sure each week really is lower than the week before.
    assert all(later < earlier for earlier, later in zip(totals, totals[1:])), totals
    record(planted, ta_id, 6, "Hours dropping",
           "weeks 3 to 6: " + " -> ".join(f"{hours:g}" for hours in totals) + " hours")
    return df


def plant_low_hours(df, planted, ta_id):
    """Trend 2: a TA who works far fewer hours than the team, every week."""
    df.loc[df["ta_id"] == ta_id, "hours"] = 0.5
    record(planted, ta_id, None, "Far below team average", "0.5 hours per day, all 7 weeks")
    return df


def plant_problems(df, tas):
    """Plant every problem, each on a different TA. Returns (df, planted)."""
    planted = []

    # Problems that add hours go to TAs with 4 work days, who have room to
    # spare. Everyone else goes in the second pool.
    four_day = [ta["ta_id"] for ta in tas if len(ta["work_days"]) == 4]
    adders = random.sample(four_day, 4)
    others = [ta["ta_id"] for ta in tas if ta["ta_id"] not in adders]
    random.shuffle(others)

    # pop() removes and returns the last TA in a list, so no TA is used twice.
    df = plant_duplicate(df, planted, adders.pop())
    df = plant_duplicate(df, planted, adders.pop())
    df = plant_long_day_single(df, planted, adders.pop())
    df = plant_long_day_split(df, planted, adders.pop())

    df = plant_bad_hours(df, planted, others.pop(), 0.0)
    df = plant_bad_hours(df, planted, others.pop(), -2.0)
    df = plant_long_week(df, planted, others.pop())
    df = plant_outside_period(df, planted, others.pop())
    df = plant_outside_period(df, planted, others.pop())

    late_ta = others.pop()  # one TA is late twice, for the trends in Block 6
    df = plant_late(df, planted, late_ta, week=2, days_late=1)
    df = plant_late(df, planted, late_ta, week=5, days_late=2)
    df = plant_late(df, planted, others.pop(), week=6, days_late=1)

    df = plant_missing_week(df, planted, others.pop(), week=4)
    df = plant_name_typo(df, planted, others.pop(), week=3)

    df = plant_dropping_hours(df, planted, others.pop())
    df = plant_low_hours(df, planted, others.pop())

    # Put rows back in order, so a duplicate sits next to the row it copies.
    df = df.sort_values(["ta_id", "entry_date"], kind="stable").reset_index(drop=True)
    return df, pd.DataFrame(planted)


def main():
    random.seed(RANDOM_SEED)

    tas = make_tas()
    entries = make_clean_entries(tas)

    # A DataFrame is pandas' table: one row per entry, one column per field.
    df = pd.DataFrame(entries)
    clean_rows = len(df)

    df, planted = plant_problems(df, tas)

    OUTPUT_FILE.parent.mkdir(exist_ok=True)  # create the data/ folder if it's missing
    df.to_csv(OUTPUT_FILE, index=False)  # index=False: don't save pandas' row numbers
    # Int64 (capital I) allows a blank week, which "Far below team average" has.
    planted["week"] = planted["week"].astype("Int64")
    planted.to_csv(PLANTED_FILE, index=False)

    print(f"Built {clean_rows:,} clean entries, then planted {len(planted)} problems.")
    print(f"Saved {len(df):,} entries for {df['ta_id'].nunique()} TAs to {OUTPUT_FILE}")
    print(f"Saved the list of planted problems to {PLANTED_FILE}")
    print()
    print(planted.to_string(index=False))


# Run main() only when this file is run directly (python generate_data.py),
# not when another file imports it.
if __name__ == "__main__":
    main()
