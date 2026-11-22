#!/usr/bin/env python3
"""Tito Goes to NY multi-source refresh helper (headless Chrome via Playwright).

Usage:
  python3 tools/refresh_sources.py recheck  [--out DIR]   # open every board URL, report live/price/flex
  python3 tools/refresh_sources.py search   [--out DIR]   # sweep all working sources, write candidates.json
  python3 tools/refresh_sources.py all      [--out DIR]

Needs: pip install playwright pillow && python3 -m playwright install chromium
(uses channel='chrome' when /usr/bin/google-chrome exists, which gets past more bot checks).
Output goes to --out (default /workspace/tito-refresh-YYYY-MM-DD). It never edits the board:
review candidates.json, open each detail page it saved, then add keepers to data/listings.json
+ listings.js by hand or with a small apply script. See tools/SOURCES.md for what works.
"""
import asyncio, re, json, os, sys, html as H, datetime, shutil
from playwright.async_api import async_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
CAP2, CAP3 = 5000, 7500
COVER = {'east village', 'alphabet city', 'west village', 'greenwich village', 'soho', 'noho',
         'hudson square', 'meatpacking', 'meatpacking district', 'chelsea', 'west chelsea'}
BAD_WORDS = re.compile(r'\bflex\b|flex[- ]?\d|convertible|converts? to|junior \d|net effective|stuyvesant town|stuy ?town', re.I)

def under_cap(beds, price):
    try: beds, price = int(beds), int(price)
    except Exception: return False
    return (beds == 2 and 0 < price <= CAP2) or (beds == 3 and 0 < price <= CAP3)

async def browser(p):
    kw = dict(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
    if shutil.which('google-chrome'): kw['channel'] = 'chrome'
    return await p.chromium.launch(**kw)

async def fetch(br, url, wait=6000, scroll=False):
    ctx = await br.new_context(user_agent=UA, locale='en-US', viewport={'width': 1366, 'height': 900})
    pg = await ctx.new_page(); st = None
    try:
        r = await pg.goto(url, timeout=45000, wait_until='domcontentloaded'); st = r.status if r else None
        await pg.wait_for_timeout(wait)
        if scroll:
            for _ in range(6): await pg.mouse.wheel(0, 3000); await pg.wait_for_timeout(500)
        h = await pg.content(); t = await pg.inner_text('body')
    except Exception as e:
        h, t = '', 'ERR ' + str(e)[:200]
    await ctx.close()
    return st, h, t

# ---------------- source parsers ----------------
def renthop_cards(h):
    out = []
    for m in re.finditer(r'id="listing-(\d+)" listing_id="\d+"', h):
        lid = m.group(1); seg = h[m.start():m.start() + 9000]
        g = lambda p: (re.search(p, seg, re.S) or [None, None])[1]
        out.append(dict(source='RentHop', id=lid, url=g(r'href="(https://www.renthop.com/listings/[^"]+)"'),
            addr=H.unescape((g(r'id="listing-%s-title"[^>]*>(.*?)</a>' % lid) or '').strip()),
            hood=(g(r'id="listing-%s-neighborhoods"[^>]*>(.*?)</div>' % lid) or '').strip(),
            price=int(re.sub(r'\D', '', g(r'id="listing-%s-price"[^>]*>(.*?)</div>' % lid) or '0') or 0),
            agent=(g(r'By <a [^>]*>(.*?)</a>') or '').strip(), beds=g(r'(\d+) Bed'), baths=g(r'([\d.]+) Bath')))
    return out

def renthop_detail(t, h):
    d = {}
    m = re.search(r'(\d) Bed\s+([\d.]+) Bath(?:\s+([\d,]+) Sqft)?', t)
    if m: d['beds'], d['baths'], d['sqft'] = m.groups()
    a = t.find('DESCRIPTION'); b = t.find('AMENITIES', a); d['desc'] = re.sub(r'\s+', ' ', t[a + 11:b])[:2000]
    j = t.find('Report this listing here.')
    if j > 0:
        tail = [x.strip() for x in t[j:].split('\n') if x.strip()][1:4]
        d['agent'] = tail[0]; d['company'] = tail[1] if tail[1] not in ('RentHop Pro', 'Check Availability') else ''
    d['photos'] = sorted(set(re.findall(r'https://photos\.renthop\.com/p/s/1024x1024/[^"\s]+?\.webp', h)))[:6]
    return d

def compass_cards(h):
    dec = lambda s: json.loads('"' + s + '"')
    out = []
    for m in re.finditer(r'"listingIdSHA":"(\d+)","title":"([^"]*)","subtitles":\[(.*?)\]', h):
        seg = h[m.end():m.end() + 8000]
        subs = [dec(x) for x in re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(3))]
        beds = re.search(r'"title":"beds?","subtitle":"([^"]*)"', seg)
        court = re.search(r'Listing Courtesy of ([^"]+)"', seg); link = re.search(r'"navigationPageLink":"([^"]+)"', seg)
        out.append(dict(source='Compass', id=m.group(1), price=int(re.sub(r'\D', '', m.group(2)) or 0), addr=subs[0] if subs else '',
                        hood=subs[1] if len(subs) > 1 else '', beds=beds and beds.group(1), agent=court and court.group(1),
                        url='https://www.compass.com' + dec(link.group(1)) if link else None))
    return out

