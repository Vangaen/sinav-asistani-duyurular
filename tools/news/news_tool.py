#!/usr/bin/env python3
"""Gelişmeler üretim aracı: kaynaklardan (RSS) ve elle gelen kutusundan (inbox.json) yeni
duyuruları bulur, Claude ile 2-3 cümlelik özet çıkarır, duyurular.json'a ekler.

Kurallar (kodda zorunlu):
  - `tarih` ve `uyari` kayıtları HER ZAMAN status=draft (insan onayı gerekir).
  - Tarih içeren her kayıt draft'tır (tür haber gelse bile tarih'e çevrilir).
  - Yalnızca tarihsiz genel `haber` / `deneme` published olabilir.
  - Özet kaynak metinden uzun birebir parça içeriyorsa draft'a düşer.
  - ANTHROPIC_API_KEY ortam değişkeninden okunur; yoksa özetleme yapılmaz (hiçbir şey 'görüldü' sayılmaz).

Kullanım:  python news_tool.py --feed duyurular.json [--today 2026-11-13]
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "claude-haiku-5-5"
API_URL = "https://api.anthropic.com/v1/messages"
USER_AGENT = "sinav-asistani-news/1.0"
TYPES = {"tarih", "haber", "deneme", "uyari"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VERBATIM_WORDS = 8  # özette kaynaktan ardışık bu kadar kelime aynıysa kopya sayılır

PROMPT = """Aşağıdaki resmi duyuru metnini oku ve YALNIZCA şu JSON'u döndür (başka metin yok):
{{"type": "tarih|haber|deneme|uyari", "title": "kısa başlık (en çok 70 karakter)",
 "body": "2-3 cümlelik sade Türkçe bilgi", "date": "YYYY-MM-DD veya boş", "date_end": "YYYY-MM-DD veya boş"}}
Kurallar:
- Orijinal metni kopyalama; yalnızca olguyu kendi cümlelerinle yaz.
- Emin olmadığın tarihi YAZMA (boş bırak). Tarihi metinde açıkça görmediysen tahmin etme.
- type: sınav/başvuru/sonuç tarihi içeriyorsa "tarih"; ülke geneli deneme ise "deneme"; önemli uyarı ise "uyari"; diğer "haber".
Kaynak adı: {source}
Metin:
{text}
"""


# --- Yardımcılar ---------------------------------------------------------------

def today_str(override=None):
    return override or dt.date.today().isoformat()


def add_days(date_str, days):
    return (dt.date.fromisoformat(date_str) + dt.timedelta(days=days)).isoformat()


def stable_id(exam, key):
    return "%s-%s" % (exam, hashlib.sha1(key.encode("utf-8")).hexdigest()[:10])


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def words(text):
    return re.findall(r"\w+", text.lower())


def copies_source(body, source_text, n=VERBATIM_WORDS):
    """Özet, kaynaktan ardışık n kelime birebir alıyor mu?"""
    src = words(source_text)
    grams = {" ".join(src[i:i + n]) for i in range(max(len(src) - n + 1, 0))}
    b = words(body)
    return any(" ".join(b[i:i + n]) in grams for i in range(max(len(b) - n + 1, 0)))


# --- Çekme ---------------------------------------------------------------------

def _child(node, name):
    for c in node:
        if c.tag.split("}")[-1] == name:
            return c
    return None


def fetch_rss(url, timeout=15):
    """RSS 2.0 / Atom: [{key, title, text, url}]. Hata olursa boş liste."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            root = ET.fromstring(r.read())
    except Exception as e:  # ağ/XML hatası sessiz geçilir
        print("kaynak okunamadı: %s (%s)" % (url, e), file=sys.stderr)
        return []
    out = []
    for it in root.iter():
        if it.tag.split("}")[-1] not in ("item", "entry"):
            continue
        t = _child(it, "title")
        title = (t.text or "").strip() if t is not None else ""
        l = _child(it, "link")
        link = ((l.get("href") or l.text or "").strip()) if l is not None else ""
        d = _child(it, "description") or _child(it, "summary")
        desc = re.sub(r"<[^>]+>", " ", (d.text or "") if d is not None else "")
        g = _child(it, "guid") or _child(it, "id")
        key = (g.text or "").strip() if g is not None and g.text else (link or title)
        if title and key:
            out.append({"key": key, "title": title, "text": (title + ". " + desc).strip(), "url": link})
    return out


