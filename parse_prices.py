#!/usr/bin/env python3
"""
parse_prices.py - แปลงข้อความราคาจากร้านเป็น JSON และ regenerate viewer.html

วิธีใช้:
  python3 parse_prices.py <ไฟล์ข้อความ>          # อ่านจากไฟล์
  python3 parse_prices.py --paste                 # วางข้อความโดยตรง
  python3 parse_prices.py --list                  # แสดงรายการ snapshot ที่มี
  python3 parse_prices.py --rebuild               # สร้าง viewer.html ใหม่จาก DB

ตัวอย่าง:
  python3 parse_prices.py new_prices.txt
"""

import sys
import json
import re
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, 'prices_db.json')
VIEWER_TEMPLATE = os.path.join(SCRIPT_DIR, 'viewer_template.html')
VIEWER_OUT = os.path.join(SCRIPT_DIR, 'viewer.html')


# ──────────────────────────────────────────────
# DATE HELPERS
# ──────────────────────────────────────────────

MONTH_MAP = {
    'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
    'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12,
    'january':1,'february':2,'march':3,'april':4,'june':6,
    'july':7,'august':8,'september':9,'october':10,'november':11,'december':12,
}

def detect_date(lines):
    """หาวันที่จากบรรทัดแรกๆ ของข้อความ"""
    for line in lines[:8]:
        # "25 May 26" or "25 may 2026"
        m = re.search(r'(\d{1,2})\s+([a-zA-Z]+)\s+(\d{2,4})', line)
        if m:
            day = int(m.group(1))
            mo_str = m.group(2).lower()[:3]
            mo = MONTH_MAP.get(mo_str)
            yr = int(m.group(3))
            if yr < 100:
                yr += 2000
            if mo and 1 <= day <= 31:
                return f'{yr}-{mo:02d}-{day:02d}'
        # "25/05/2569" Thai year
        m2 = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', line)
        if m2:
            yr = int(m2.group(3))
            if yr > 2500:
                yr -= 543
            return f'{yr}-{int(m2.group(2)):02d}-{int(m2.group(1)):02d}'
    return datetime.today().strftime('%Y-%m-%d')


def iso_to_thai(iso):
    """'2026-05-25' -> '25/05/2569'"""
    y, m, d = iso.split('-')
    return f'{d}/{m}/{int(y)+543}'


# ──────────────────────────────────────────────
# PARSER
# ──────────────────────────────────────────────

PRICE_RE = re.compile(r'(\d[\d,]+)\s*[-–]\s*(\d[\d,]+)')
# Match RAM/storage: "4/64", "4/64GB", "128GB" — but NOT bare "5G" connectivity marker
STORAGE_RE = re.compile(r'(\d+/\d+\s*(?:[gG][bB])?|\d+\s*[gG][bB])(?=\s|$)')


def parse_price(s):
    return int(s.replace(',', ''))


def clean(s):
    return re.sub(r'\s+', ' ', s.strip())


def detect_section(line):
    # Lines with prices or storage are items, not section headers
    if PRICE_RE.search(line):
        return None
    if re.search(r'\d+/\d+|\d+[gG][bB]', line):
        return None
    # Strip leading emoji/symbols then lowercase
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', line).lower().strip()
    if re.match(r'samsung', cleaned):  return 'Samsung'
    if re.match(r'oppo', cleaned):     return 'OPPO'
    if re.match(r'vivo', cleaned):     return 'Vivo'
    if re.match(r'redmi', cleaned):    return 'Redmi'
    if re.match(r'realme', cleaned):   return 'Realme'
    return None


def is_section_separator(line):
    return bool(re.match(r'^[-—=]{3,}', line.strip()))


