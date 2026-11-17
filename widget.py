"""Виджет «Расписание» (Bot API 10.4): данные дня и HTML для sendWidget.

Виджет работает в песочнице без сети, поэтому все данные приносит бот:
- первый показ вшит в HTML;
- переключение дней идёт через TelegramWidget.request('d:ГГГГ-ММ-ДД') -> answerWidgetQuery (до 1024 байт).
"""
import json
import re
import zlib
from datetime import datetime
from typing import Any, Dict, List

from parser import parse_pair_times
from timeutil import BOT_TZ, now_local

ANSWER_LIMIT_BYTES = 1024        # лимит answerWidgetQuery
HTML_LIMIT_BYTES = 32768         # лимит html в sendWidget
HTML_COMPRESSED_LIMIT = 4096     # лимит html после zlib (уровень 9)
WIDGET_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_DAYS_FROM_TODAY = 90         # не даём листать виджет в бесконечность


def tz_offset_minutes() -> int:
    """Смещение часового пояса техникума от UTC в минутах (нужно виджету для «сейчас»)."""
    offset = datetime.now(BOT_TZ).utcoffset()
    return int(offset.total_seconds() // 60) if offset else 180


def short_fio(fio: str) -> str:
    """'Иванов Иван Иванович' -> 'Иванов И.И.' (уже сокращённое не трогаем)."""
    parts = (fio or "").replace("\xa0", " ").split()
    if len(parts) >= 3 and "." not in fio:
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."
    return " ".join(parts)


def _cut(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_day_payload(sched: Dict[str, Any], group_name: str, date_str: str) -> Dict[str, Any]:
    """Компактные данные дня для виджета.

    d — дата, g — группа, p — пары [номер, начало, конец, [[предмет, аудитория, преподаватель, подгруппа], ...]],
    x — прочее (практика, консультации) [[заголовок, подробность], ...], m — текст, если показать нечего,
    e — ошибка.
    """
    payload: Dict[str, Any] = {"d": date_str, "g": group_name}
    if not sched.get("success", True):
        payload["e"] = _cut(sched.get("error") or "Не удалось получить расписание", 160)
        return payload

    pairs: List[list] = []
    for lesson in sched.get("lessons", []) or []:
        t1, t2, _, _ = parse_pair_times(lesson.get("time", ""))
        items = []
        for item in lesson.get("items", []) or []:
            items.append([
                _cut(item.get("subject") or "Предмет не указан", 70),
                _cut(item.get("audience", ""), 20),
                short_fio(item.get("teacher", "")),
                _cut(item.get("subgroup", ""), 12),
            ])
        if items:
            pairs.append([str(lesson.get("pair", "")), t1 or "", t2 or "", items])
    payload["p"] = pairs

    extras: List[list] = []
    for practice in sched.get("practices", []) or []:
        title = practice.get("name", "").strip() or practice.get("title") or "Практика"
        extras.append(["Практика", _cut(title, 70)])
    for consultation in sched.get("consultations", []) or []:
        extras.append(["Консультация", _cut(consultation.get("title") or "Консультация", 70)])
    if extras:
        payload["x"] = extras

    if not pairs and not extras:
        alerts = sched.get("alerts") or []
        payload["m"] = _cut(alerts[0], 120) if alerts else "Пар нет! В этот день занятий нет."
    return payload


def _dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def fit_payload(payload: Dict[str, Any], limit: int = ANSWER_LIMIT_BYTES) -> str:
    """JSON данных дня ≤ limit байт (кириллица — 2 байта/символ): при нехватке места упрощаем."""
    def size(p: Dict[str, Any]) -> int:
        return len(_dumps(p).encode("utf-8"))

    p = json.loads(_dumps(payload))   # глубокая копия
    if size(p) <= limit:
        return _dumps(p)

    steps = (
        lambda: [it.__setitem__(3, "") for pair in p.get("p", []) for it in pair[3]],      # подгруппы
        lambda: [it.__setitem__(2, "") for pair in p.get("p", []) for it in pair[3]],      # преподаватели
        lambda: [it.__setitem__(0, _cut(it[0], 32)) for pair in p.get("p", []) for it in pair[3]],
        lambda: p.pop("x", None),
        lambda: [it.__setitem__(0, _cut(it[0], 18)) for pair in p.get("p", []) for it in pair[3]],
    )
    for step in steps:
        step()
        if size(p) <= limit:
            return _dumps(p)
    # Совсем много подгрупп: оставляем столько пар, сколько влезает.
    while p.get("p") and size(p) > limit:
        p["p"].pop()
        p["t"] = 1   # признак «показаны не все пары»
    return _dumps(p)


WIDGET_TEMPLATE = """<style>
html{--fg:#111;--mut:#6b7280;--acc:#2481cc}
html[data-t=dark]{--fg:#f5f5f5;--mut:#9aa7b4;--acc:#6ab3f3}
body{margin:0;padding:10px 12px;font:14px/1.35 system-ui,-apple-system,sans-serif;color:var(--fg)}
.top{display:flex;align-items:center;gap:6px}
.nav{flex:0 0 auto;border:0;border-radius:8px;background:rgba(127,127,127,.18);color:var(--fg);font:inherit;padding:6px 11px}
.nav:active{opacity:.6}
.ttl{flex:1;text-align:center;min-width:0}
.ttl b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ttl span{color:var(--mut);font-size:12px}
.st{margin:8px 0 6px;color:var(--acc);font-weight:600;font-size:13px;min-height:16px}
.p{margin:6px 0;padding:7px 9px;border-radius:10px;background:rgba(127,127,127,.13)}
.p.now{background:rgba(36,129,204,.28);box-shadow:inset 3px 0 0 var(--acc)}
.p.done{opacity:.5}
.h{display:flex;justify-content:space-between;color:var(--mut);font-size:12px;margin-bottom:2px}
.s{font-weight:600}
.i{color:var(--mut);font-size:12px}
.sub{margin-top:5px}
.m{margin:14px 4px;text-align:center}
.ld{opacity:.5}
</style>
<div class="top"><button class="nav" id="pv">‹</button><div class="ttl"><b id="g"></b><span id="dt"></span></div><button class="nav" id="td">Сегодня</button><button class="nav" id="nx">›</button></div>
<div class="st" id="st"></div>
<div id="c"></div>
<script>
var W=window.TelegramWidget,D=__DATA__,TZ=__TZ__,busy=false;
var DN=['вс','пн','вт','ср','чт','пт','сб'],MN=['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];
var RM={'1':'I','2':'II','3':'III','4':'IV','5':'V','6':'VI','7':'VII','8':'VIII'};
function $(i){return document.getElementById(i)}
function theme(){document.documentElement.setAttribute('data-t',W&&W.colorScheme==='dark'?'dark':'light')}
function nowC(){return new Date(Date.now()+TZ*60000)}
function todayS(){return nowC().toISOString().slice(0,10)}
function mins(t){var a=(t||'').split(':');return a.length==2?(+a[0])*60+(+a[1]):-1}
function shift(ds,n){var a=ds.split('-'),d=new Date(Date.UTC(+a[0],a[1]-1,+a[2]));d.setUTCDate(d.getUTCDate()+n);if(d.getUTCDay()===0)d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10)}
function label(ds){var a=ds.split('-'),d=new Date(Date.UTC(+a[0],a[1]-1,+a[2]));return DN[d.getUTCDay()]+', '+(+a[2])+' '+MN[a[1]-1]}
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function status(){
  var s=$('st');if(D.d!==todayS()||!D.p||!D.p.length){s.textContent='';return}
  var n=nowC(),m=n.getUTCHours()*60+n.getUTCMinutes(),i;
  for(i=0;i<D.p.length;i++){var a=mins(D.p[i][1]),b=mins(D.p[i][2]);if(a<0||b<0)continue;
    if(m>=a&&m<b){s.textContent='Идёт '+(RM[D.p[i][0]]||D.p[i][0])+' пара · ещё '+(b-m)+' мин';return}
    if(m<a){s.textContent='До '+(RM[D.p[i][0]]||D.p[i][0])+' пары: '+(a-m)+' мин';return}}
  s.textContent='Пары на сегодня закончились'
}
function render(){
  $('g').textContent=D.g?('Группа '+D.g):'Расписание';$('dt').textContent=label(D.d);
  var c=$('c');c.textContent='';
  if(D.e){c.appendChild(el('div','m',D.e));$('st').textContent='';return}
  var isT=D.d===todayS(),n=nowC(),m=n.getUTCHours()*60+n.getUTCMinutes();
  (D.x||[]).forEach(function(x){var p=el('div','p');p.appendChild(el('div','h',x[0]));p.appendChild(el('div','s',x[1]));c.appendChild(p)});
  (D.p||[]).forEach(function(pr){
    var a=mins(pr[1]),b=mins(pr[2]),p=el('div','p');
    if(isT&&a>=0&&b>=0){if(m>=a&&m<b)p.className+=' now';else if(m>=b)p.className+=' done'}
    var h=el('div','h');h.appendChild(el('span',null,(RM[pr[0]]||pr[0])+' пара'));h.appendChild(el('span',null,pr[1]?pr[1]+'–'+pr[2]:''));p.appendChild(h);
    pr[3].forEach(function(it,k){var w=el('div',k?'sub':null);
      w.appendChild(el('div','s',(it[3]?it[3]+' · ':'')+it[0]));
      var inf=[it[1]?'ауд. '+it[1]:'',it[2]].filter(Boolean).join(' · ');if(inf)w.appendChild(el('div','i',inf));p.appendChild(w)});
    c.appendChild(p)});
  if(D.t)c.appendChild(el('div','m','Показаны не все пары — открой полное расписание в чате'));
  if(D.m)c.appendChild(el('div','m',D.m));
  status()
}
function load(ds){
  if(!W||busy)return;busy=true;$('c').className='ld';
  W.request('d:'+ds).then(function(r){var d=null;try{d=JSON.parse(r.result)}catch(e){}
    D=d||{d:ds,g:D.g,e:'Не удалось прочитать ответ'}},
  function(e){D={d:ds,g:D.g,e:e&&e.code==='RATE_LIMITED'?'Слишком часто, подожди пару секунд':e&&e.code==='TIMEOUT'?'Сайт техникума долго отвечает, попробуй ещё раз':'Не удалось загрузить расписание'}})
  .then(function(){busy=false;$('c').className='';render()})
}
$('pv').addEventListener('click',function(){load(shift(D.d,-1))});
$('nx').addEventListener('click',function(){load(shift(D.d,1))});
$('td').addEventListener('click',function(){load(todayS())});
if(W&&W.onEvent){W.onEvent('themeChanged',theme)}
theme();render();setInterval(status,30000);
</script>"""


def build_widget_html(payload: Dict[str, Any]) -> str:
    """HTML виджета с вшитым первым днём. '<' экранируем, чтобы данные не закрыли <script>."""
    data = _dumps(payload).replace("<", "\\u003c")
    html_text = WIDGET_TEMPLATE.replace("__DATA__", data).replace("__TZ__", str(tz_offset_minutes()))
    return html_text


def check_widget_size(html_text: str) -> None:
    """Проверка лимитов Telegram до отправки (иначе придёт непонятная ошибка API)."""
    raw = html_text.encode("utf-8")
    if len(raw) > HTML_LIMIT_BYTES:
        raise ValueError(f"HTML виджета {len(raw)} байт > {HTML_LIMIT_BYTES}")
    packed = len(zlib.compress(raw, 9))
    if packed > HTML_COMPRESSED_LIMIT:
        raise ValueError(f"HTML виджета после zlib {packed} байт > {HTML_COMPRESSED_LIMIT}")


def is_allowed_date(date_str: str) -> bool:
    """Дата из запроса виджета: формат ГГГГ-ММ-ДД и не дальше MAX_DAYS_FROM_TODAY от сегодня."""
    if not WIDGET_DATE_RE.fullmatch(date_str or ""):
        return False
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return False
    return abs((target - now_local().replace(hour=0, minute=0, second=0, microsecond=0)).days) <= MAX_DAYS_FROM_TODAY
