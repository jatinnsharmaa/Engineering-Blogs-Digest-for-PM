"""
Run this after changing schedule.day or schedule.hour in config/settings.yaml.
It prints the cron line to paste into .github/workflows/weekly_digest.yml.

Usage: python make_cron.py
"""
import yaml

DAY_MAP = {
    "sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
    "thursday": 4, "friday": 5, "saturday": 6,
}

with open("config/settings.yaml") as f:
    settings = yaml.safe_load(f)

sched = settings.get("schedule", {})
day = sched.get("day", "Saturday").lower()
hour = int(sched.get("hour", 9))

weekday = DAY_MAP.get(day)
if weekday is None:
    raise ValueError(f"Unknown day '{day}'. Use: Mon/Tue/Wed/Thu/Fri/Sat/Sun")

cron = f"0 {hour} * * {weekday}"
print(f"Cron expression: {cron}")
print(f"Schedule: every {day.capitalize()} at {hour:02d}:00 UTC")
print()
print("Paste this into .github/workflows/weekly_digest.yml:")
print(f"    - cron: '{cron}'")
