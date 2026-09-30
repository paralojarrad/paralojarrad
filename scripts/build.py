#!/usr/bin/env python3
"""Render the profile's brand SVGs from real GitHub data.

  python3 scripts/build.py --collect   # re-pull merged PRs with your local gh login, then render
  python3 scripts/build.py             # render from data/shipping.json
"""
import base64, json, statistics, subprocess, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "shipping.json"
COMMITS = ROOT / "data" / "commits.json"
ORG, SINCE = "getparalo", date(2026, 6, 1)
LONDON = ZoneInfo("Europe/London")

SERIF = "Georgia, 'Times New Roman', Times, serif"
SANS = "-apple-system, 'Helvetica Neue', Helvetica, Arial, sans-serif"
THEMES = {
    "dark":  dict(ground="#1A1815", ink="#FAF7F2", muted="#8A8378", hair="#3A352F", gold="#C49A2A", label="#C49A2A", bar="#C49A2A", line="#FAF7F2"),
    "light": dict(ground="#FAF7F2", ink="#1A1815", muted="#6B655C", hair="#E3DCCF", gold="#C49A2A", label="#7D6316", bar="#C49A2A", line="#1A1815"),
}


def gql(query, variables):
    out = subprocess.run(["gh", "api", "graphql", "-f", f"query={query}", "--input", "-"],
                         input=json.dumps({"query": query, "variables": variables}), capture_output=True, text=True)
    if out.returncode:
        sys.exit(out.stderr)
    return json.loads(out.stdout)["data"]


def collect():
    q = """query($q:String!,$after:String){ search(type:ISSUE, query:$q, first:100, after:$after){
      issueCount pageInfo{hasNextPage endCursor}
      nodes{ ... on PullRequest { createdAt mergedAt repository{ nameWithOwner } } } } }"""
    prs, start, today = [], SINCE, date.today()
    while start <= today:
        end = min(start + timedelta(days=9), today)
        after = None
        while True:
            d = gql(q, {"q": f"org:{ORG} is:pr is:merged merged:{start}..{end}", "after": after})["search"]
            if d["issueCount"] > 1000:
                sys.exit(f"window {start}..{end} exceeds the 1000-result search cap; shorten the window")
            prs += d["nodes"]
            if not d["pageInfo"]["hasNextPage"]:
                break
            after = d["pageInfo"]["endCursor"]
        start = end + timedelta(days=1)
    days = {}
    ttm, repos = [], set()
    for p in prs:
        m = datetime.fromisoformat(p["mergedAt"].replace("Z", "+00:00")).astimezone(LONDON)
        c = datetime.fromisoformat(p["createdAt"].replace("Z", "+00:00"))
        days[m.date().isoformat()] = days.get(m.date().isoformat(), 0) + 1
        ttm.append((m.astimezone(timezone.utc) - c).total_seconds() / 3600)
        repos.add(p["repository"]["nameWithOwner"])
    me = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True).stdout.strip()
    mine = gql("query($q:String!){ search(type:ISSUE, query:$q){ issueCount } }",
               {"q": f"org:{ORG} is:pr is:merged merged:>={SINCE} author:{me}"})["search"]["issueCount"]
    series = [(SINCE + timedelta(days=i)).isoformat() for i in range((today - SINCE).days + 1)]
    DATA.write_text(json.dumps({
        "since": SINCE.isoformat(), "until": today.isoformat(), "org": ORG,
        "merged": [days.get(d, 0) for d in series],
        "median_ttm_h": round(statistics.median(ttm), 3) if ttm else 0,
        "repos": len(repos), "mine": mine,
    }, indent=1))


def anim(attr, start, end, delay, dur):
    """Entrance animation whose resting state is the final value, so a renderer without SMIL still shows everything."""
    T = delay + dur
    return (f'<animate attributeName="{attr}" values="{start};{start};{end}" keyTimes="0;{delay/T:.3f};1" dur="{T:.2f}s" '
            f'begin="0s" fill="freeze" calcMode="spline" keySplines="0 0 1 1;0.2 0.7 0.2 1"/>')


