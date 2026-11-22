# Tito Goes to NY: listing sources (tested 22 Nov 2026)

Run `python3 tools/refresh_sources.py all --out /workspace/tito-refresh-YYYY-MM-DD`
(recheck every board URL, then sweep all working sources into `candidates.json`).
It uses Playwright with the system Chrome (`channel='chrome'`); install with
`pip install playwright pillow && python3 -m playwright install chromium` if missing.
It never edits the board. Open each candidate's detail page before adding it.

## Works (headless Chrome)
| Source | How | Notes |
|---|---|---|
| Zumper | unit or building pages | Board's original source. Off-market units show `MONTHLY RENT -` plus "Notify me". Building pages list units as AVAILABLE/Occupied. |
| RentHop | `/apartments-for-rent/<hood>-new-york-ny?max_price=7500&bedrooms[]=2&bedrooms[]=3&sort=price&page=N` | Best multi-agency source. Detail page shows agent + brokerage under "Report this listing here." (FIND, Alta, City Connections, Oxford, Keller Williams, Metropolitan Property Group, Voro, EXP...). Watch "net effective" (Voro) and "flexible". In practice only East Village had under-cap 2/3BRs. |
| Corcoran | `/search/for-rent/location/east-village-ny,west-village-ny,.../regionId/1?page=N` | Server-rendered, full address + unit. Skip cards marked LEASE SIGNED. Photo from og:image. |
| Compass | `/for-rent/<hood>-manhattan-ny/price.max=X/beds.min=N/beds.max=N/` | Cards embed JSON incl. "Listing Courtesy of" (Elliman, Corcoran, etc.). Detail pages need login (REBNY rule), so verify on the agency site. Undisclosed-address cards were 590+ days stale. |
| Realtor.com | `/apartments/<zip>/beds-2-3/price-na-7500[/pg-N]` | Detail page `__NEXT_DATA__` has status, list date, feed (Zumper/Avail/OLR/RealtyMX) and advertiser (brokerage). Many generic-copy feed units are 2023-2025 stale; check list_date. |
| Nest Seekers | `/Rentals/East-Village/?page=N` (also west-village, greenwich-village, soho, Chelsea) | Loads, but under-cap cards had move-in dates from past months and no posted date. Only use with a second source. |
| Craigslist | `/search/mnh/apa?max_price=7500&min_bedrooms=2&max_bedrooms=3&broker_fee=1&query=...` | Rendered list uses `a.posting-title`. Most posts hide the address; useful to cross-confirm. Many are Stuy Town or flex. |
| Douglas Elliman | `/rentals/<hood>-new-york-ny` | Loads, small inventory, nothing under cap on 22 Nov. |
| Brown Harris Stevens | `/neighborhood/<hood>` (`/for-rent/` search ignores filters) | Loads; nothing under cap on 22 Nov. |
| Keller Williams NYC | `kwnyc.com/rentals` | Loads but only a featured carousel; their agents' listings show up on RentHop. |

## Blocked or unusable
- StreetEasy, Zillow, Trulia, HotPads: 403 "Access to this page has been denied" (PerimeterX).
- Apartments.com: Access Denied (Akamai).
- Pinnacle, A&E: Cloudflare "Just a moment".
- Bond New York: HTTP response failure. Warburg and Halstead: certificate error. Triplemint, Croman, Ved Parkash, Spire Realty Group: connection closed.
- Serhant, Living NY, Stonehenge, Glenwood, Rose, Related, Gotham: load, but no usable downtown rental search or all over cap. Serhant and Living NY listings appear on Elliman/BHS/Compass cards.

## Rules recap
2BR <= $5,000, 3BR <= $7,500. West Village, Greenwich Village, East Village (incl. Alphabet City), SoHo, NoHo, Hudson Square, Meatpacking, Chelsea. Reject flex/convertible/junior, Stuy Town, LES, Bowery, Nolita, Little Italy, Two Bridges, Gramercy, Hudson Yards/Garment, net-effective prices, stale feeds.