def parse_text(text):
    lines = [l.strip() for l in text.splitlines()]
    non_empty = [l for l in lines if l]

    date_iso = detect_date(non_empty)
    items = []
    section = 'iPhone'  # default — Apple products listed first

    i = 0
    while i < len(non_empty):
        line = non_empty[i]

        # Skip boilerplate intro lines (Thai-only keywords, not brand headers)
        if any(kw in line for kw in ['📌','📉','💬','🍎','ขอบคุณ','ขอความ','ราคาอาจ','อัปเดต','ก่อนส่ง','สั่งสี','ทั้งนี้','โปรดอ่าน','แจ้งได้','ปรับเปลี่ยน','รอติดตาม','ความเข้าใจ']):
            i += 1
            continue

        # Skip pure date lines like "25 May 26"
        if re.match(r'^\d{1,2}\s+[a-zA-Z]+\s+\d{2,4}\s*$', line):
            i += 1
            continue

        # Detect brand section switch
        new_sec = detect_section(line)
        if new_sec:
            section = new_sec
            i += 1
            continue

        # iPad header (line with 'ipad' but no price)
        if re.search(r'\bipad\b', line, re.I) and not PRICE_RE.search(line):
            section = 'iPad'
            i += 1
            continue

        # Section separator
        if is_section_separator(line):
            i += 1
            continue

        # ── Android compact format: model storage color price ──
        if section in ('Samsung', 'OPPO', 'Vivo', 'Redmi', 'Realme'):
            pm = PRICE_RE.search(line)
            if pm:
                lo = parse_price(pm.group(1))
                hi = parse_price(pm.group(2))
                before = line[:pm.start()].strip()
                # Extract storage
                sm = STORAGE_RE.search(before)
                if not sm:
                    # Fallback: only match recognized storage sizes to avoid matching model numbers
                    sm = re.search(r'(?<!\d)(64|128|256|512|1024)\s*(?:[gG][bB]?)?(?=\s|$)', before)
                if sm:
                    raw_storage = sm.group(0).strip()
                    if not re.search(r'[gG][bB]$', raw_storage):
                        raw_storage += 'GB'
                    before_storage = before[:sm.start()].strip()
                    after_storage = before[sm.end():].strip()
                else:
                    raw_storage = '-'
                    before_storage = before
                    after_storage = ''

                # Model name
                model_raw = before_storage
                if section == 'Samsung':
                    model_raw = re.sub(r'^galaxy\s*', '', model_raw, flags=re.I)
                    model = 'Galaxy ' + clean(model_raw)
                elif section == 'OPPO':
                    model_raw = re.sub(r'^oppo\s*', '', model_raw, flags=re.I)
                    model = 'OPPO ' + clean(model_raw)
                elif section == 'Vivo':
                    model_raw = re.sub(r'^vivo\s*', '', model_raw, flags=re.I)
                    model = 'Vivo ' + clean(model_raw)
                elif section == 'Redmi':
                    model_raw = re.sub(r'^redmi\s*', '', model_raw, flags=re.I)
                    model = 'Redmi ' + clean(model_raw)
                else:
                    model = clean(model_raw)

                color_raw = after_storage if after_storage else 'คละสี'
                color_raw = re.sub(r'^=\s*', '', color_raw).strip()
                # Absorb model suffix keywords (ultra/pro/max/fe/lite/5g) into model name
                if section in ('Samsung', 'OPPO', 'Vivo', 'Redmi', 'Realme'):
                    SUFFIX_RE = re.compile(r'^(ultra[s]?|pro|max|fe|lite|plus|5g|4g)(\s+(ultra[s]?|pro|max|fe|lite|plus|5g|4g))*', re.I)
                    sfx_m = SUFFIX_RE.match(color_raw)
                    if sfx_m:
                        sfx = re.sub(r'\bultras\b', 'Ultra', sfx_m.group(0), flags=re.I).strip().title()
                        model = model + ' ' + sfx
                        color_raw = color_raw[sfx_m.end():].strip()
                # Normalize colors to Title/Case
                color_raw = re.sub(r'^=\s*', '', color_raw).strip()
                color = '/'.join(c.strip().capitalize() for c in re.split(r'[\s/]+', color_raw) if c.strip())
                if not color or color.lower() in ('คละสี', 'ไม่ต้องเยอะ', '='):
                    color = 'คละสี'

                if model and len(model) > 3 and lo > 0:
                    items.append({'brand': section, 'model': model, 'storage': raw_storage, 'color': color, 'lo': lo, 'hi': hi})
            i += 1
            continue

        # ── Accessories ──
        if section == 'Accessories' or re.search(r'อะแดปเตอร์|adapter|สาย\s*c|หูฟัง|airpod|pencil|pen usb|‎', line, re.I):
            if section != 'Accessories':
                section = 'Accessories'
            pm = re.search(r'(\d[\d,]+)\s*[-–=]\s*(\d[\d,]+)', line)
            if pm:
                lo = parse_price(pm.group(1))
                hi = parse_price(pm.group(2))
                model = clean(line[:pm.start()].rstrip('= ').strip())
                if model and lo > 0:
                    items.append({'brand': 'Accessories', 'model': model, 'storage': '-', 'color': '-', 'lo': lo, 'hi': hi})
            i += 1
            continue

        # ── iPhone / iPad multi-line format ──
        # Model line: contains storage pattern or known model keywords
        # Collect: model_line, [color_line], price_line(s)
        is_model_line = bool(
            re.search(r'(\d+\s*[gt]b|\d+/\d+|iphone|ipad|ip\s*\d+|\b1[3-9]\b|\b2[0-9]\b)', line, re.I)
            and not PRICE_RE.search(line)
        )

        if is_model_line:
            model_line = line
            j = i + 1
            color_lines = []
            price_entries = []

            while j < len(non_empty) and j < i + 8:
                nxt = non_empty[j]
                if is_section_separator(nxt):
                    break
                if detect_section(nxt):
                    break
                pm = PRICE_RE.search(nxt)
                if pm:
                    lo = parse_price(pm.group(1))
                    hi = parse_price(pm.group(2))
                    prefix = nxt[:pm.start()].strip()
                    price_entries.append({'lo': lo, 'hi': hi, 'color_prefix': prefix})
                    j += 1
                    continue
                # If we already have at least one price and this looks like a new model line → stop
                nxt_is_model = bool(
                    re.search(r'(\d+\s*[gG][bB]|\d+/\d+|iphone|ipad|ip\s*\d+|\b1[3-9]\b|\b2[0-9]\b)', nxt, re.I)
                    and not PRICE_RE.search(nxt)
                )
                if price_entries and nxt_is_model:
                    break
                if nxt and not is_section_separator(nxt) and not detect_section(nxt):
                    color_lines.append(nxt)
                j += 1

            # Parse model line
            parsed = _parse_apple_model_line(model_line, section)
            if parsed['model'] and price_entries:
                base_color = '/'.join(color_lines) if color_lines else 'คละสี'
                base_color = _normalize_color(base_color)
                for pe in price_entries:
                    color = _normalize_color(pe['color_prefix']) if pe['color_prefix'] else base_color
                    items.append({
                        'brand': section,
                        'model': parsed['model'],
                        'storage': parsed['storage'],
                        'color': color,
                        'lo': pe['lo'],
                        'hi': pe['hi'],
                    })
                i = j
                continue

        i += 1

    return {'date_iso': date_iso, 'items': items}


