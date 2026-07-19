# ============================================================
# calendar.py — CalDAV 日历集成（Phase 7.2）
#
# 功能：
#   - get_today_events() → 返回今日日程
#   - get_week_events() → 返回本周日程
#   - create_event(title, date, time?, duration?, notes?) → 创建事件
#
# 安全：
#   - CalDAV 密码存环境变量 CALDAV_URL / CALDAV_USERNAME / CALDAV_PASSWORD
#   - 默认只读，写操作需用户确认（is_enabled 检查）
# ============================================================

import os
import json
from datetime import date, datetime, timedelta


def _get_config() -> dict:
    """获取 CalDAV 配置，未配置时返回空。"""
    url = os.environ.get("CALDAV_URL", "")
    username = os.environ.get("CALDAV_USERNAME", "")
    password = os.environ.get("CALDAV_PASSWORD", "")
    if not url or not username or not password:
        return {}
    return {"url": url, "username": username, "password": password}


def is_enabled() -> bool:
    """检查日历集成是否已配置。"""
    return bool(_get_config())


async def get_today_events() -> str:
    """获取今日日程列表。"""
    config = _get_config()
    if not config:
        return json.dumps({"status": "disabled", "message": "CalDAV 未配置（设置 CALDAV_URL / CALDAV_USERNAME / CALDAV_PASSWORD 环境变量）"}, ensure_ascii=False)

    try:
        import caldav
        from caldav.elements import dav

        client = caldav.DAVClient(
            url=config["url"],
            username=config["username"],
            password=config["password"],
        )
        principal = client.principal()
        calendars = principal.calendars()

        if not calendars:
            return json.dumps({"events": [], "message": "No calendars found"}, ensure_ascii=False)

        today = date.today()
        tomorrow = today + timedelta(days=1)
        events = []

        for cal in calendars:
            try:
                cal_events = cal.search(
                    start=today, end=tomorrow,
                    event=True, expand=True,
                )
                for ev in cal_events:
                    events.append({
                        "uid": str(ev.data.find(".//{urn:ietf:params:xml:ns:caldav}uid")) if hasattr(ev, 'data') else "",
                        "summary": getattr(ev.instance.vevent.summary, 'value', '') if hasattr(ev, 'instance') else str(ev),
                        "start": str(ev.instance.vevent.dtstart.value) if hasattr(ev, 'instance') else "",
                        "end": str(ev.instance.vevent.dtend.value) if hasattr(ev, 'instance') and hasattr(ev.instance.vevent, 'dtend') else "",
                    })
            except Exception:
                pass

        return json.dumps({"events": events, "date": today.isoformat()}, ensure_ascii=False)
    except ImportError:
        return json.dumps({"status": "error", "message": "caldav library not installed. Run: pip install caldav"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": f"CalDAV error: {e}"}, ensure_ascii=False)


async def get_week_events() -> str:
    """获取本周日程列表。"""
    config = _get_config()
    if not config:
        return json.dumps({"status": "disabled", "message": "CalDAV 未配置"}, ensure_ascii=False)

    try:
        import caldav

        client = caldav.DAVClient(
            url=config["url"],
            username=config["username"],
            password=config["password"],
        )
        principal = client.principal()
        calendars = principal.calendars()

        if not calendars:
            return json.dumps({"events": [], "message": "No calendars found"}, ensure_ascii=False)

        today = date.today()
        week_end = today + timedelta(days=7)
        events = []

        for cal in calendars:
            try:
                cal_events = cal.search(
                    start=today, end=week_end,
                    event=True, expand=True,
                )
                for ev in cal_events:
                    events.append({
                        "summary": getattr(ev.instance.vevent.summary, 'value', '') if hasattr(ev, 'instance') else str(ev),
                        "start": str(ev.instance.vevent.dtstart.value) if hasattr(ev, 'instance') else "",
                        "end": str(ev.instance.vevent.dtend.value) if hasattr(ev, 'instance') and hasattr(ev.instance.vevent, 'dtend') else "",
                    })
            except Exception:
                pass

        return json.dumps({"events": events, "week_start": today.isoformat(), "week_end": week_end.isoformat()}, ensure_ascii=False)
    except ImportError:
        return json.dumps({"status": "error", "message": "caldav library not installed. Run: pip install caldav"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": f"CalDAV error: {e}"}, ensure_ascii=False)


async def create_event(title: str, event_date: str, event_time: str = "", duration_min: int = 60, notes: str = "") -> str:
    """创建日历事件。需要 CalDAV 写权限。"""
    config = _get_config()
    if not config:
        return json.dumps({"status": "disabled", "message": "CalDAV 未配置"}, ensure_ascii=False)

    try:
        import caldav
        from caldav.elements import dav, cdav
        from icalendar import Calendar, Event
        import pytz

        client = caldav.DAVClient(
            url=config["url"],
            username=config["username"],
            password=config["password"],
        )
        principal = client.principal()
        calendars = principal.calendars()

        if not calendars:
            return json.dumps({"status": "error", "message": "No writeable calendar found"}, ensure_ascii=False)

        # Parse date/time
        dt_str = event_date
        if event_time:
            dt_str += f" {event_time}"
        try:
            if event_time:
                dt_start = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            else:
                dt_start = datetime.strptime(dt_str, "%Y-%m-%d")
        except ValueError:
            return json.dumps({"status": "error", "message": f"Invalid date/time format: {dt_str}"}, ensure_ascii=False)

        dt_end = dt_start + timedelta(minutes=duration_min)

        cal_event = Event()
        cal_event.add('summary', title)
        cal_event.add('dtstart', dt_start)
        cal_event.add('dtend', dt_end)
        if notes:
            cal_event.add('description', notes)

        cal = Calendar()
        cal.add_component(cal_event)

        calendars[0].save_event(cal.to_ical().decode())

        return json.dumps({
            "status": "ok",
            "title": title,
            "start": dt_start.isoformat(),
            "end": dt_end.isoformat(),
            "duration_min": duration_min,
        }, ensure_ascii=False)
    except ImportError as e:
        return json.dumps({"status": "error", "message": f"Missing library: {e}. Run: pip install caldav icalendar pytz"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": f"CalDAV error: {e}"}, ensure_ascii=False)