def realtor_cards(t, h):
    out = []
    for b in t.split('Property detail for ')[1:]:
        L = [x.strip() for x in b.split('\n') if x.strip()]
        pr = next((x for x in L[:6] if x.startswith('$')), '')
        bd = next((x for x in L[:10] if re.match(r'^(\d)bed$', x)), '')
        out.append(dict(source='Realtor.com', addr=L[0], price=int((re.findall(r'[\d,]+', pr) or ['0'])[0].replace(',', '')), beds=bd[:1]))
    links = sorted(set('https://www.realtor.com' + x for x in re.findall(r'href="(/rentals/details/[^"]+)"', h)))
    return out, links

def realtor_detail(h):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
    if not m: return None
    j = json.loads(m.group(1)); pd = (j.get('props', {}).get('pageProps', {}).get('initialReduxState', {}) or {}).get('propertyDetails')
    if not pd: return None
    d = pd.get('description') or {}; src = pd.get('source') or {}
    adv = [a.get('name') for a in (pd.get('consumer_advertisers') or []) if a.get('name')]
    return dict(status=pd.get('status'), price=pd.get('list_price'), beds=d.get('beds'), baths=d.get('baths_consolidated'), sqft=d.get('sqft'),
                text=d.get('text'), list_date=pd.get('list_date'), updated=pd.get('last_update_date'), feed=src.get('name'), advertisers=adv,
                photos=[re.sub(r's\.jpg$', 'od-w1024_h768.jpg', p.get('href', '')) for p in (pd.get('photos') or [])][:6])

def corcoran_rows(cards):
    rows = []
    for href, t in cards:
        m = re.search(r'/listing/for-rent/([^/]+)/(\d+)/', href)
        if not m: continue
        bd = re.search(r'(\d) BD', t); pr = re.search(r'\$([\d,]+)', t)
        addr = next((x for x in t.split('\n') if 'Manhattan, NY' in x), m.group(1))
        rows.append(dict(source='Corcoran', id=m.group(2), url=href, beds=bd and bd.group(1), addr=addr,
                         price=int(pr.group(1).replace(',', '')) if pr else 0, signed='LEASE SIGNED' in t))
    return rows

def nest_cards(h):
    out = []
    for m in re.finditer(r'<a href="(https://www\.nestseekers\.com/(\d+)/[^"]+)"[^>]*aria-label="View details for ([^"]*)"', h):
        seg = h[m.end():m.end() + 5000]
        info = re.search(r'text-white/85 mt-1 text-sm leading-tight">(.*?)</div></div>', seg, re.S)
        parts = re.findall(r'<div>(.*?)</div>', info.group(1)) if info else []
        pr = re.search(r'font-semibold leading-tight">\$([\d,]+)', seg); bd = re.search(r'<div>(\d+) bed</div>', seg)
        out.append(dict(source='Nest Seekers', id=m.group(2), url=m.group(1), addr=H.unescape(parts[0]) if parts else '',
                        hood=parts[1] if len(parts) > 1 else '', price=int(pr.group(1).replace(',', '')) if pr else 0, beds=bd and bd.group(1)))
    return out

