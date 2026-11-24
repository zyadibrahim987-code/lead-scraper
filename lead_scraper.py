#!/usr/bin/env python3
"""
Lead Scraper — جمع بيانات الشركات والمتاجر الإلكترونية
الاسم - الرقم - العنوان - الموقع - السوشيال ميديا - الإيميل - منصة المتجر

المصادر:
  1) Google Maps  ← عبر Google Places API الرسمي (GOOGLE_PLACES_API_KEY)
  2) بحث جوجل     ← عبر Serper.dev (SERPER_API_KEY) لاكتشاف مواقع المتاجر
                     وصفحات انستجرام/فيسبوك/تيك توك/لينكدإن من نتائج البحث
  3) ملف روابط     ← قائمة مواقع عندك (urls.txt) يتم إثراؤها

الإثراء (Enrichment): بيزور موقع كل نشاط (الرئيسية + صفحات التواصل/من نحن)
ويستخرج: إيميلات، أرقام، واتساب، روابط السوشيال، ومنصة المتجر (Shopify, Salla, Zid ...).

أمثلة:
  python lead_scraper.py --query "متجر ملابس" --location "القاهرة" --sources maps,search
  python lead_scraper.py --urls urls.txt
  python lead_scraper.py --query "online store" --location "Dubai" --max 60 --out dubai.xlsx
"""
import argparse
import csv
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
TIMEOUT = 15

FIELDS = ["name", "phone", "whatsapp", "email", "address", "website", "platform",
          "facebook", "instagram", "tiktok", "linkedin", "twitter", "youtube", "snapchat",
          "rating", "reviews", "category", "maps_url", "source"]

SOCIAL_PATTERNS = {
    "facebook": r"(?:facebook|fb)\.com/(?!sharer|share|plugins|dialog|tr\b|login|privacy)[A-Za-z0-9_.\-/%]+",
    "instagram": r"instagram\.com/(?!p/|reel/|explore|accounts|share)[A-Za-z0-9_.]+",
    "tiktok": r"tiktok\.com/@[A-Za-z0-9_.]+",
    "linkedin": r"linkedin\.com/(?:company|in|school)/[A-Za-z0-9_\-%]+",
    "twitter": r"(?:twitter|x)\.com/(?!share|intent|home|search)[A-Za-z0-9_]{2,}",
    "youtube": r"youtube\.com/(?:@|channel/|c/|user/)[A-Za-z0-9_\-]+",
    "snapchat": r"snapchat\.com/add/[A-Za-z0-9_.\-]+",
}
WHATSAPP_RE = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp\.com/send\?phone=)\+?(\d{8,15})")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+|00)?\d[\d\s\-().]{7,17}\d")
BAD_EMAIL_ENDINGS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")
BAD_EMAIL_PARTS = ("example.", "sentry", "wixpress", "domain.com", "email.com", "yourname")

PLATFORMS = {
    "Shopify": ["cdn.shopify.com", "Shopify.theme"],
    "Salla": ["salla.sa", "cdn.salla.network"],
    "Zid": ["zid.store", "zid.sa"],
    "WooCommerce": ["woocommerce", "wc-ajax"],
    "YouCan": ["youcan.shop"],
    "ExpandCart": ["expandcart"],
    "Wix": ["wixstatic.com", "wix.com"],
    "Magento": ["Magento", "mage/"],
    "OpenCart": ["route=product", "catalog/view/theme"],
    "BigCommerce": ["bigcommerce"],
    "Squarespace": ["squarespace"],
}
CONTACT_HINTS = ("contact", "about", "تواصل", "اتصل", "من-نحن", "about-us", "contact-us")

# مواقع لا تعتبر "موقع النشاط" نفسه
NON_BUSINESS_DOMAINS = ("facebook.com", "instagram.com", "tiktok.com", "linkedin.com", "twitter.com",
                        "x.com", "youtube.com", "google.", "wikipedia.org", "amazon.", "noon.com",
                        "jumia.", "yellowpages", "tripadvisor", "pinterest.")

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "ar,en;q=0.8"})


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- Google Maps
def source_google_maps(query, location, max_results):
    key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not key:
        log("[maps] تخطي: GOOGLE_PLACES_API_KEY غير موجود")
        return []
    url = "https://places.googleapis.com/v1/places:searchText"
    mask = ("places.displayName,places.formattedAddress,places.nationalPhoneNumber,"
            "places.internationalPhoneNumber,places.websiteUri,places.rating,"
            "places.userRatingCount,places.primaryTypeDisplayName,places.googleMapsUri,nextPageToken")
    headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": mask}
    body = {"textQuery": f"{query} {location}".strip(), "pageSize": 20}
    out, token = [], None
    while len(out) < max_results:
        if token:
            body["pageToken"] = token
        r = requests.post(url, json=body, headers=headers, timeout=TIMEOUT)
        if r.status_code != 200:
            log(f"[maps] خطأ {r.status_code}: {r.text[:300]}")
            break
        data = r.json()
        for p in data.get("places", []):
            out.append({
                "name": p.get("displayName", {}).get("text", ""),
                "phone": p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber", ""),
                "address": p.get("formattedAddress", ""),
                "website": p.get("websiteUri", ""),
                "rating": p.get("rating", ""),
                "reviews": p.get("userRatingCount", ""),
                "category": p.get("primaryTypeDisplayName", {}).get("text", ""),
                "maps_url": p.get("googleMapsUri", ""),
                "source": "google_maps",
            })
        token = data.get("nextPageToken")
        if not token:
            break
        time.sleep(2)
    log(f"[maps] {len(out)} نتيجة")
    return out[:max_results]


