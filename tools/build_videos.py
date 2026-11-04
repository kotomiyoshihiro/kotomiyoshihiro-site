#!/usr/bin/env python3
"""videos/videos.json を、personal-hub の予約の記録から作る。

読むもの(personal-hub/publicity/kotomi-yoshihiro/ の中。書き換えはしない):
  - posting-schedule.md        YouTube のショートの行(日付・時刻・中身・状態・URL)。正本
  - youtube-shorts-posts.md    10/22 に公開した 9 本の表(posting-schedule.md は 10/25 から)
                               と、題・再生リストの表
  - youtube-reupload-2026-11.md 上げ直しで非公開にした古い ID(「旧 ID」「← ID」「古い 6 本」)と、
                               ID ごとの再生リスト
  - shorts-captions-*.md       題と単元(再生リスト)の表
  - shorts-stats.csv           公開済みの動画の、YouTube 上の題

ページ(videos/index.html)は、各動画の publishAt(日本時間)を過ぎたものだけを出す。
予約を足したら、このスクリプトを流し直して videos/videos.json を commit する。

使い方:
  python tools/build_videos.py [--src <kotomi-yoshihiro フォルダ>] [--out videos/videos.json] [--now 2026-11-04T12:00]
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ID = r"[A-Za-z0-9_-]{11}"
ID_END = r"(?![A-Za-z0-9_-])"
FALLBACK_UNIT = "そのほか"
PLAYLIST_PREFIX = "中学受験の理科｜"

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SRC = REPO.parent / "personal-hub" / "publicity" / "kotomi-yoshihiro"


def read(path):
    return path.read_text(encoding="utf-8")


def table_rows(text):
    """Markdown の表を (見出しの列名リスト, 行のセルのリスト, 行番号) で返す。"""
    header = None
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
            continue
        if header is None:
            header = cells
            continue
        yield header, cells, i


def col(header, *names):
    for n in names:
        if n in header:
            return header.index(n)
    return None


def card_of(cell):
    m = re.match(r"\s*(\d{3})(?!\d)", cell or "")
    return m.group(1) if m else None


def display_title(t):
    t = re.sub(r"\s*説明できる？\s*$", "", t.strip())
    return t


# ---------- 非公開(古い)ID ----------

def private_ids(texts):
    ids = set()
    for text in texts:
        ids.update(re.findall(r"旧\s*(" + ID + ")" + ID_END, text))
        ids.update(re.findall(r"←\s*(" + ID + ")" + ID_END, text))
        for m in re.finditer(r"古い\s*6\s*本[(（]([^)）]*)[)）]を非公開", text):
            ids.update(re.findall(r"(?<![A-Za-z0-9_-])(" + ID + ")" + ID_END, m.group(1)))
    # 上げ直しの表の「古い方(非公開にする)」の列
    for text in texts:
        for header, cells, _ in table_rows(text):
            c = col(header, "古い方(非公開にする)")
            if c is not None and c < len(cells):
                ids.update(re.findall(ID, cells[c]))
    return ids


# ---------- 単元(再生リスト)と題 ----------

def known_units(posts_text):
    units = []
    for name in re.findall(re.escape(PLAYLIST_PREFIX) + r"([^|」\s]+)", posts_text):
        if name not in units:
            units.append(name)
    return units


def clean_unit(raw, units):
    if not raw:
        return None
    raw = raw.replace(PLAYLIST_PREFIX, "")
    raw = re.split(r"[(（]", raw)[0].strip()
    return raw if raw in units else None


def build_lookups(src, units):
    """カード番号 → 題、カード番号 → 単元、動画 ID → 単元、動画 ID → 題(YouTube 上)。"""
    title_by_card, unit_by_card, unit_by_id, title_by_id = {}, {}, {}, {}

    def put(d, k, v):
        if k and v and k not in d:
            d[k] = v

    # 優先の高い順に読む(先に入った方を残す)
    caption_files = sorted(src.glob("shorts-captions-*.md"), reverse=True)  # 新しい月から
    for f in caption_files + [src / "youtube-shorts-posts.md"]:
        if not f.exists():
            continue
        for header, cells, _ in table_rows(read(f)):
            ci = col(header, "Card")
            if ci is None or ci >= len(cells):
                continue
            card = card_of(cells[ci])
            ti = col(header, "題(YouTube)", "題", "題(今と同じ)")
            if ti is not None and ti < len(cells) and "説明できる？" in cells[ti]:
                put(title_by_card, card, cells[ti])
            ui = col(header, "単元(再生リスト)")
            if ui is not None and ui < len(cells):
                put(unit_by_card, card, clean_unit(cells[ui], units))

    # youtube-shorts-posts.md の再生リストの表: 「004 鏡に…説明できる？ / 005 …」
    posts = src / "youtube-shorts-posts.md"
    if posts.exists():
        for header, cells, _ in table_rows(read(posts)):
            pi, vi = col(header, "再生リスト"), col(header, "動画(Card と題)")
            if pi is None or vi is None or vi >= len(cells):
                continue
            unit = clean_unit(cells[pi], units)
            for m in re.finditer(r"(?<!\d)(\d{3})(?!\d)\s*([^/]*?説明できる？)", cells[vi]):
                put(unit_by_card, m.group(1), unit)
                put(title_by_card, m.group(1), m.group(2).strip())

    # 上げ直しの記録: 「… https://youtube.com/shorts/ID (単元)」と「題「…説明できる？」」
    reup = src / "youtube-reupload-2026-11.md"
    if reup.exists():
        for line in read(reup).splitlines():
            for m in re.finditer(r"shorts/(" + ID + r")" + ID_END + r"\s*[(（]([^)）]+)[)）]", line):
                put(unit_by_id, m.group(1), clean_unit(m.group(2), units))
            t = re.search(r"題「([^」]*説明できる？)」", line)
            c = re.search(r"(?<![\d:/.-])(\d{3})(?![\d:])", line)
            if t and c:
                put(title_by_card, c.group(1), t.group(1))

    stats = src / "shorts-stats.csv"
    if stats.exists():
        with stats.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("video_id") and row.get("title"):
                    title_by_id[row["video_id"]] = row["title"]  # 新しい行で上書き

    return title_by_card, unit_by_card, unit_by_id, title_by_id


# ---------- 動画の行 ----------

def schedule_entries(text, warn):
    """posting-schedule.md の YouTube ショートの行。"""
    year, last_month = None, None
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        h = re.match(r"#{2,4}\s*(\d{4})-(\d{2})-\d{2}", line)
        if h:
            year, last_month = int(h.group(1)), int(h.group(2))
            continue
        s = line.strip()
        if not s.startswith("|"):
            continue
        c = [x.strip() for x in s.strip("|").split("|")]
        if len(c) < 7 or c[2] != "YouTube":
            continue
        date, time_, kind, content, status, url = c[0], c[1], c[3], c[4], c[5], c[6]
        if "ショート" not in kind:
            continue  # 長い動画など
        if status.startswith("出さない"):
            continue
        m = re.search(r"shorts/(" + ID + ")" + ID_END, url)
        if not m:
            warn(f"posting-schedule.md:{i} URL がない行を飛ばした: {date} {content[:20]}")
            continue
        d = re.fullmatch(r"(?:(\d{4})/)?(\d{1,2})/(\d{1,2})", date)
        t = re.match(r"(\d{1,2}):(\d{2})", time_)
        if not d or not t:
            warn(f"posting-schedule.md:{i} 日時が読めない行を飛ばした: {date} {time_}")
            continue
        month = int(d.group(2))
        if d.group(1):
            year = int(d.group(1))
        elif year is None:
            warn(f"posting-schedule.md:{i} 年が分からない行を飛ばした")
            continue
        elif last_month and month < last_month:
            year += 1
        last_month = month
        when = datetime(year, month, int(d.group(3)), int(t.group(1)), int(t.group(2)), tzinfo=JST)
        unit = re.search(r"再生リスト「([^」]+)」", status)
        out.append({
            "id": m.group(1),
            "card": card_of(content),
            "name": re.split(r"[(（`]", content)[0].strip(),
            "publishAt": when,
            "unit_hint": unit.group(1) if unit else None,
            "src": f"posting-schedule.md:{i}",
        })
    return out


def first_day_entries(text, warn):
    """youtube-shorts-posts.md の「公開した 9 本(2026-10-22 …)」の表。"""
    m = re.search(r"^##\s*公開した\s*\d+\s*本[(（](\d{4})-(\d{2})-(\d{2})(.*?)(?=^##\s)", text, re.S | re.M)
    if not m:
        warn("youtube-shorts-posts.md の「公開した 9 本」の節が見つからない")
        return []
    when = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST)
    out = []
    for header, cells, _ in table_rows(m.group(4)):
        ui = col(header, "URL")
        ci = col(header, "Card")
        if ui is None or ci is None:
            continue
        idm = re.search(r"shorts/(" + ID + ")" + ID_END, cells[ui])
        if idm:
            out.append({"id": idm.group(1), "card": card_of(cells[ci]), "name": cells[ci],
                        "publishAt": when, "unit_hint": None, "src": "youtube-shorts-posts.md(公開した 9 本)"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=REPO / "videos" / "videos.json")
    ap.add_argument("--now", help="集計に使う日本時間(例 2026-11-04T12:00)。既定は今")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    warnings = []
    warn = warnings.append
    src = args.src
    schedule = src / "posting-schedule.md"
    if not schedule.exists():
        sys.exit(f"見つからない: {schedule}")
    posts_text = read(src / "youtube-shorts-posts.md") if (src / "youtube-shorts-posts.md").exists() else ""
    reup_text = read(src / "youtube-reupload-2026-11.md") if (src / "youtube-reupload-2026-11.md").exists() else ""
    sched_text = read(schedule)

    units = known_units(posts_text)
    if not units:
        sys.exit("再生リストの名前(中学受験の理科｜…)が見つからない")
    private = private_ids([reup_text, sched_text, posts_text])
    title_by_card, unit_by_card, unit_by_id, title_by_id = build_lookups(src, units)

    raw = first_day_entries(posts_text, warn) + schedule_entries(sched_text, warn)
    videos, seen, skipped_private = [], set(), []
    for e in raw:
        if e["id"] in private:
            skipped_private.append(f'{e["card"]} {e["id"]} ({e["src"]})')
            continue
        if e["id"] in seen:
            warn(f'同じ ID が二度ある: {e["id"]} ({e["src"]})')
            continue
        seen.add(e["id"])
        card = e["card"]
        unit = (clean_unit(e["unit_hint"], units) or unit_by_id.get(e["id"])
                or unit_by_card.get(card))
        if not unit:
            unit = FALLBACK_UNIT
            warn(f'単元が分からない → 「{FALLBACK_UNIT}」: {card} {e["name"]} {e["id"]}')
        title = title_by_id.get(e["id"]) or title_by_card.get(card)
        if not title:
            title = e["name"]
            warn(f'題が見つからない → 記録の名前を使う: {e["name"]} {e["id"]}')
        videos.append({
            "id": e["id"],
            "card": card,
            "title": display_title(title),
            "unit": unit,
            "publishAt": e["publishAt"].isoformat(),
        })

    cards = {}
    for v in videos:
        cards.setdefault(v["card"], []).append(v["id"])
    for card, ids in cards.items():
        if len(ids) > 1:
            warn(f"同じカードが複数の ID で載っている: {card} {ids}")

    # 単元の並び: その単元のいちばん小さいカード番号の順(本の章の順になる)
    def unit_key(u):
        if u == FALLBACK_UNIT:
            return (2, "")
        nums = [int(v["card"]) for v in videos if v["unit"] == u and v["card"]]
        return (0 if nums else 1, min(nums) if nums else 0)
    used_units = sorted({v["unit"] for v in videos}, key=unit_key)
    videos.sort(key=lambda v: (used_units.index(v["unit"]), v["card"] or "", v["publishAt"]))

    data = {
        "note": "tools/build_videos.py が personal-hub の予約の表から作るファイル。手で直さない。",
        "units": used_units,
        "videos": videos,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    now = (datetime.fromisoformat(args.now).replace(tzinfo=JST) if args.now else datetime.now(JST))
    published = [v for v in videos if datetime.fromisoformat(v["publishAt"]) <= now]
    print(f"書き出し: {args.out}")
    print(f"動画: {len(videos)} 本 / {now:%Y-%m-%d %H:%M} JST で公開済み {len(published)} 本")
    for u in used_units:
        n_all = sum(1 for v in videos if v["unit"] == u)
        n_pub = sum(1 for v in published if v["unit"] == u)
        print(f"  {u}: 公開済み {n_pub} / 全 {n_all}")
    print(f"非公開の古い ID として外した行: {len(skipped_private)}")
    for s in skipped_private:
        print(f"  - {s}")
    if warnings:
        print("注意:")
        for w in warnings:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