def collect_commits():
    """PRs opened plus non-merge commits by me on every default branch in the org since 1 June, by London day."""
    me = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True).stdout.strip()
    today = date.today()
    first = SINCE - timedelta(days=(SINCE.weekday() + 1) % 7)   # the Sunday on or before 1 June
    repos = subprocess.run(["gh", "api", f"orgs/{ORG}/repos?per_page=100&type=all", "--paginate", "--jq",
                            ".[] | select(.archived|not) | .full_name"], capture_output=True, text=True).stdout.split()
    counts, touched = {}, 0
    for r in repos:
        out = subprocess.run(["gh", "api", f"repos/{r}/commits?author={me}&since={first}T00:00:00Z&per_page=100", "--paginate",
                              "--jq", ".[] | select((.parents|length)<2) | .commit.author.date"], capture_output=True, text=True)
        n = 0
        if out.returncode:
            continue  # empty repositories answer 409
        for line in out.stdout.splitlines():
            if not line.strip('"')[:4].isdigit():
                continue
            d = datetime.fromisoformat(line.strip('"').replace("Z", "+00:00")).astimezone(LONDON).date()
            if d >= first:
                counts[d.isoformat()] = counts.get(d.isoformat(), 0) + 1
                n += 1
        touched += 1 if n else 0
    commits_total = sum(counts.values())
    q = """query($q:String!,$after:String){ search(type:ISSUE, query:$q, first:100, after:$after){
      pageInfo{hasNextPage endCursor} nodes{ ... on PullRequest { createdAt } } } }"""
    prs, start = 0, first
    while start <= today:
        end, after = min(start + timedelta(days=9), today), None
        while True:
            d = gql(q, {"q": f"org:{ORG} is:pr author:{me} created:{start}..{end}", "after": after})["search"]
            for n in d["nodes"]:
                day = datetime.fromisoformat(n["createdAt"].replace("Z", "+00:00")).astimezone(LONDON).date().isoformat()
                counts[day] = counts.get(day, 0) + 1
                prs += 1
            if not d["pageInfo"]["hasNextPage"]:
                break
            after = d["pageInfo"]["endCursor"]
        start = end + timedelta(days=1)
    days = [(first + timedelta(days=i)).isoformat() for i in range((today - first).days + 1)]
    series = [counts.get(d, 0) for d in days]
    streak = best = 0
    for v in series:
        streak = streak + 1 if v else 0
        best = max(best, streak)
    COMMITS.write_text(json.dumps({"me": me, "org": ORG, "first": first.isoformat(), "until": today.isoformat(),
                                   "counts": series, "total": sum(series), "repos": touched, "commits": commits_total, "prs": prs,
                                   "active_days": sum(1 for v in series if v), "streak": best}, indent=1))


def shade(hex_colour, k):
    r, g, b = (int(hex_colour[i:i+2], 16) for i in (1, 3, 5))
    return "#%02X%02X%02X" % (int(r * k), int(g * k), int(b * k))