# --------------------------------------------------------------- Google search
def serper(q, num=20):
    key = os.getenv("SERPER_API_KEY")
    r = requests.post("https://google.serper.dev/search",
                      json={"q": q, "num": num},
                      headers={"X-API-KEY": key, "Content-Type": "application/json"},
                      timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("organic", [])


def source_search(query, location, max_results):
    if not os.getenv("SERPER_API_KEY"):
        log("[search] تخطي: SERPER_API_KEY غير موجود")
        return []
    q = f"{query} {location}".strip()
    queries = [
        (f"{q} متجر الكتروني", "web"),
        (f"{q} online store", "web"),
        (f"site:instagram.com {q}", "instagram"),
        (f"site:facebook.com {q}", "facebook"),
        (f"site:tiktok.com {q}", "tiktok"),
        (f"site:linkedin.com/company {q}", "linkedin"),
    ]
    out, seen = [], set()
    for sq, kind in queries:
        try:
            results = serper(sq)
        except Exception as e:
            log(f"[search] فشل '{sq}': {e}")
            continue
        for it in results:
            link, title = it.get("link", ""), it.get("title", "")
            snippet = it.get("snippet", "")
            name = re.split(r"\s[|\-–•(]\s?|\(@", title)[0].strip()
            rec = {"name": name, "source": f"search:{kind}"}
            if kind == "web":
                dom = urlparse(link).netloc.lower()
                if any(d in dom for d in NON_BUSINESS_DOMAINS):
                    continue
                rec["website"] = f"{urlparse(link).scheme}://{urlparse(link).netloc}"
            else:
                rec[kind] = link.split("?")[0]
            # أرقام/إيميلات ظاهرة في وصف النتيجة (شائع في البايو)
            rec["email"] = ", ".join(clean_emails(EMAIL_RE.findall(snippet)))
            rec["phone"] = ", ".join(clean_phones(PHONE_RE.findall(snippet)))
            k = rec.get("website") or rec.get(kind)
            if k and k not in seen:
                seen.add(k)
                out.append(rec)
        if len(out) >= max_results:
            break
    log(f"[search] {len(out)} نتيجة")
    return out[:max_results]


def source_urls(path):
    with open(path, encoding="utf-8") as f:
        urls = [u.strip() for u in f if u.strip() and not u.startswith("#")]
    return [{"name": "", "website": u if u.startswith("http") else "https://" + u, "source": "urls_file"}
            for u in urls]


# ----------------------------------------------------------------- Enrichment
def clean_emails(emails):
    res = []
    for e in emails:
        e = e.strip(".").lower()
        if e.endswith(BAD_EMAIL_ENDINGS) or any(b in e for b in BAD_EMAIL_PARTS):
            continue
        if e not in res:
            res.append(e)
    return res


def clean_phones(phones):
    res = []
    for p in phones:
        digits = re.sub(r"\D", "", p)
        if 9 <= len(digits) <= 15 and not re.fullmatch(r"(19|20)\d{2}(19|20)\d{2}.*", digits):
            p = re.sub(r"\s+", " ", p.strip())
            if digits not in [re.sub(r"\D", "", x) for x in res]:
                res.append(p)
    return res


def fetch(url):
    try:
        r = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get("Content-Type", ""):
            return r.text, r.url
    except requests.RequestException:
        pass
    return None, url


def extract_page(html, base):
    soup = BeautifulSoup(html, "html.parser")
    hrefs = [a.get("href", "") for a in soup.find_all("a", href=True)]
    blob = html + " " + " ".join(hrefs)
    data = {"emails": [], "phones": [], "whatsapp": [], "social": {}, "links": []}

    data["emails"] += [h[7:].split("?")[0] for h in hrefs if h.lower().startswith("mailto:")]
    data["emails"] += EMAIL_RE.findall(soup.get_text(" "))
    data["phones"] += [h[4:] for h in hrefs if h.lower().startswith("tel:")]
    # أرقام من النص الظاهر فقط لو مفيش tel:
    if not data["phones"]:
        footer = soup.find("footer")
        txt = (footer.get_text(" ") if footer else "")
        data["phones"] += PHONE_RE.findall(txt)
    data["whatsapp"] += WHATSAPP_RE.findall(blob)

    for net, pat in SOCIAL_PATTERNS.items():
        m = re.findall(r"https?://(?:www\.|m\.|[a-z]{2}-[a-z]{2}\.)?" + pat, blob, re.I)
        if m:
            data["social"][net] = m[0].rstrip("/").rstrip("\\")

    for h in hrefs:
        full = urljoin(base, h)
        if urlparse(full).netloc == urlparse(base).netloc and any(k in full.lower() for k in CONTACT_HINTS):
            data["links"].append(full.split("#")[0])

    title = soup.title.get_text(strip=True) if soup.title else ""
    og = soup.find("meta", property="og:site_name")
    data["name"] = (og.get("content") if og else "") or re.split(r"\s[|\-–]\s", title)[0]
    data["platform"] = next((p for p, sigs in PLATFORMS.items() if any(s in html for s in sigs)), "")

    for s in soup.find_all("script", type="application/ld+json"):
        t = s.string or ""
        m = re.search(r'"streetAddress"\s*:\s*"([^"]+)"', t)
        if m:
            data["address"] = m.group(1)
        m = re.search(r'"telephone"\s*:\s*"([^"]+)"', t)
        if m:
            data["phones"].insert(0, m.group(1))
    return data


def enrich(rec):
    site = rec.get("website")
    if not site:
        return rec
    html, final = fetch(site)
    if not html:
        rec["website_status"] = "unreachable"
        return rec
    agg = extract_page(html, final)
    for link in list(dict.fromkeys(agg["links"]))[:3]:
        h, u = fetch(link)
        if h:
            d = extract_page(h, u)
            agg["emails"] += d["emails"]
            agg["phones"] += d["phones"]
            agg["whatsapp"] += d["whatsapp"]
            agg.setdefault("address", d.get("address"))
            for k, v in d["social"].items():
                agg["social"].setdefault(k, v)

    rec["name"] = rec.get("name") or agg.get("name", "")
    rec["platform"] = rec.get("platform") or agg["platform"]
    rec["address"] = rec.get("address") or agg.get("address") or ""
    rec["email"] = ", ".join(dict.fromkeys(filter(None, (rec.get("email", "").split(", ") + clean_emails(agg["emails"])))))
    phones = [p for p in rec.get("phone", "").split(", ") if p] + clean_phones(agg["phones"])
    rec["phone"] = ", ".join(clean_phones(phones)[:3])
    rec["whatsapp"] = ", ".join(dict.fromkeys(agg["whatsapp"]))
    for net, link in agg["social"].items():
        rec[net] = rec.get(net) or link
    return rec


# --------------------------------------------------------------------- Output
def dedupe(records):
    out, keys = [], {}
    for r in records:
        dom = urlparse(r.get("website", "")).netloc.replace("www.", "")
        phone = re.sub(r"\D", "", (r.get("phone") or "").split(",")[0])[-9:]
        k = dom or phone or (r.get("name", "").lower() + r.get("instagram", "") + r.get("facebook", ""))
        if k in keys:  # دمج الحقول الفاضية
            base = keys[k]
            for f in FIELDS:
                if not base.get(f) and r.get(f):
                    base[f] = r[f]
            continue
        keys[k] = r
        out.append(r)
    return out


def save(records, path):
    if path.endswith(".xlsx"):
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Leads"
        ws.append(FIELDS)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F4E78")
        for r in records:
            ws.append([str(r.get(f, "") or "") for f in FIELDS])
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(
                45, max(12, max(len(str(c.value or "")) for c in col) + 2))
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        wb.save(path)
    else:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig عشان العربي في Excel
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(records)


def main():
    ap = argparse.ArgumentParser(description="جمع بيانات الشركات والمتاجر الإلكترونية")
    ap.add_argument("--query", "-q", default="", help='نوع النشاط، مثال: "متجر ملابس"')
    ap.add_argument("--location", "-l", default="", help='المدينة/الدولة، مثال: "القاهرة"')
    ap.add_argument("--sources", default="maps,search", help="maps,search (افتراضي الاتنين)")
    ap.add_argument("--urls", help="ملف فيه لينكات مواقع (سطر لكل لينك)")
    ap.add_argument("--max", type=int, default=40, help="أقصى عدد نتائج لكل مصدر")
    ap.add_argument("--no-enrich", action="store_true", help="بدون زيارة المواقع")
    ap.add_argument("--only-with-phone", action="store_true", help="احتفظ فقط بالي ليهم رقم")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", "-o", default="leads.xlsx", help="leads.xlsx أو leads.csv")
    a = ap.parse_args()

    records = []
    srcs = [s.strip() for s in a.sources.split(",")]
    if a.query:
        if "maps" in srcs:
            records += source_google_maps(a.query, a.location, a.max)
        if "search" in srcs:
            records += source_search(a.query, a.location, a.max)
    if a.urls:
        records += source_urls(a.urls)
    if not records:
        sys.exit("مفيش نتائج — اتأكد من --query أو --urls ومن مفاتيح الـ API")

    records = dedupe(records)
    if not a.no_enrich:
        log(f"[enrich] زيارة {sum(1 for r in records if r.get('website'))} موقع ...")
        with ThreadPoolExecutor(a.workers) as ex:
            records = list(ex.map(enrich, records))
        records = dedupe(records)
    if a.only_with_phone:
        records = [r for r in records if r.get("phone") or r.get("whatsapp")]

    save(records, a.out)
    log(f"✔ تم حفظ {len(records)} نشاط في {a.out}")


if __name__ == "__main__":
    main()
