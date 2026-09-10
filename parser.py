import time
import re
import html
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import httpx
from bs4 import BeautifulSoup

from config import ALMETPT_BASE_URL
from premium_emoji import (
    te, PE_CALENDAR, PE_CLOCK, PE_BELL, PE_PEOPLE, PE_SEARCH,
    PE_HOUSE, PE_ARROW_LEFT, PE_REPEAT, PE_LINK,
    PE_PERSON_CHECK, PE_INFO, PE_CHECK, PE_PARTY, PE_PENCIL,
    PE_FILE, PE_WARNING, PE_GEOTAG, PE_STAR, PE_TIME_PASSED
)

# Caching containers
_GROUPS_CACHE: Dict[str, Any] = {}
_GROUPS_CACHE_TIME: float = 0
_STAFFS_CACHE: Dict[str, Any] = {}
_STAFFS_CACHE_TIME: float = 0
_DATES_CACHE: Dict[str, Any] = {}
_DATES_CACHE_TIME: float = 0

CACHE_TTL_GROUPS = 1800   # 30 minutes
CACHE_TTL_STAFFS = 1800   # 30 minutes
CACHE_TTL_DATES = 300     # 5 minutes

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

XHR_HEADERS = {
    **HEADERS,
    "X-Requested-With": "XMLHttpRequest"
}


def normalize_string(s: str) -> str:
    """Normalizes string for search: lowercase, remove dashes, spaces, dots."""
    return re.sub(r"[\s\-_.\(\)]+", "", s.lower())


