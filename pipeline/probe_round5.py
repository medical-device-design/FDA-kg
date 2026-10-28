#!/usr/bin/env python3
"""Read-only probe for two remaining sources (nothing is written):
  1. Import Alerts (accessdata cms_ia): page structure of the country index and one country page,
     and whether an all-alerts index exists.
  2. Tobacco retailer compliance check inspection database (timp-ccid.fda.gov): a single-page app;
     list the API endpoints its bundle names, so an export route can be judged."""
import re
import sys
import urllib.request

UA = "Mozilla/5.0"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.geturl(), r.read().decode("utf-8", errors="replace")


def links(page, base):
    out = []
    for m in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page, re.S | re.I):
        href, text = m.group(1), " ".join(re.sub(r"<[^>]+>", " ", m.group(2)).split())
        if href.startswith("#") or "javascript" in href:
            continue
        full = href if href.startswith("http") else (base.rsplit("/", 1)[0] + "/" + href if not href.startswith("/") else "https://www.accessdata.fda.gov" + href)
        out.append((full, text))
    return out


print("==== 1. Import alerts")
for url in ["https://www.accessdata.fda.gov/cms_ia/countrylist.html",
            "https://www.accessdata.fda.gov/cms_ia/industrylist.html",
            "https://www.accessdata.fda.gov/cms_ia/ialist.html",
            "https://www.accessdata.fda.gov/cms_ia/default.html"]:
    try:
        st, final, page = get(url)
    except Exception as e:      # noqa: BLE001
        print(f"-- {url}: FAILED {str(e)[:80]}")
        continue
    ls = links(page, url)
    kinds = {}
    for full, text in ls:
        k = re.sub(r"[^a-z_]", "", full.rsplit("/", 1)[-1].split(".")[0].lower())[:12]
        kinds[k] = kinds.get(k, 0) + 1
    print(f"-- {url}: {st} {len(page)} bytes, {len(ls)} links; link-name groups: {sorted(kinds.items(), key=lambda x: -x[1])[:8]}")
    for full, text in ls[:6] + ls[-3:]:
        print(f"     [{text[:50]}] {full}")
    # follow the first country page once
    if "countrylist" in url:
        cp = next((f for f, t in ls if "country" in f.lower() and f != url), None)
        if cp:
            st2, _f, page2 = get(cp)
            ls2 = links(page2, cp)
            print(f"   country page {cp}: {st2} {len(page2)} bytes, {len(ls2)} links")
            ias = [(f, t) for f, t in ls2 if "importalert" in f.lower()]
            print(f"   import-alert links on it: {len(ias)}")
            for f, t in ias[:3]:
                print(f"     [{t[:50]}] {f}")
            if ias:
                st3, _f, page3 = get(ias[0][0])
                print(f"   one alert page: {st3} {len(page3)} bytes, tables {len(re.findall(r'<table', page3, re.I))}, "
                      f"headings: {[' '.join(re.sub(r'<[^>]+>', ' ', h).split())[:40] for h in re.findall(r'<h[1-4][^>]*>(.*?)</h[1-4]>', page3, re.S | re.I)][:12]}")

print("==== 2. timp-ccid.fda.gov")
try:
    st, final, page = get("https://timp-ccid.fda.gov/")
    print(f"-- index: {st} {len(page)} bytes")
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', page, re.I)
    print("   scripts:", scripts)
    for s in scripts:
        if "main" in s or "app" in s:
            u = s if s.startswith("http") else "https://timp-ccid.fda.gov/" + s.lstrip("/")
            st2, _f, js = get(u)
            print(f"   {u}: {st2} {len(js)} bytes")
            found = sorted(set(re.findall(r'(?:https?://[A-Za-z0-9.\-]+)?/(?:api|rest|services?|data)/[A-Za-z0-9_./\-{}]*', js)))
            print("   endpoints:", found[:40])
            hosts = sorted(set(re.findall(r'https?://[A-Za-z0-9.\-]+\.fda\.gov[^"\' )]*', js)))
            print("   fda hosts:", hosts[:20])
            words = sorted(set(re.findall(r'\b(?:export|download|csv|excel|xlsx)\b[A-Za-z]*', js, re.I)))
            print("   export words:", words[:20])
except Exception as e:      # noqa: BLE001
    print("FAILED", str(e)[:100])