# ---------------- search ----------------
async def search(out):
    cands = []; log = {}
    async with async_playwright() as p:
        br = await browser(p)
        # RentHop (works; filter params honored)
        for hd in ['east-village', 'west-village', 'greenwich-village', 'soho', 'noho', 'chelsea', 'hudson-square']:
            seen = set()
            for page in range(1, 12):
                st, h, t = await fetch(br, f'https://www.renthop.com/apartments-for-rent/{hd}-new-york-ny?max_price={CAP3}&bedrooms%5B%5D=2&bedrooms%5B%5D=3&sort=price&page={page}', 2500)
                items = [i for i in renthop_cards(h) if i['id'] not in seen]
                seen |= {i['id'] for i in items}; cands += items
                if not items: break
            log[f'renthop-{hd}'] = len(seen)
        # Compass (cards include other brokerages via 'Listing Courtesy of'); detail pages need login
        for hd in ['east-village', 'west-village', 'greenwich-village', 'soho', 'noho', 'chelsea', 'hudson-square']:
            for b, cap in [(2, CAP2), (3, CAP3)]:
                st, h, t = await fetch(br, f'https://www.compass.com/for-rent/{hd}-manhattan-ny/price.max={cap}/beds.min={b}/beds.max={b}/', 4000)
                items = compass_cards(h); cands += items; log[f'compass-{hd}-{b}'] = len(items)
        # Corcoran (server-rendered, ?page=N)
        slugs = 'east-village-ny,west-village-ny,greenwich-village-ny,soho-nolita-ny,noho-ny,chelsea-ny,hudson-square-ny,meatpacking-district-ny'
        ctx = await br.new_context(user_agent=UA); pg = await ctx.new_page(); seen = {}
        for page in range(1, 30):
            await pg.goto(f'https://www.corcoran.com/search/for-rent/location/{slugs}/regionId/1' + (f'?page={page}' if page > 1 else ''), wait_until='domcontentloaded', timeout=45000)
            await pg.wait_for_timeout(5000)
            cards = await pg.eval_on_selector_all('a[href*="/listing/for-rent/"]', 'els=>els.map(e=>{let c=e.closest("li")||e.closest("article")||e.parentElement.parentElement;return [e.href,c?c.innerText:""]})')
            n0 = len(seen)
            for hr, tx in cards:
                if len(tx) > len(seen.get(hr, '')): seen[hr] = tx
            if len(seen) == n0: break
        await ctx.close()
        rows = corcoran_rows(seen.items()); cands += rows; log['corcoran'] = len(rows)
        # Realtor.com by zip (JSON detail has feed, advertisers, list date)
        rl_links = []
        for z in ['10003', '10009', '10011', '10012', '10013', '10014']:
            for page in range(1, 6):
                st, h, t = await fetch(br, f'https://www.realtor.com/apartments/{z}/beds-2-3/price-na-{CAP3}' + (f'/pg-{page}' if page > 1 else ''), 4000, scroll=True)
                items, links = realtor_cards(t, h); cands += items; rl_links += links
                if not items: break
            log[f'realtor-{z}'] = 'ok'
        # Nest Seekers (works, but many stale cards without dates; verify elsewhere)
        for s in ['East-Village', 'west-village', 'greenwich-village', 'soho', 'Chelsea']:
            seen = set()
            for page in range(1, 25):
                st, h, t = await fetch(br, f'https://www.nestseekers.com/Rentals/{s}/' + (f'?page={page}' if page > 1 else ''), 2500)
                items = [i for i in nest_cards(h) if i['id'] not in seen]; seen |= {i['id'] for i in items}; cands += items
                if not items: break
            log[f'nest-{s}'] = len(seen)
        # Craigslist (rendered list view; only use posts with an address or a second source)
        ctx = await br.new_context(user_agent=UA); pg = await ctx.new_page()
        for q in ['east village', 'west village', 'greenwich village', 'chelsea', 'soho', 'noho']:
            await pg.goto(f'https://newyork.craigslist.org/search/mnh/apa?max_price={CAP3}&min_bedrooms=2&max_bedrooms=3&broker_fee=1&query=' + q.replace(' ', '+'), wait_until='domcontentloaded')
            await pg.wait_for_timeout(5000)
            for _ in range(8): await pg.mouse.wheel(0, 4000); await pg.wait_for_timeout(400)
            rows = await pg.eval_on_selector_all('a.posting-title', 'els=>els.map(e=>[e.href,(e.closest(".cl-search-result")||e.parentElement.parentElement).innerText])')
            for hr, tx in rows:
                tx = ' '.join(tx.split()); pr = re.search(r'\$([\d,]+)', tx); bd = re.search(r'(\d)br', tx)
                cands.append(dict(source='Craigslist', url=hr, addr=tx[:120], price=int(pr.group(1).replace(',', '')) if pr else 0, beds=bd and bd.group(1)))
            log[f'craigslist-{q}'] = len(rows)
        await ctx.close()
        await br.close()
    keep = [c for c in cands if under_cap(c.get('beds'), c.get('price'))]
    board = json.load(open(f'{REPO}/data/listings.json'))['listings']
    baddr = {re.sub(r'\W', '', l['address'].lower())[:18] for l in board}
    for c in keep: c['maybe_on_board'] = re.sub(r'\W', '', (c.get('addr') or '').lower())[:18] in baddr
    json.dump(dict(log=log, candidates=keep, realtor_links=sorted(set(rl_links))), open(f'{out}/candidates.json', 'w'), indent=1)
    print(json.dumps(log, indent=1)); print('candidates under cap:', len(keep))