def _normalize_color(s):
    s = re.sub(r'\*[^*]*\*', '', s).strip()
    s = re.sub(r'(ไม่ต้องเยอะ|ไม่ชัว[รา]*ค[าั]*)', '', s, flags=re.I).strip()
    parts = re.split(r'[\s/]+', s)
    parts = [p.capitalize() for p in parts if p and p not in ('คละสี', '-')]
    return '/'.join(parts) if parts else 'คละสี'


def _parse_apple_model_line(line, section):
    line = re.sub(r'\*[^*]*\*', '', line).strip()
    line = re.sub(r'(ไม่ต้องเยอะ|ไม่ชัว[รา]*ค[าั]*)', '', line, flags=re.I).strip()

    if section == 'iPhone':
        line = re.sub(r'^(ip)\s+', 'iPhone ', line, flags=re.I)
        line = re.sub(r'^(iphone)\s*', 'iPhone ', line, flags=re.I)
        if not line.lower().startswith('iphone'):
            line = 'iPhone ' + line
        # Normalize "128G" → "128GB"
        line = re.sub(r'\b(\d+)([gG])(?![bB])\b', r'\1GB', line)

        storage = ''
        # TB first
        sm = re.search(r'(\d+)\s*[tT][bB](?=\s|$)', line)
        if sm:
            storage = sm.group(0).strip().upper()
            line = (line[:sm.start()] + line[sm.end():]).strip()

        if not storage:
            # RAM/storage slash: "8/256" or "8/256GB"
            sm = re.search(r'(\d+/\d+)\s*(?:[gG][bB]?)?(?=\s|$)', line)
            if sm:
                storage = sm.group(0).strip()
                if not re.search(r'[gG][bB]$', storage):
                    storage += 'GB'
                line = (line[:sm.start()] + line[sm.end():]).strip()

        if not storage:
            # Bare storage number: 128, 256, 512 — optionally followed by GB
            sm = re.search(r'(?<!\d)(128|256|512|64|1024)\s*[gG]?[bB]?(?=\s|$)', line)
            if sm:
                storage = sm.group(1) + 'GB'
                line = (line[:sm.start()] + line[sm.end():]).strip()

        model = clean(line)
        return {'model': model, 'storage': storage}

    else:  # iPad
        line = re.sub(r'^(ipad)\s*', 'iPad ', line, flags=re.I)
        if not line.lower().startswith('ipad'):
            line = 'iPad ' + line

        # Extract WiFi/SIM + storage
        sm = re.search(r'(wi-?fi|sim)?\s*(\d+[gG][bB])', line, re.I)
        storage = ''
        if sm:
            storage = clean(sm.group(0))
            line = (line[:sm.start()] + line[sm.end():]).strip()

        model = clean(line)
        return {'model': model, 'storage': storage}