def commits_svg(d, t, name):
    first, until = date.fromisoformat(d["first"]), date.fromisoformat(d["until"])
    counts = d["counts"]
    ramp = ["#5B4A1E", "#8C6F1F", "#B8902A", "#E4C373"] if name == "dark" else ["#E4C373", "#D4AA45", "#C49A2A", "#826518"]
    empty = t["hair"]
    W, H = 1200, 536
    u = 30.0; w = u * 0.8660; dz = u * 0.5; g = 0.84
    ox, oy = 560, 70
    nz = sorted(v for v in counts if v)
    def q(v):
        return min(3, sum(1 for cut in (nz[len(nz)//4], nz[len(nz)//2], nz[3*len(nz)//4]) if v > cut)) if nz else 0
    peak = max(counts) or 1
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{d["total"]:,} contributions by {d["me"]} across Paralo repositories since 1 June">',
             f'<rect width="{W}" height="{H}" rx="18" fill="{t["ground"]}"/>',
             f'<text x="56" y="70" font-family="{SANS}" font-size="12" letter-spacing="3.2" font-weight="600" fill="{t["label"]}">WHAT I SHIPPED</text>']
    cols = (len(counts) + (0)) // 7 + 1
    for c in range(cols):
        cells = []
        for r in range(7):
            i = c * 7 + r
            if i >= len(counts): break
            v = counts[i]
            cx, cy = ox + (c - r) * w, oy + (c + r) * dz
            if v:
                h = 0.2 * u + 1.6 * u * (v / peak) ** 0.5
                top = ramp[q(v)]
                cells.append(f'<polygon points="{cx-w*g:.1f},{cy+dz*(1-g)-h+dz*g:.1f} {cx:.1f},{cy+2*dz*g-h+dz*(1-g):.1f} {cx:.1f},{cy+2*dz*g+dz*(1-g):.1f} {cx-w*g:.1f},{cy+dz*(1-g)+dz*g:.1f}" fill="{shade(top,0.72)}"/>')
                cells.append(f'<polygon points="{cx+w*g:.1f},{cy+dz*(1-g)-h+dz*g:.1f} {cx:.1f},{cy+2*dz*g-h+dz*(1-g):.1f} {cx:.1f},{cy+2*dz*g+dz*(1-g):.1f} {cx+w*g:.1f},{cy+dz*(1-g)+dz*g:.1f}" fill="{shade(top,0.5)}"/>')
                cells.append(f'<polygon points="{cx:.1f},{cy+dz*(1-g)-h:.1f} {cx+w*g:.1f},{cy+dz-h:.1f} {cx:.1f},{cy+2*dz*g+dz*(1-g)-h:.1f} {cx-w*g:.1f},{cy+dz-h:.1f}" fill="{top}"><title>{v} on {first+timedelta(days=i):%-d %b %Y}</title></polygon>')
            else:
                cells.append(f'<polygon points="{cx:.1f},{cy+dz*(1-g):.1f} {cx+w*g:.1f},{cy+dz:.1f} {cx:.1f},{cy+2*dz*g+dz*(1-g):.1f} {cx-w*g:.1f},{cy+dz:.1f}" fill="{empty}"/>')
            dd = first + timedelta(days=i)
            if r == 0 and dd.day <= 7:
                cells.append(f'<text x="{cx+w*0.9:.1f}" y="{cy-dz*0.6:.1f}" font-family="{SANS}" font-size="11" fill="{t["muted"]}">{dd:%b}</text>')
        parts.append(f'<g>{anim("opacity",0,1,0.05+c*0.016,0.5)}' + "".join(cells) + '</g>')
    parts.append(f'<text x="52" y="332" font-family="{SERIF}" font-size="128" fill="{t["ink"]}">{anim("opacity",0,1,0.1,0.8)}{d["total"]:,}</text>')
    parts.append(f'<text x="56" y="382" font-family="{SERIF}" font-size="30" fill="{t["ink"]}">contributions of mine</text>')
    parts.append(f'<text x="56" y="420" font-family="{SERIF}" font-size="30" fill="{t["ink"]}">since 1 June.</text>')
    busiest = max(range(len(counts)), key=lambda i: counts[i])
    stats = [(f'{d["prs"]:,}', "pull requests opened"), (f'{d["commits"]:,}', "commits landed on main"), (f'{d["active_days"]}', "active days")]
    for k, (num, lab) in enumerate(stats):
        x = 56 + k * 220
        parts.append(f'<text x="{x}" y="474" font-family="{SERIF}" font-size="34" fill="{t["ink"]}">{num}</text>')
        parts.append(f'<text x="{x}" y="496" font-family="{SANS}" font-size="13" fill="{t["muted"]}">{lab}</text>')
    parts.append(f'<text x="56" y="518" font-family="{SANS}" font-size="12" fill="{t["muted"]}">Pull requests opened plus non-merge commits on default branches, {d["org"]} organisation, {first:%-d %B} to {until:%-d %B %Y}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def fmt_hours(h):
    return f"{int(h)}h {int(round((h - int(h)) * 60)):02d}m" if h >= 1 else f"{int(round(h * 60))} min"


def shipping_svg(d, t):
    merged = d["merged"]
    since, until = date.fromisoformat(d["since"]), date.fromisoformat(d["until"])
    n, total = len(merged), sum(merged)
    W, H = 1200, 456
    cx0, cx1, base, top = 560, 1144, 296, 96
    peak = max(merged) or 1
    step = (cx1 - cx0) / n
    bw = max(1.5, step * 0.62)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{total:,} pull requests merged at Paralo since {since:%-d %B %Y}">',
             f'<rect width="{W}" height="{H}" rx="18" fill="{t["ground"]}"/>']
    # left column
    parts.append(f'<text x="56" y="70" font-family="{SANS}" font-size="12" letter-spacing="3.2" font-weight="600" fill="{t["label"]}">SHIPPING AT PARALO</text>')
    parts.append(f'<text x="52" y="196" font-family="{SERIF}" font-size="128" fill="{t["ink"]}">{anim("opacity",0,1,0.1,0.8)}{total:,}</text>')
    parts.append(f'<text x="56" y="246" font-family="{SERIF}" font-size="30" fill="{t["ink"]}">pull requests merged</text>')
    parts.append(f'<text x="56" y="284" font-family="{SERIF}" font-size="30" fill="{t["ink"]}">since {since:%-d %B}.</text>')
    # gridlines
    for v in (0, 25, 50, 75, 100):
        if v > peak + 15: break
        y = base - (base - top) * v / max(peak, 100 if peak > 75 else 75 if peak > 50 else 50)
        parts.append(f'<line x1="{cx0}" x2="{cx1}" y1="{y:.1f}" y2="{y:.1f}" stroke="{t["hair"]}" stroke-width="1"/>')
        parts.append(f'<text x="{cx0-10}" y="{y+4:.1f}" text-anchor="end" font-family="{SANS}" font-size="12" fill="{t["muted"]}">{v}</text>')
    scale = (base - top) / max(peak, 100 if peak > 75 else 75 if peak > 50 else 50)
    # bars, growing from the baseline
    for i, v in enumerate(merged):
        if not v: continue
        x, h = cx0 + i * step + (step - bw) / 2, v * scale
        parts.append(f'<rect x="{x:.2f}" y="{base-h:.2f}" width="{bw:.2f}" height="{h:.2f}" fill="{t["bar"]}">{anim("y",base,f"{base-h:.2f}",0.15+i*0.006,0.9)}{anim("height",0,f"{h:.2f}",0.15+i*0.006,0.9)}</rect>')
    # seven day average, drawn in
    pts = []
    for i in range(n):
        win = merged[max(0, i - 6): i + 1]
        pts.append((cx0 + i * step + step / 2, base - (sum(win) / len(win)) * scale))
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    parts.append(f'<path d="{path}" fill="none" stroke="{t["line"]}" stroke-width="2.2" stroke-linejoin="round" stroke-dasharray="3000" stroke-dashoffset="0">{anim("stroke-dashoffset",3000,0,0.4,1.6)}</path>')
    # peak label
    pi = merged.index(max(merged))
    px = cx0 + pi * step + step / 2
    anchor = "end" if px > cx1 - 120 else "start"
    parts.append(f'<text x="{px + (-8 if anchor=="end" else 8):.1f}" y="{base - peak*scale - 10:.1f}" text-anchor="{anchor}" font-family="{SANS}" font-size="13" fill="{t["ink"]}">{anim("opacity",0,1,1.6,0.5)}{peak} on {date.fromisoformat(d["since"]) + timedelta(days=pi):%-d %b}</text>')
    # month ticks
    for i in range(n):
        dd = since + timedelta(days=i)
        if dd.day == 1:
            parts.append(f'<text x="{cx0 + i*step:.1f}" y="{base+22}" font-family="{SANS}" font-size="12" fill="{t["muted"]}">{dd:%b}</text>')
    # legend
    parts.append(f'<rect x="{cx0}" y="{top-30}" width="10" height="10" rx="2" fill="{t["bar"]}"/><text x="{cx0+16}" y="{top-21}" font-family="{SANS}" font-size="12" fill="{t["muted"]}">Merged that day</text>')
    parts.append(f'<line x1="{cx0+140}" x2="{cx0+160}" y1="{top-25}" y2="{top-25}" stroke="{t["line"]}" stroke-width="2.2"/><text x="{cx0+168}" y="{top-21}" font-family="{SANS}" font-size="12" fill="{t["muted"]}">Seven day average</text>')
    # hairline + stat row
    parts.append(f'<line x1="56" x2="{cx1}" y1="338" y2="338" stroke="{t["hair"]}" stroke-width="1"/>')
    this_month = [v for i, v in enumerate(merged) if (since + timedelta(days=i)).month == until.month and (since + timedelta(days=i)).year == until.year]
    per_day = sum(this_month) / len(this_month) if this_month else 0
    stats = [(f'{d["mine"]:,}', "of them opened by me"), (fmt_hours(d["median_ttm_h"]), "median open to merge"), (f"{per_day:.1f}", f"merged per day in {until:%B}")]
    for k, (num, lab) in enumerate(stats):
        x = 56 + k * 300
        parts.append(f'<text x="{x}" y="386" font-family="{SERIF}" font-size="34" fill="{t["ink"]}">{num}</text>')
        parts.append(f'<text x="{x}" y="408" font-family="{SANS}" font-size="13" fill="{t["muted"]}">{lab}</text>')
    parts.append(f'<text x="56" y="438" font-family="{SANS}" font-size="12" fill="{t["muted"]}">Source: GitHub, {d["org"]} organisation, {since:%-d %B} to {until:%-d %B %Y}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def header_svg(t):
    kite = base64.b64encode((ROOT / "assets" / "kite.png").read_bytes()).decode()
    W, H = 1200, 340
    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Paralo. Golf clubs deserve better.">
<rect width="{W}" height="{H}" rx="18" fill="{t["ground"]}"/>
<g>{anim("opacity",0,1,0.01,0.9)}
<image x="56" y="46" width="52" height="36" xlink:href="data:image/png;base64,{kite}"/>
<text x="120" y="72" font-family="{SANS}" font-size="13" letter-spacing="4.5" font-weight="600" fill="{t["label"]}">PARALO</text>
<text x="{W-56}" y="72" text-anchor="end" font-family="{SANS}" font-size="12" letter-spacing="2.5" fill="{t["muted"]}">GETPARALO.COM</text>
</g>
<text x="54" y="188" font-family="{SERIF}" font-size="76" fill="{t["ink"]}">{anim("opacity",0,1,0.25,0.9)}Golf clubs deserve better.</text>
<text x="56" y="236" font-family="{SANS}" font-size="20" fill="{t["muted"]}">{anim("opacity",0,1,0.55,0.9)}One system for the entire club. Tee sheet, competitions, live scoring, member app, wearables, EPOS, finance.</text>
<line x1="56" x2="{W-56}" y1="286" y2="286" stroke="{t["hair"]}" stroke-width="1">{anim("x2",56,W-56,0.7,1.4)}</line>
<text x="56" y="312" font-family="{SERIF}" font-size="17" font-style="italic" fill="{t["ink"]}" opacity="0.9">{anim("opacity",0,0.9,1.3,0.9)}We move at the pace of quality.</text>
<text x="{W-56}" y="312" text-anchor="end" font-family="{SANS}" font-size="13" fill="{t["muted"]}">{anim("opacity",0,1,1.3,0.9)}Jarrad Hicks, co-founder and CEO</text>
</svg>'''


if __name__ == "__main__":
    if "--collect" in sys.argv:
        collect()
        collect_commits()
    d, c = json.loads(DATA.read_text()), json.loads(COMMITS.read_text())
    for name, t in THEMES.items():
        (ROOT / "assets" / f"shipping-{name}.svg").write_text(shipping_svg(d, t))
        (ROOT / "assets" / f"header-{name}.svg").write_text(header_svg(t))
        (ROOT / "assets" / f"commits-{name}.svg").write_text(commits_svg(c, t, name))
    print(f"{c['total']:,} contributions by {c['me']} ({c['prs']:,} PRs + {c['commits']:,} commits), {c['active_days']} active days, streak {c['streak']}")
    print(f"{sum(d['merged']):,} merged, {d['repos']} repos, median {fmt_hours(d['median_ttm_h'])}, through {d['until']}")
