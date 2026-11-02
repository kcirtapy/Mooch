"""Renders the results: an HTML page to open, and a table for the terminal."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

from .models import Hit

SOURCE_LABEL = {
    "jumbolife": "JumboLife",
    "email": "Newsletter",
    "instagram": "Instagram",
}


def _fmt_relative(when: datetime | None, now: datetime) -> str:
    if when is None:
        return "no date given"
    delta = (when - now).total_seconds()
    if delta < 0:
        return "happening now"
    minutes = int(delta // 60)
    if minutes < 60:
        return f"in {minutes} min"
    hours = minutes / 60
    if hours < 24:
        whole = int(hours)
        return "in 1 hour" if whole == 1 else f"in {whole} hours"
    days = int(hours // 24)
    return "tomorrow" if days == 1 else f"in {days} days"


def _day_label(when: datetime, now: datetime) -> str:
    if when.date() == now.date():
        return "Today"
    if (when.date() - now.date()).days == 1:
        return "Tomorrow"
    return when.strftime("%A, %B %-d")


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------


def print_table(hits: list[Hit], tz) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    now = datetime.now(timezone.utc)

    if not hits:
        console.print("\n[dim]Nothing free on the horizon. Try again after the next run.[/dim]\n")
        return

    table = Table(title=f"Free food — {len(hits)} upcoming", title_justify="left",
                  header_style="bold", box=None, pad_edge=False)
    table.add_column("When", style="yellow", no_wrap=True)
    table.add_column("What")
    table.add_column("Where", style="cyan")
    table.add_column("Who", style="dim")
    table.add_column("Conf", justify="right", style="dim", no_wrap=True)

    for hit in hits:
        when = hit.when
        when_str = (
            f"{when.astimezone(tz).strftime('%a %-m/%-d %-I:%M%p').lower()}"
            if when else "undated"
        )
        what = hit.name
        if hit.verdict.food:
            what += f"\n[dim]{hit.verdict.food}[/dim]"
        table.add_row(
            when_str,
            what,
            hit.where or "—",
            hit.item.author or SOURCE_LABEL.get(hit.item.source, hit.item.source),
            f"{hit.verdict.confidence:.0%}",
        )

    console.print()
    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

CSS = """
:root{
  --paper:#e7ebe3; --ink:#18251f; --soft:#4c5f55; --rule:#c2ccba;
  --butter:#e8b23c; --tomato:#ab3a2b; --card:#f3f5ef;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:"Bricolage Grotesque",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:17px; line-height:1.5; padding:clamp(20px,5vw,64px) clamp(18px,5vw,40px) 80px;
}
.wrap{max-width:52rem;margin:0 auto}

.masthead{display:flex;align-items:baseline;gap:.6rem;margin-bottom:clamp(24px,5vw,44px)}
.masthead h1{font-size:1.5rem;font-weight:800;letter-spacing:-.02em;margin:0}
.masthead span{font-size:.85rem;color:var(--soft)}

.next{
  border-top:3px solid var(--ink); border-bottom:1px solid var(--rule);
  padding:clamp(18px,4vw,30px) 0 clamp(20px,4vw,32px); margin-bottom:clamp(30px,6vw,52px);
}
.next .countdown{
  font-size:clamp(2.4rem,9vw,4.2rem); font-weight:800; line-height:.98;
  letter-spacing:-.035em; margin:0 0 .35rem;
}
.next .countdown em{font-style:normal;color:var(--tomato)}
.next .headline{font-size:clamp(1.1rem,3.4vw,1.5rem);font-weight:600;margin:0 0 .5rem}
.next .detail{color:var(--soft);font-size:.98rem;margin:0}
.next .headline a{color:inherit;text-decoration-thickness:1px;text-underline-offset:4px;
  text-decoration-color:var(--rule)}
.next .headline a:hover{text-decoration-color:var(--ink)}
a:focus-visible{outline:2px solid var(--butter);outline-offset:3px;border-radius:2px}