# ──────────────────────────────────────────────
# DB HELPERS
# ──────────────────────────────────────────────

def load_db():
    if os.path.exists(DB_PATH):
        with open(DB_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'snapshots': []}


def save_db(db):
    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def add_snapshot(db, date_iso, items, source='ร้าน A'):
    date_th = iso_to_thai(date_iso)
    snapshot = {'id': date_iso, 'date': date_th, 'date_iso': date_iso, 'source': source, 'items': items}
    existing = next((i for i, s in enumerate(db['snapshots']) if s['date_iso'] == date_iso), -1)
    if existing >= 0:
        print(f'  ⚠️  มีข้อมูลวันที่ {date_iso} อยู่แล้ว ({len(db["snapshots"][existing]["items"])} รายการ) — เขียนทับ')
        db['snapshots'][existing] = snapshot
    else:
        db['snapshots'].append(snapshot)
    db['snapshots'].sort(key=lambda s: s['date_iso'])
    return db


# ──────────────────────────────────────────────
# HTML REGENERATION
# ──────────────────────────────────────────────

def regenerate_html(db):
    """อ่าน viewer.html ปัจจุบัน แทนที่ข้อมูล JSON แล้วบันทึกใหม่"""
    with open(VIEWER_OUT, 'r', encoding='utf-8') as f:
        html = f.read()

    # Replace the embedded DB constant
    new_json = json.dumps(db, ensure_ascii=False)
    # Pattern: const SEED_DB = {...};
    html = re.sub(
        r'(const SEED_DB\s*=\s*)(\{.*?\});',
        rf'\g<1>{new_json};',
        html,
        flags=re.DOTALL
    )
    with open(VIEWER_OUT, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'  ✅ อัปเดต viewer.html แล้ว ({sum(len(s["items"]) for s in db["snapshots"])} รายการรวม {len(db["snapshots"])} รอบ)')


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def cmd_list(db):
    print(f'\n📋 ข้อมูลในฐาน ({len(db["snapshots"])} รอบ):')
    for s in db['snapshots']:
        print(f'  {s["date"]}  {s["source"]}  — {len(s["items"])} รายการ')
    print()


