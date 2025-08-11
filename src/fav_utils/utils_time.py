# utils_time.py
from datetime import datetime, timedelta, timezone, time as dtime

def utcnow():
    return datetime.now(timezone.utc)

def floor_to_hour(dt):
    return dt.replace(minute=0, second=0, microsecond=0)

def prev_full_hour_window(now=None):
    now = now or utcnow()
    start = floor_to_hour(now) - timedelta(hours=1)
    end   = start + timedelta(hours=1)
    return start, end

def prev_mon_sun_week(now=None):
    """Previous Mon 00:00:00 UTC → next Mon 00:00:00 UTC."""
    now = (now or utcnow()).date()
    weekday = now.weekday()  # Mon=0
    last_monday = now - timedelta(days=weekday+7)
    start = datetime.combine(last_monday, dtime.min, tzinfo=timezone.utc)
    end   = start + timedelta(days=7)
    return start, end

# add this
from datetime import timedelta
def last_60m_window(now=None):
    now = now or utcnow()
    return now - timedelta(minutes=60), now

def next_monday_start(now=None):
    now = now or utcnow()
    wd = now.weekday()  # Mon=0
    days = (7 - wd) % 7
    if days == 0:
        days = 7
    nxt = (now + timedelta(days=days)).date()
    return datetime.combine(nxt, dtime.min, tzinfo=timezone.utc)