.day{margin-bottom:clamp(26px,5vw,42px)}
.day > h2{
  font-size:1.05rem; font-weight:700; margin:0 0 .9rem;
  padding-bottom:.45rem; border-bottom:1px solid var(--rule);
}
.day.today > h2{color:var(--tomato)}

.slot{display:grid;grid-template-columns:5.4rem 1fr;gap:0 1.1rem;position:relative}
.slot + .slot{margin-top:1.4rem}
.slot .time{
  font-variant-numeric:tabular-nums; font-weight:600; font-size:.95rem;
  color:var(--soft); padding-top:.1rem; text-align:right;
}
.slot .body{border-left:2px solid var(--rule);padding:0 0 0 1.1rem}
.slot.soon .body{border-left-color:var(--butter)}
.slot .what{font-size:1.06rem;font-weight:650;margin:0 0 .25rem;letter-spacing:-.01em}
.slot .what a{color:inherit;text-decoration-thickness:1px;text-underline-offset:3px;
  text-decoration-color:var(--rule)}
.slot .what a:hover{text-decoration-color:var(--ink)}
.slot .food{color:var(--tomato);font-weight:600}
.slot .meta{color:var(--soft);font-size:.9rem;margin:0}
.slot .why{color:var(--soft);font-size:.85rem;margin:.3rem 0 0;opacity:.8}

.undated{border-top:1px solid var(--rule);padding-top:1.4rem}
.undated h2{font-size:1.05rem;font-weight:700;margin:0 0 .9rem}

.empty{border-top:3px solid var(--ink);padding-top:1.6rem}
.empty p{font-size:1.15rem;margin:0 0 .4rem}
.empty span{color:var(--soft);font-size:.95rem}

footer{margin-top:3rem;color:var(--soft);font-size:.82rem}

