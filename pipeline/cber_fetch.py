#!/usr/bin/env python3
"""
cber_fetch.py -- L0 snapshot of the two CBER establishment registration query apps, which have
no bulk download:
  eber    Blood Establishment Registration (eBER)            accessdata.fda.gov/scripts/cber/CFAppsPub/
  hcters  Human Cell and Tissue Establishment Registration    accessdata.fda.gov/scripts/cber/CFAppsPub/tiss/

For each establishment status the app offers, one search (100 rows per page) is paged with the
app's own "Display next" link, every list page is saved, and every establishment's detail page is
fetched once and saved. Pages are stored as gzipped HTML, untouched, under
  <snapshot>/<app>/list_<status>_p<N>.html.gz and <snapshot>/<app>/detail/<id>.html.gz
with index.tsv (id, name, city/state/zip, FEI, status, list page) and SOURCE_URL. SHA256SUMS is
written at the end. One request per DELAY seconds, resumable (existing detail files are skipped).

Usage: python3 cber_fetch.py <snapshot_dir> [eber|hcters|both] [delay_seconds]
"""
import gzip
import hashlib
import html
import http.cookiejar
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (research; NSF Proto-OKN FDA products KG; roche0619@outlook.com)"
APPS = {
    "eber": dict(url="https://www.accessdata.fda.gov/scripts/cber/CFAppsPub/",
                 statuses=["ACTIVE", "INACTIVE", "PRE-REGISTERED"], idkey="facility_id"),
    "hcters": dict(url="https://www.accessdata.fda.gov/scripts/cber/CFAppsPub/tiss/index.cfm",
                   statuses=["Registered", "Inactive", "Pre-registered"], idkey="establishment_id"),
}
DELAY = 1.0


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


class App:
    def __init__(self, name, cfg, out):
        self.name, self.cfg, self.out = name, cfg, out
        (out / "detail").mkdir(parents=True, exist_ok=True)
        self.op = None
        self.base = None

    def session(self):
        cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        self.op.addheaders = [("User-Agent", UA)]

    def get(self, url, data=None):
        time.sleep(DELAY)
        body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
        for attempt in range(4):
            try:
                with self.op.open(urllib.request.Request(url, data=body), timeout=120) as r:
                    return r.geturl(), r.read().decode("utf-8", errors="replace")
            except Exception as e:       # noqa: BLE001
                log(f"  retry {attempt + 1}: {e}")
                time.sleep(10 * (attempt + 1))
        raise RuntimeError(f"gave up on {url}")

    def search(self, status):
        """New session, load the form, submit a one-criterion search; returns page 1 HTML."""
        self.session()
        final, page = self.get(self.cfg["url"])
        self.base = final
        form = re.search(r"<form\b[^>]*>.*?</form>", page, re.S | re.I).group(0)
        action = re.search(r'action="([^"]*)"', form).group(1)
        data = {}
        for inp in re.finditer(r"<input\b[^>]*>", form, re.I):
            tag = inp.group(0)
            name = re.search(r'name="([^"]*)"', tag)
            typ = re.search(r'type="([^"]*)"', tag)
            if not name or (typ and typ.group(1) in ("submit", "button")):
                continue
            val = re.search(r'value="([^"]*)"', tag)
            data[name.group(1)] = html.unescape(val.group(1)) if (typ and typ.group(1) == "hidden" and val) else ""
        for sel in re.findall(r'<select\b[^>]*name="([^"]*)"', form):
            data[sel] = ""
        data.update({"EstablishmentStatus": status, "Sortby": "BusinessName", "nrecords": "100", "SubmitButton": "Continue"})
        final2, res = self.get(urllib.parse.urljoin(final, action), data)
        if "attackerror" in final2:
            raise RuntimeError(f"search for {status} rejected: {final2}")
        return res

    def next_page(self, n):
        final, res = self.get(urllib.parse.urljoin(self.base, f"index.cfm?fuseAction=fuse_DisplaySearchResults&pagenum={n}"))
        return res

    def rows(self, page):
        """(id, name, place, FEI, status) per result row, in the table's column order."""
        out = []
        # split on row starts rather than matching <tr>...</tr>: the tissue app's result
        # table has unclosed rows, and only result rows carry a detail link anyway
        for tr in re.split(r"<tr\b", page, flags=re.I):
            m = re.search(self.cfg["idkey"] + r"=(\d+)", tr)
            if not m:
                continue
            cells = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
                     for c in re.findall(r"<td\b[^>]*>(.*?)</td>", tr, re.S | re.I)]
            cells = (cells + ["", "", "", ""])[:4]
            out.append((m.group(1),) + tuple(cells))
        return out

    def save(self, name, text):
        with gzip.open(self.out / name, "wt", encoding="utf-8") as fh:
            fh.write(text)

    def detail(self, rid):
        path = self.out / "detail" / f"{rid}.html.gz"
        if path.exists():
            return False
        url = urllib.parse.urljoin(self.base, f"index.cfm?fuseAction=fuse_ActionSearchResults&{self.cfg['idkey']}={rid}")
        final, res = self.get(url)
        if "DisplayDetails" not in final or "attackerror" in final:
            raise RuntimeError(f"detail {rid} landed on {final}")
        self.save(f"detail/{rid}.html.gz", res)
        return True


def run(app_name, snap):
    cfg = APPS[app_name]
    out = snap / app_name
    app = App(app_name, cfg, out)
    (out / "SOURCE_URL").write_text(cfg["url"] + "\n", encoding="utf-8")
    index = {}
    for status in cfg["statuses"]:
        slug = re.sub(r"[^a-z0-9]+", "_", status.lower())
        page = app.search(status)
        n = 1
        while True:
            app.save(f"list_{slug}_p{n}.html.gz", page)
            rows = app.rows(page)
            for r in rows:
                index.setdefault(r[0], r[1:] + (status, f"list_{slug}_p{n}"))
            log(f"{app_name} {status} page {n}: {len(rows)} rows, {len(index)} ids so far")
            if not rows or not re.search(r'pagenum=%d\'' % (n + 1), page):
                break
            n += 1
            page = app.next_page(n)
        # details for this status while the session that produced the list is alive
        done = skipped = 0
        for rid, meta in list(index.items()):
            if meta[4] != status:
                continue
            try:
                new = app.detail(rid)
            except RuntimeError as e:
                log(f"  {e}; new session")
                app.search(status)
                new = app.detail(rid)
            done += new
            skipped += (not new)
            if (done + skipped) % 200 == 0:
                log(f"  {app_name} {status}: {done} fetched, {skipped} already present")
        log(f"{app_name} {status}: details {done} fetched, {skipped} already present")
    with open(out / "index.tsv", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("id\tname\tplace\tfei\tstatus_cell\tstatus\tlist_page\n")
        for rid, meta in sorted(index.items(), key=lambda kv: int(kv[0])):
            fh.write("\t".join((rid,) + meta) + "\n")
    with open(out / "SHA256SUMS", "w", encoding="utf-8", newline="\n") as fh:
        for p in sorted(out.rglob("*")):
            if p.is_file() and p.name != "SHA256SUMS":
                fh.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n")
    log(f"{app_name} done: {len(index)} establishments")


if __name__ == "__main__":
    snap = Path(sys.argv[1])
    which = sys.argv[2] if len(sys.argv) > 2 else "both"
    if len(sys.argv) > 3:
        DELAY = float(sys.argv[3])
    for name in (["eber", "hcters"] if which == "both" else [which]):
        run(name, snap)
    print("DONE cber_fetch")