def cmd_parse_file(path, db):
    if not os.path.exists(path):
        print(f'ไม่พบไฟล์: {path}'); return

    with open(path, 'r', encoding='utf-8') as f:
        text = f.read().strip()

    # ── ตรวจสอบว่าเป็น JSON format ──────────────────────────────────
    if text.startswith('{') or text.startswith('['):
        try:
            data = json.loads(text)
            # รองรับ format: snapshot object เดี่ยว หรือ array ของ items
            if isinstance(data, dict) and 'items' in data:
                # JSON snapshot format: { "date": "...", "items": [...] }
                date_iso = data.get('date_iso', datetime.today().strftime('%Y-%m-%d'))
                items = data.get('items', [])
                source = data.get('source', 'ร้าน A')
            elif isinstance(data, list):
                # Array of items
                items = data
                date_iso = datetime.today().strftime('%Y-%m-%d')
                source = 'ร้าน A'
            else:
                print('❌ รูปแบบ JSON ไม่ถูกต้อง'); return

            print(f'\n📦 JSON format: {len(items)} รายการ  วันที่ {date_iso}')
            for brand in dict.fromkeys(r.get('brand','') for r in items):
                count = sum(1 for r in items if r.get('brand') == brand)
                print(f'   {brand}: {count} รายการ')

            ans = input('\nบันทึกลงฐานข้อมูล? [y/n] ').strip().lower()
            if ans == 'y':
                db = add_snapshot(db, date_iso, items, source)
                save_db(db)
                regenerate_html(db)
                print(f'\n✅ บันทึกสำเร็จ! เปิด viewer.html ในเบราเซอร์เพื่อดูราคา')
            return
        except json.JSONDecodeError as e:
            print(f'⚠️ JSON parse error: {e} — ลองอ่านเป็น text format แทน')

    # ── Text format (ข้อความจากร้าน) ────────────────────────────────
    result = parse_text(text)
    date_iso = result['date_iso']
    items = result['items']

    print(f'\n📦 วิเคราะห์เสร็จ: {len(items)} รายการ  วันที่ {date_iso}')

    # Preview
    for brand in dict.fromkeys(r['brand'] for r in items):
        count = sum(1 for r in items if r['brand'] == brand)
        print(f'   {brand}: {count} รายการ')

    ans = input('\nบันทึกลงฐานข้อมูล? [y/n] ').strip().lower()
    if ans == 'y':
        db = add_snapshot(db, date_iso, items)
        save_db(db)
        regenerate_html(db)
        print(f'\n✅ บันทึกสำเร็จ! เปิด viewer.html ในเบราเซอร์เพื่อดูราคา')


def cmd_paste(db):
    print('วางข้อความที่ร้านส่งมา (กด Ctrl+D หรือ Ctrl+Z เมื่อเสร็จ):')
    try:
        text = sys.stdin.read()
    except KeyboardInterrupt:
        return

    result = parse_text(text)
    date_iso = result['date_iso']
    items = result['items']

    print(f'\n📦 วิเคราะห์เสร็จ: {len(items)} รายการ  วันที่ {date_iso}')
    for brand in dict.fromkeys(r['brand'] for r in items):
        count = sum(1 for r in items if r['brand'] == brand)
        print(f'   {brand}: {count} รายการ')

    ans = input('\nบันทึกลงฐานข้อมูล? [y/n] ').strip().lower()
    if ans == 'y':
        db = add_snapshot(db, date_iso, items)
        save_db(db)
        regenerate_html(db)
        print(f'\n✅ บันทึกสำเร็จ! เปิด viewer.html ในเบราเซอร์เพื่อดูราคา')


def main():
    db = load_db()

    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        return

    if sys.argv[1] == '--list':
        cmd_list(db)
    elif sys.argv[1] == '--paste':
        cmd_paste(db)
    elif sys.argv[1] == '--rebuild':
        regenerate_html(db)
    else:
        cmd_parse_file(sys.argv[1], db)


if __name__ == '__main__':
    main()