@media (max-width:560px){
  .slot{grid-template-columns:1fr;gap:.2rem}
  .slot .time{text-align:left}
  .slot .body{border-left:none;border-top:2px solid var(--rule);padding:.5rem 0 0}
  .slot.soon .body{border-top-color:var(--butter)}
}
@media (prefers-color-scheme:dark){
  :root{--paper:#121a16;--ink:#e6ece3;--soft:#93a598;--rule:#2e3d35;--card:#18221d}
}
"""

JS = """
(function(){
  function rel(ts){
    var d=(ts*1000-Date.now())/1000;
    if(d<0) return 'happening now';
    var m=Math.floor(d/60);
    if(m<60) return 'in '+m+' min';
    var h=Math.floor(m/60);
    if(h<24) return 'in '+h+(h===1?' hour':' hours');
    var days=Math.floor(h/24);
    return days===1?'tomorrow':'in '+days+' days';
  }
  function tick(){
    document.querySelectorAll('[data-ts]').forEach(function(el){
      el.textContent=rel(parseInt(el.getAttribute('data-ts'),10));
    });
  }
  tick(); setInterval(tick,60000);
})();
"""


def write_html(hits: list[Hit], tz, path: Path, counts: dict[str, int] | None = None) -> Path:
    now = datetime.now(timezone.utc)
    dated = [h for h in hits if h.when is not None]
    undated = [h for h in hits if h.when is None]

    parts: list[str] = []
    parts.append(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Mooch</title>"
        "<link rel='preconnect' href='https://fonts.googleapis.com'>"
        "<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>"
        "<link href='https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&display=swap' rel='stylesheet'>"
        f"<style>{CSS}</style></head><body><div class='wrap'>"
    )

    stamp = now.astimezone(tz).strftime("%-I:%M %p").lower()
    parts.append(
        "<div class='masthead'><h1>Mooch</h1>"
        f"<span>checked at {html.escape(stamp)}</span></div>"
    )

    if not hits:
        parts.append(
            "<div class='empty'><p>No free food on the calendar.</p>"
            "<span>Mooch is watching. Run it again later, or add more clubs to the burner's "
            "follow list.</span></div>"
        )
    else:
        if dated:
            parts.append(_hero(dated[0], tz, now))
        _render_days(parts, dated[1:] if dated else [], tz, now)
        if undated:
            parts.append("<section class='undated'><h2>No date attached</h2>")
            for hit in undated:
                parts.append(_slot(hit, tz, now, show_time=False))
            parts.append("</section>")

    if counts:
        parts.append(
            f"<footer>{counts.get('items', 0)} items seen, "
            f"{counts.get('food', 0)} with food.</footer>"
        )

    parts.append(f"</div><script>{JS}</script></body></html>")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(parts), encoding="utf-8")
    return path


def _hero(hit: Hit, tz, now: datetime) -> str:
    when = hit.when
    local = when.astimezone(tz)
    countdown = _fmt_relative(when, now)
    food = hit.verdict.food or "Free food"

    detail_bits = []
    if hit.where:
        detail_bits.append(html.escape(hit.where))
    day = _day_label(local, now.astimezone(tz))
    clock = local.strftime("%-I:%M %p").replace("AM", "am").replace("PM", "pm")
    detail_bits.append(f"{day} at {clock}")
    if hit.item.author:
        detail_bits.append(html.escape(hit.item.author))
    detail = ", ".join(detail_bits)

    name = html.escape(hit.name)
    if hit.item.url:
        name = f"<a href='{html.escape(hit.item.url)}'>{name}</a>"

    return (
        "<section class='next'>"
        f"<p class='countdown'><em data-ts='{int(when.timestamp())}'>{html.escape(countdown)}</em></p>"
        f"<p class='headline'>{html.escape(food[0].upper() + food[1:])} at {name}</p>"
        f"<p class='detail'>{detail}</p>"
        "</section>"
    )


def _render_days(parts: list[str], hits: list[Hit], tz, now: datetime) -> None:
    current_day = None
    open_section = False
    for hit in hits:
        local = hit.when.astimezone(tz)
        label = _day_label(local, now.astimezone(tz))
        if label != current_day:
            if open_section:
                parts.append("</section>")
            cls = "day today" if label == "Today" else "day"
            parts.append(f"<section class='{cls}'><h2>{html.escape(label)}</h2>")
            current_day = label
            open_section = True
        parts.append(_slot(hit, tz, now))
    if open_section:
        parts.append("</section>")


def _slot(hit: Hit, tz, now: datetime, show_time: bool = True) -> str:
    when = hit.when
    soon = bool(when and 0 <= (when - now).total_seconds() <= 6 * 3600)

    if show_time and when:
        local = when.astimezone(tz)
        time_str = local.strftime("%-I:%M %p").replace("AM", "am").replace("PM", "pm")
    else:
        posted = hit.item.posted_at.astimezone(tz)
        time_str = f"seen {posted.strftime('%-m/%-d')}"

    food = (
        f"<span class='food'>{html.escape(hit.verdict.food)}</span> &mdash; "
        if hit.verdict.food else ""
    )

    meta = []
    if hit.where:
        meta.append(html.escape(hit.where))
    if hit.item.author:
        meta.append(html.escape(hit.item.author))
    meta.append(SOURCE_LABEL.get(hit.item.source, hit.item.source))
    meta_str = ", ".join(meta)

    name = html.escape(hit.name)
    if hit.item.url:
        name = f"<a href='{html.escape(hit.item.url)}'>{name}</a>"

    why = ""
    if hit.verdict.confidence < 0.75 and hit.verdict.reason:
        why = f"<p class='why'>Not certain: {html.escape(hit.verdict.reason)}</p>"

    return (
        f"<div class='slot{' soon' if soon else ''}'>"
        f"<div class='time'>{html.escape(time_str)}</div>"
        f"<div class='body'>"
        f"<p class='what'>{food}{name}</p>"
        f"<p class='meta'>{meta_str}</p>{why}"
        f"</div></div>"
    )