def collect(sources_path, inbox_path):
    """Her kaynaktan ham girdiler: [{exam, source_name, key, title, text, url}]."""
    entries = []
    for s in load_json(sources_path, {}).get("sources", []):
        if not s.get("enabled") or not s.get("url"):
            continue
        for e in fetch_rss(s["url"]):
            entries.append({"exam": s["exam"], "source_name": s["name"], **e})
    for e in load_json(inbox_path, []):
        if e.get("text") and e.get("url"):
            entries.append({"exam": e.get("exam", "yks"), "source_name": e.get("source_name", ""),
                            "key": e.get("key") or e["url"], "title": e.get("title", ""),
                            "text": e["text"], "url": e["url"]})
    return entries


# --- Özetleme ------------------------------------------------------------------

def claude_summarize(entry):
    """Claude API ile özet. Dönen: sözlük (PROMPT'taki alanlar) ya da None."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return None
    body = {"model": MODEL, "max_tokens": 500, "messages": [{
        "role": "user", "content": PROMPT.format(source=entry["source_name"], text=entry["text"][:6000])}]}
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode("utf-8"), headers={
        "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            reply = json.load(r)
        text = "".join(b.get("text", "") for b in reply.get("content", []))
        return json.loads(text[text.index("{"):text.rindex("}") + 1])
    except Exception as e:
        print("özetleme başarısız: %s" % e, file=sys.stderr)
        return None


def build_item(entry, summary, today):
    """Özetten feed kaydı. Taslak/yayın kuralı BURADA uygulanır."""
    typ = summary.get("type") if summary.get("type") in TYPES else "haber"
    date = summary.get("date", "") if DATE_RE.match(str(summary.get("date", ""))) else ""
    date_end = summary.get("date_end", "") if DATE_RE.match(str(summary.get("date_end", ""))) else ""
    if date_end and not date:
        date, date_end = date_end, ""
    if date and date_end and date_end < date:
        date_end = ""
    body = str(summary.get("body", "")).strip()
    title = str(summary.get("title", "")).strip() or entry["title"]
    if date and typ == "haber":
        typ = "tarih"
    status = "published"
    if typ in ("tarih", "uyari") or date or date_end:
        status = "draft"
    if copies_source(body, entry["text"]):
        status = "draft"
    if typ == "tarih" and (date or date_end):
        expires = add_days(date_end or date, 1)
    else:
        expires = add_days(today, 30)
    return {
        "id": stable_id(entry["exam"], entry["key"]), "exam": entry["exam"], "type": typ,
        "title": title[:90], "body": body, "date": date, "date_end": date_end,
        "source_name": entry["source_name"], "source_url": entry["url"],
        "published": today, "expires": expires, "sponsored": False, "status": status,
    }


# --- Birleştirme ---------------------------------------------------------------

def run(feed_path, seen_path, entries, summarizer, today):
    """Yeni girdileri özetleyip feed'e ekler; süresi dolanları temizler. Eklenen kayıtları döndürür."""
    feed = load_json(feed_path, {"version": 1, "updated": "", "items": []})
    items = feed.get("items", [])
    seen = set(load_json(seen_path, []))
    known = {i["id"] for i in items}
    added = []
    for e in entries:
        item_id = stable_id(e["exam"], e["key"])
        if item_id in seen or item_id in known:
            continue
        summary = summarizer(e)
        if not summary:
            continue  # özetlenemedi: görülmedi sayılır, sonra yeniden denenir
        item = build_item(e, summary, today)
        items.append(item)
        known.add(item["id"])
        seen.add(item["id"])
        added.append(item)
    items = [i for i in items if not i.get("expires") or i["expires"] >= today]
    feed.update({"version": 1, "updated": today + "T06:00:00Z", "items": items})
    save_json(feed_path, feed)
    save_json(seen_path, sorted(seen))
    return added


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--feed", default=os.path.join(HERE, "..", "..", "duyurular.json"))
    p.add_argument("--seen", default=os.path.join(HERE, "seen.json"))
    p.add_argument("--sources", default=os.path.join(HERE, "sources.json"))
    p.add_argument("--inbox", default=os.path.join(HERE, "inbox.json"))
    p.add_argument("--today", default=None)
    a = p.parse_args()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY yok; özetleme atlandı.", file=sys.stderr)
        return 0
    added = run(a.feed, a.seen, collect(a.sources, a.inbox), claude_summarize, today_str(a.today))
    for i in added:
        print("+ [%s] %s (%s)" % (i["status"], i["title"], i["id"]))
    print("%d yeni kayıt." % len(added))
    return 0


if __name__ == "__main__":
    sys.exit(main())