async def get_available_dates(force_refresh: bool = False) -> Dict[str, Any]:
    """Fetches available schedule dates from /2020/schedule/dates"""
    global _DATES_CACHE, _DATES_CACHE_TIME
    now_ts = time.time()
    if not force_refresh and _DATES_CACHE and (now_ts - _DATES_CACHE_TIME < CACHE_TTL_DATES):
        return _DATES_CACHE

    url = f"{ALMETPT_BASE_URL}/2020/schedule/dates"
    try:
        async with httpx.AsyncClient(headers=XHR_HEADERS, timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                today = data.get("now", "")
                selected = data.get("selected_date", today)
                raw_dates = data.get("dates", [])
                
                formatted_dates = []
                for d in raw_dates:
                    dt = d.get("Date", "")
                    day_name = d.get("name", "") or d.get("Value", "")
                    day_label = d.get("day", dt)
                    is_today = (dt == today)
                    formatted_dates.append({
                        "date": dt,
                        "day_name": day_name,
                        "label": day_label,
                        "is_today": is_today
                    })

                result = {
                    "today": today,
                    "selected": selected,
                    "dates": formatted_dates
                }
                _DATES_CACHE = result
                _DATES_CACHE_TIME = now_ts
                return result
    except Exception as e:
        print(f"Error fetching dates: {e}")

    # Fallback if request fails
    today_str = datetime.now().strftime("%Y-%m-%d")
    fallback_dates = []
    for i in range(-1, 5):
        d_val = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
        fallback_dates.append({
            "date": d_val,
            "day_name": f"+{i} дн." if i != 0 else "Сегодня",
            "label": d_val,
            "is_today": i == 0
        })
    return {
        "today": today_str,
        "selected": today_str,
        "dates": fallback_dates
    }


def get_tomorrow_date(dates_info: Dict[str, Any]) -> str:
    """
    Returns the next schedule date for 'tomorrow'.
    Filters dates > today (sorted ascending, e.g. tomorrow).
    If not yet published, computes the next study day (skipping Sunday).
    """
    today_str = dates_info.get("today") or datetime.now().strftime("%Y-%m-%d")
    dates_list = dates_info.get("dates", [])
    future_dates = sorted([d["date"] for d in dates_list if d.get("date", "") > today_str])
    if future_dates:
        return future_dates[0]
    try:
        curr = datetime.strptime(today_str, "%Y-%m-%d")
        next_day = curr + timedelta(days=1)
        if next_day.weekday() == 6:  # Sunday -> Monday
            next_day += timedelta(days=1)
        return next_day.strftime("%Y-%m-%d")
    except Exception:
        return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")


async def get_groups(force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    """Fetches and parses list of all groups from /2020/json/groups"""
    global _GROUPS_CACHE, _GROUPS_CACHE_TIME
    now_ts = time.time()
    if not force_refresh and _GROUPS_CACHE and (now_ts - _GROUPS_CACHE_TIME < CACHE_TTL_GROUPS):
        return _GROUPS_CACHE

    url = f"{ALMETPT_BASE_URL}/2020/json/groups"
    try:
        async with httpx.AsyncClient(headers=XHR_HEADERS, timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                groups_dict = {}
                raw_groups = data.get("groups", {})
                
                for key, val in raw_groups.items():
                    if isinstance(val, dict) and "Name" in val:
                        g_id = str(val.get("id") or val.get("idGroup") or key)
                        name = val.get("Name", "").strip()
                        kurs = val.get("Kurs") or val.get("realCourse") or 1
                        is_sched = val.get("isSchedule", 1)
                        out_name = val.get("outName", name)
                        
                        try:
                            kurs_int = int(kurs)
                        except (ValueError, TypeError):
                            kurs_int = 1

                        groups_dict[g_id] = {
                            "id": g_id,
                            "name": name,
                            "out_name": out_name,
                            "kurs": kurs_int,
                            "is_schedule": is_sched
                        }

                if groups_dict:
                    _GROUPS_CACHE = groups_dict
                    _GROUPS_CACHE_TIME = now_ts
                    return groups_dict
    except Exception as e:
        print(f"Error fetching groups: {e}")

    return _GROUPS_CACHE


async def search_groups(query: str, limit: int = 15) -> List[Dict[str, Any]]:
    """Searches groups by name, course, or partial text."""
    all_groups = await get_groups()
    if not all_groups:
        return []

    clean_q = normalize_string(query)
    results = []
    
    for g in all_groups.values():
        norm_name = normalize_string(g["name"])
        if norm_name == clean_q:
            results.insert(0, g)
        elif norm_name.startswith(clean_q):
            results.append(g)
        elif clean_q in norm_name:
            results.append(g)

    seen = set()
    unique_results = []
    for g in results:
        if g["id"] not in seen:
            seen.add(g["id"])
            unique_results.append(g)
            if len(unique_results) >= limit:
                break

    return unique_results


async def get_groups_by_course(course: int) -> List[Dict[str, Any]]:
    """Returns all active groups for a specific course (1-4)."""
    all_groups = await get_groups()
    result = [g for g in all_groups.values() if g.get("kurs") == course]
    result.sort(key=lambda x: x["name"])
    return result


async def get_staffs(force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    """Fetches list of teachers/staff from /2020/json/staffs"""
    global _STAFFS_CACHE, _STAFFS_CACHE_TIME
    now_ts = time.time()
    if not force_refresh and _STAFFS_CACHE and (now_ts - _STAFFS_CACHE_TIME < CACHE_TTL_STAFFS):
        return _STAFFS_CACHE

    url = f"{ALMETPT_BASE_URL}/2020/json/staffs"
    try:
        async with httpx.AsyncClient(headers=XHR_HEADERS, timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                staffs_dict = {}
                raw_staffs = data.get("staffs", {})
                
                for key, val in raw_staffs.items():
                    if isinstance(val, dict):
                        s_id = str(val.get("id") or val.get("idStaff") or key)
                        family = val.get("Family", "").strip()
                        name = val.get("Name", "").strip()
                        father = val.get("Father", "").strip()
                        fio = f"{family} {name} {father}".strip()
                        short_fio = f"{family} {name[:1]}.{father[:1]}." if name and father else fio
                        
                        staffs_dict[s_id] = {
                            "id": s_id,
                            "fio": fio,
                            "short_fio": short_fio,
                            "is_teacher": val.get("isTeacher", 0)
                        }

                if staffs_dict:
                    _STAFFS_CACHE = staffs_dict
                    _STAFFS_CACHE_TIME = now_ts
                    return staffs_dict
    except Exception as e:
        print(f"Error fetching staffs: {e}")

    return _STAFFS_CACHE


async def search_teachers(query: str, limit: int = 15) -> List[Dict[str, Any]]:
    """Searches teachers by surname or full name."""
    all_staff = await get_staffs()
    if not all_staff:
        return []

    clean_q = normalize_string(query)
    results = []
    
    for s in all_staff.values():
        if not s.get("is_teacher", 1):
            continue
        norm_fio = normalize_string(s["fio"])
        if clean_q in norm_fio:
            results.append(s)

    results.sort(key=lambda x: x["fio"])
    return results[:limit]


async def get_teacher_letters() -> List[str]:
    """Returns sorted unique letters of teachers' surnames for pure button navigation."""
    all_staff = await get_staffs()
    letters = set()
    for s in all_staff.values():
        if not s.get("is_teacher", 1):
            continue
        fio = (s.get("fio") or "").strip()
        if fio and fio[0].isalpha():
            letters.add(fio[0].upper())
    return sorted(letters)


async def get_teachers_by_letter(letter: str, limit: int = 30) -> List[Dict[str, Any]]:
    """Returns teachers whose surname starts with the given letter."""
    all_staff = await get_staffs()
    if not all_staff:
        return []
    want = (letter or "").strip().upper()[:1]
    if not want:
        return []
    results = []
    for s in all_staff.values():
        if not s.get("is_teacher", 1):
            continue
        fio = (s.get("fio") or "").strip()
        if fio.upper().startswith(want):
            results.append(s)
    results.sort(key=lambda x: x["fio"])
    return results[:limit]


async def get_group_schedule(group_id: str, date_str: str) -> Dict[str, Any]:
    """
    Parses schedule for a specific group and date.
    URL: /2020/site/schedule/group/{group_id}/{date_str}
    """
    url = f"{ALMETPT_BASE_URL}/2020/site/schedule/group/{group_id}/{date_str}"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {
                    "success": False,
                    "error": f"Сайт техникума вернул код ответа {resp.status_code}.",
                    "lessons": []
                }
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        return {
            "success": False,
            "error": f"Не удалось связаться с сайтом техникума: {e}",
            "lessons": []
        }

    header_div = soup.find("div", class_="header3")
    header_text = header_div.get_text(strip=True, separator=" ") if header_div else ""

    alerts = []
    for a in soup.find_all("div", class_=re.compile(r"alert")):
        t = a.get_text(strip=True)
        if "cookie" not in t.lower():
            alerts.append(t)

    cards = soup.find_all("div", class_="myCard")
    lessons = []
    
    for card in cards:
        card_header = card.find("div", class_="card-header")
        if not card_header:
            continue
        
        pair_span = card_header.find("span", class_="h3")
        pair_num = pair_span.get_text(strip=True) if pair_span else ""
        time_span = card_header.find("span", class_="h4")
        pair_time = time_span.get_text(strip=True) if time_span else ""
        if not pair_num and not pair_time:
            continue
        
        card_body = card.find("div", class_="card-body")
        subgroup_rows = []
        if card_body:
            sub_divs = card_body.find_all("div", class_=re.compile(r"subGroup\d+|d-flex flex-column"))
            if not sub_divs:
                sub_divs = [card_body]
            
            seen_items = set()
            for sdiv in sub_divs:
                sub_label = ""
                for sp in sdiv.find_all("span", class_="rounded"):
                    t = sp.get_text(strip=True)
                    if "п/гр" in t:
                        sub_label = t
                        break
                
                aud = ""
                aud_tag = sdiv.find("a", href=re.compile(r"rooms\?idAudience"))
                if aud_tag:
                    aud = aud_tag.get_text(strip=True)
                
                teacher = ""
                staff_tag = sdiv.find("span", class_="Staff")
                if staff_tag:
                    teacher = staff_tag.get("title") or staff_tag.get_text(strip=True)
                
                subj = ""
                b_tag = sdiv.find("b")
                if b_tag:
                    subj = b_tag.get_text(strip=True)
                else:
                    changes = sdiv.find_all(class_="changesPair")
                    for ch in changes:
                        if "Staff" not in ch.get("class", []):
                            t = ch.get_text(strip=True)
                            if t and t not in (teacher, aud):
                                subj = t
                                break
                
                hw = ""
                hw_tag = sdiv.find(string=re.compile(r"Д\.з:"))
                if hw_tag:
                    hw = hw_tag.strip()
                    hw = re.sub(r"^Д\.з:\s*", "", hw).strip()

                topic = ""
                topic_tag = sdiv.find(string=re.compile(r"Тема:"))
                if topic_tag:
                    topic = topic_tag.strip()
                    topic = re.sub(r"^Тема:\s*", "", topic).strip()

                if subj or teacher or aud:
                    key = (sub_label, subj, teacher, aud)
                    if key not in seen_items:
                        seen_items.add(key)
                        subgroup_rows.append({
                            "subgroup": sub_label,
                            "subject": subj,
                            "teacher": teacher,
                            "audience": aud,
                            "homework": hw,
                            "topic": topic
                        })

        lessons.append({
            "pair": pair_num,
            "time": pair_time,
            "items": subgroup_rows
        })

    return {
        "success": True,
        "url": url,
        "header": header_text,
        "alerts": alerts,
        "lessons": lessons
    }


async def get_teacher_schedule(staff_id: str, date_str: str) -> Dict[str, Any]:
    """
    Parses schedule for a teacher on date_str.
    URL: /2020/site/schedule/staff/{staff_id}/{date_str}
    """
    url = f"{ALMETPT_BASE_URL}/2020/site/schedule/staff/{staff_id}/{date_str}"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {
                    "success": False,
                    "error": f"Сайт вернул код ответа {resp.status_code}.",
                    "lessons": []
                }
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка соединения с сайтом: {e}",
            "lessons": []
        }

    header_div = soup.find("div", class_="header3")
    header_text = header_div.get_text(strip=True, separator=" ") if header_div else ""

    alerts = []
    for a in soup.find_all("div", class_=re.compile(r"alert")):
        t = a.get_text(strip=True)
        if "cookie" not in t.lower():
            alerts.append(t)

    cards = soup.find_all("div", class_="myCard")
    lessons = []
    for card in cards:
        card_header = card.find("div", class_="card-header")
        card_body = card.find("div", class_="card-body")
        if not card_header or not card_body:
            continue
        
        pair_span = card_header.find("span", class_="h3")
        pair_num = pair_span.get_text(strip=True) if pair_span else ""
        time_span = card_header.find("span", class_="h4")
        pair_time = time_span.get_text(strip=True) if time_span else ""
        
        body_text = card_body.get_text(strip=True, separator=" ")
        
        aud = ""
        aud_tag = card_body.find("a", href=re.compile(r"rooms\?idAudience"))
        if aud_tag:
            aud = aud_tag.get_text(strip=True)
            
        grp = ""
        grp_tag = card_body.find("a", href=re.compile(r"schedule/group"))
        if grp_tag:
            grp = grp_tag.get_text(strip=True)

        lessons.append({
            "pair": pair_num,
            "time": pair_time,
            "audience": aud,
            "group": grp,
            "details": body_text
        })

    return {
        "success": True,
        "url": url,
        "header": header_text,
        "alerts": alerts,
        "lessons": lessons
    }


ROMAN_MAP = {
    "1": "I", "2": "II", "3": "III", "4": "IV",
    "5": "V", "6": "VI", "7": "VII", "8": "VIII"
}

WEEKDAYS_RU = [
    "понедельник", "вторник", "среда", "четверг",
    "пятница", "суббота", "воскресенье"
]

MONTHS_RU = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря"
]


def format_russian_date(date_str: str) -> str:
    """Formats 'YYYY-MM-DD' to Russian: e.g. 'пятница, 23 января 2026'."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{WEEKDAYS_RU[dt.weekday()]}, {dt.day} {MONTHS_RU[dt.month]} {dt.year}"
    except Exception:
        return date_str


def to_roman_pair(pair_str: str) -> str:
    """Normalizes pair string to Roman numeral: 'I', 'II', 'III', etc."""
    p = pair_str.strip()
    clean = re.sub(r"[^\w\d]", "", p).upper()
    if clean in ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]:
        return clean
    if clean in ROMAN_MAP:
        return ROMAN_MAP[clean]
    m = re.search(r"\d+", p)
    if m and m.group(0) in ROMAN_MAP:
        return ROMAN_MAP[m.group(0)]
    return p or "I"


def parse_pair_times(time_str: str) -> Tuple[Optional[str], Optional[str], Optional[datetime], Optional[datetime]]:
    """Extracts start and end times, e.g. '08:00', '09:30' and dummy datetimes."""
    m = re.search(r"(\d{1,2})[\s:]*(\d{2})\s*[-–—]\s*(\d{1,2})[\s:]*(\d{2})", time_str)
    if m:
        h1, m1, h2, m2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        t1_str = f"{h1:02d}:{m1:02d}"
        t2_str = f"{h2:02d}:{m2:02d}"
        dt1 = datetime(2000, 1, 1, h1, m1)
        dt2 = datetime(2000, 1, 1, h2, m2)
        return t1_str, t2_str, dt1, dt2
    return None, None, None, None


def format_minutes_ru(m: int) -> str:
    """Returns correct Russian plural for minutes: 20 минут, 21 минута, 22 минуты."""
    if 11 <= (m % 100) <= 14:
        return f"{m} минут"
    last = m % 10
    if last == 1:
        return f"{m} минута"
    if 2 <= last <= 4:
        return f"{m} минуты"
    return f"{m} минут"


def format_schedule_message(
    data: Dict[str, Any],
    group_name: str,
    date_str: str,
    day_label: Optional[str] = None
) -> str:
    """Formats group schedule into the simplified clean layout with premium emojis."""
    if not data.get("success", True):
        return f"{te(PE_WARNING, '!')} <b>Ошибка получения расписания:</b>\n{html.escape(data.get('error', 'Неизвестная ошибка'))}"

    human_date = format_russian_date(date_str)
    if day_label and day_label.lower() not in human_date.lower():
        date_line = f"{te(PE_CALENDAR)} {human_date} ({html.escape(day_label)})"
    else:
        date_line = f"{te(PE_CALENDAR)} {human_date}"

    lines = [
        f"{te(PE_PEOPLE)} <b>Расписание группы {html.escape(group_name)}</b>",
        date_line,
        ""
    ]

    lessons = data.get("lessons", [])
    if not lessons:
        alerts = data.get("alerts", [])
        if alerts:
            lines.append(f"{te(PE_INFO)} <i>{html.escape(alerts[0])}</i>")
        else:
            lines.append(f"{te(PE_PARTY)} <b>Пар нет!</b> В этот день занятия отсутствуют.")
        return "\n".join(lines)

    # Pre-parse pair times to calculate breaks between pairs
    parsed_lessons = []
    for l in lessons:
        t1, t2, dt1, dt2 = parse_pair_times(l.get("time", ""))
        parsed_lessons.append({
            "lesson": l,
            "t1": t1,
            "t2": t2,
            "dt1": dt1,
            "dt2": dt2
        })

    for i, item in enumerate(parsed_lessons):
        l = item["lesson"]
        p_num = to_roman_pair(l.get("pair", ""))

        # Format time part: "с 08:00 по 09:30"
        if item["t1"] and item["t2"]:
            time_part = f" с {item['t1']} по {item['t2']}"
        elif l.get("time"):
            time_clean = re.sub(r"(\d{1,2})\s+(\d{2})", r"\1:\2", l.get("time", "").strip())
            time_part = f" [{html.escape(time_clean)}]"
        else:
            time_part = ""

        # Calculate break after this pair if next pair exists and break >= 15 min
        break_str = ""
        if i + 1 < len(parsed_lessons):
            next_dt1 = parsed_lessons[i + 1]["dt1"]
            curr_dt2 = item["dt2"]
            if next_dt1 and curr_dt2:
                diff_min = int((next_dt1 - curr_dt2).total_seconds() / 60)
                if diff_min >= 15:
                    break_str = f" <i>(Перемена {format_minutes_ru(diff_min)})</i>"

        # Pair header line
        lines.append(f"{te(PE_CLOCK)} <b>{p_num} пара{time_part}</b>{break_str}")

        subgroup_items = l.get("items", [])
        if not subgroup_items:
            lines.append("  <i>Занятие не указано</i>")
        else:
            for sub in subgroup_items:
                # Subgroup text: "1 п/гр. "
                sg = sub.get("subgroup", "").strip()
                if sg:
                    if not sg.endswith("."):
                        sg += "."
                    sg_part = f"{html.escape(sg)} "
                else:
                    sg_part = ""

                # Subject: "#Будущего"
                subj = sub.get("subject", "").strip() or "Предмет не указан"
                subj_escaped = html.escape(subj)

                # Audience: "(233)" or "(дистант)"
                aud = sub.get("audience", "").strip()
                if aud:
                    if "on-line" in aud.lower():
                        aud_part = " <i>(дистант)</i>"
                    else:
                        aud_part = f" ({html.escape(aud)})"
                else:
                    aud_part = ""

                # Teacher: "Тухбатуллина Р.А."
                teacher = sub.get("teacher", "").strip()
                teacher_part = f" {html.escape(teacher)}" if teacher else ""

                lines.append(f" {sg_part}{subj_escaped}{aud_part}{teacher_part}")

                # Homework & Topic if present
                if sub.get("homework"):
                    hw = sub["homework"].strip()
                    if len(hw) > 200:
                        hw = hw[:197] + "..."
                    lines.append(f"   {te(PE_PENCIL)} <i>Д/з: {html.escape(hw)}</i>")
                elif sub.get("topic"):
                    top = sub["topic"].strip()
                    if len(top) > 150:
                        top = top[:147] + "..."
                    lines.append(f"   {te(PE_FILE)} <i>Тема: {html.escape(top)}</i>")

        lines.append("")  # Empty line between pairs

    msg_text = "\n".join(lines).strip()
    if len(msg_text) > 4000:
        msg_text = msg_text[:3990] + "\n\n<i>...(расписание сокращено из-за лимита)</i>"
    return msg_text


def format_teacher_schedule_message(
    data: Dict[str, Any],
    teacher_name: str,
    date_str: str
) -> str:
    """Formats teacher schedule into clean Telegram HTML with premium emojis."""
    if not data.get("success", True):
        return f"{te(PE_WARNING, '!')} <b>Ошибка:</b>\n{html.escape(data.get('error', ''))}"

    human_date = format_russian_date(date_str)
    lines = [
        f"{te(PE_PERSON_CHECK)} <b>Расписание преподавателя:</b>",
        f"<b>{html.escape(teacher_name)}</b>",
        f"{te(PE_CALENDAR)} {human_date}",
        ""
    ]

    lessons = data.get("lessons", [])
    if not lessons:
        lines.append(f"{te(PE_PARTY)} <b>Пар нет!</b> В этот день у преподавателя нет занятий.")
        return "\n".join(lines)

    parsed_lessons = []
    for l in lessons:
        t1, t2, dt1, dt2 = parse_pair_times(l.get("time", ""))
        parsed_lessons.append({
            "lesson": l,
            "t1": t1,
            "t2": t2,
            "dt1": dt1,
            "dt2": dt2
        })

    for i, item in enumerate(parsed_lessons):
        l = item["lesson"]
        p_num = to_roman_pair(l.get("pair", ""))

        if item["t1"] and item["t2"]:
            time_part = f" с {item['t1']} по {item['t2']}"
        elif l.get("time"):
            time_clean = re.sub(r"(\d{1,2})\s+(\d{2})", r"\1:\2", l.get("time", "").strip())
            time_part = f" [{html.escape(time_clean)}]"
        else:
            time_part = ""

        break_str = ""
        if i + 1 < len(parsed_lessons):
            next_dt1 = parsed_lessons[i + 1]["dt1"]
            curr_dt2 = item["dt2"]
            if next_dt1 and curr_dt2:
                diff_min = int((next_dt1 - curr_dt2).total_seconds() / 60)
                if diff_min >= 15:
                    break_str = f" <i>(Перемена {format_minutes_ru(diff_min)})</i>"

        lines.append(f"{te(PE_CLOCK)} <b>{p_num} пара{time_part}</b>{break_str}")

        grp_part = f"<b>{html.escape(l['group'])}</b>" if l.get("group") else ""
        aud = l.get("audience", "").strip()
        if aud:
            aud_part = " <i>(дистант)</i>" if "on-line" in aud.lower() else f" ({html.escape(aud)})"
        else:
            aud_part = ""

        details = l.get("details", "").strip()
        details_part = f" {html.escape(details)}" if details else ""

        line_body = f"{grp_part}{aud_part}{details_part}".strip()
        if line_body:
            lines.append(f" {line_body}")

        lines.append("")

    msg_text = "\n".join(lines).strip()
    if len(msg_text) > 4000:
        msg_text = msg_text[:3990] + "\n\n<i>...(сокращено из-за лимита)</i>"
    return msg_text


def get_calls_text() -> str:
    """Returns звонки table styled exclusively with premium emojis."""
    return (
        f"{te(PE_BELL)} <b>Расписание звонков ГАПОУ «АПТ»:</b>\n\n"
        f"{te(PE_CLOCK)} <b>I пара:</b> <code>08:00 – 09:20</code> <i>(перемена 10 мин)</i>\n"
        f"{te(PE_CLOCK)} <b>II пара:</b> <code>09:30 – 10:50</code> <i>(большая перемена 30 мин)</i>\n"
        f"{te(PE_CLOCK)} <b>III пара:</b> <code>11:20 – 12:40</code> <i>(перемена 10 мин)</i>\n"
        f"{te(PE_CLOCK)} <b>IV пара:</b> <code>12:50 – 14:10</code> <i>(перемена 10 мин)</i>\n"
        f"{te(PE_CLOCK)} <b>V пара:</b> <code>14:20 – 15:40</code> <i>(перемена 10 мин)</i>\n"
        f"{te(PE_CLOCK)} <b>VI пара:</b> <code>15:50 – 17:10</code> <i>(перемена 5 мин)</i>\n"
        f"{te(PE_CLOCK)} <b>VII пара:</b> <code>17:15 – 18:35</code> <i>(перемена 5 мин)</i>\n"
        f"{te(PE_CLOCK)} <b>VIII пара:</b> <code>18:40 – 20:00</code>"
    )