# ---------------- recheck ----------------
async def recheck(out):
    board = json.load(open(f'{REPO}/data/listings.json'))['listings']; res = []
    async with async_playwright() as p:
        br = await browser(p); sem = asyncio.Semaphore(4)
        async def one(l):
            async with sem:
                st, h, t = await fetch(br, l['url'], 7000)
                open(f"{out}/recheck-{l['id']}.txt", 'w').write(t)
                r = dict(id=l['id'], board_rent=l['rent'], http=st, live=None, rent=None, flex=bool(BAD_WORDS.search(t[:6000])))
                u = l['url']
                if 'zumper.com' in u:
                    m = re.search(r'MONTHLY RENT\s*\n\s*(\S+)', t, re.I)
                    r['rent'] = m.group(1) if m else None; r['live'] = bool(m and m.group(1).startswith('$'))
                    if 'Show occupied' in t and not (m and m.group(1).startswith('$') and '#' in t[:600]):
                        unit = (l['address'].split('#') + [''])[1].split(',')[0].strip()
                        mm = re.search(r'AVAILABLE\s*\n\s*%s\s*\n(.{0,120}?)\$([\d,]+)' % re.escape(unit), t, re.S | re.I)
                        r['live'] = bool(mm); r['rent'] = mm and mm.group(2)
                elif 'renthop.com' in u:
                    pr = re.search(r'\n\$([\d,]+)\s*\n', t); r['rent'] = pr and pr.group(1)
                    r['live'] = bool(pr) and not re.search(r'no longer available|listing (is )?(inactive|off)', t, re.I)
                elif 'realtor.com' in u:
                    d = realtor_detail(h) or {}; r['rent'] = d.get('price'); r['live'] = d.get('status') == 'for_rent'
                elif 'corcoran.com' in u:
                    pr = re.search(r'\$([\d,]+) USD', t); r['rent'] = pr and pr.group(1); r['live'] = bool(pr) and 'LEASE SIGNED' not in t[:3000]
                else:
                    r['live'] = st == 200
                res.append(r)
        await asyncio.gather(*[one(l) for l in board]); await br.close()
    json.dump(res, open(f'{out}/recheck.json', 'w'), indent=1)
    for r in sorted(res, key=lambda r: r['id']):
        flag = '' if r['live'] and not r['flex'] else '  <-- CHECK'
        print(f"{r['id']:32} live={r['live']} rent={r['rent']} board={r['board_rent']} flex={r['flex']}{flag}")

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    out = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else f"/workspace/tito-refresh-{datetime.date.today()}"
    os.makedirs(out, exist_ok=True)
    if mode in ('recheck', 'all'): asyncio.run(recheck(out))
    if mode in ('search', 'all'): asyncio.run(search(out))
