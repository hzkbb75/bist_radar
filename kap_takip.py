from datetime import datetime
import io
import json
import os
import time
import pandas as pd
import requests

# ==========================================
# AYARLAR VE ÇEVRE DEĞİŞKENLERİ
# ==========================================
MAKE_WEBHOOK_URL = os.getenv(
    "MAKE_WEBHOOK_URL",
    "https://hook.eu1.make.com/w2bw4cexf24z4huxs3nikopnofif1t1j",
)

# kartal.py'ye eklediğiniz Google Sheets "Web'de Yayınla > CSV" bağlantısını buraya da yapıştırın
GOOGLE_SHEETS_CSV_URL = os.getenv(
    "GOOGLE_SHEETS_CSV_URL",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vT_ORNEK_BAGLANTI/pub?gid=0&single=true&output=csv",
)

STATE_FILE = "son_bildirimler.json"

# ==========================================
# HİSSE DEĞERİNİ ETKİLEYEN KRİTİK FİLTRE
# ==========================================
FILTRE_KELIMELER = [
    "yeni iş ilişkisi",
    "sözleşme",
    "ihale",
    "sipariş",
    "finansal rapor",
    "faaliyet raporu",
    "sorumluluk beyanı",
    "sermaye artırımı",
    "bedelli",
    "bedelsiz",
    "kâr payı",
    "temettü",
    "geri alım",
    "pay alım satım",
    "özel durum açıklaması (genel)",
    "yatırım",
    "birleşme",
    "devralma",
]


def get_open_positions():
  """Google Sheets CSV üzerinden anlık taşınan/açık hisse kodlarını çeker."""
  if not GOOGLE_SHEETS_CSV_URL or "2PACX" not in GOOGLE_SHEETS_CSV_URL:
    print("UYARI: Geçerli bir Google Sheets CSV bağlantısı tanımlanmadı.")
    # Acil durum yedeği (mevcut çekirdek hisseleriniz)
    return {
        "PETKM",
        "ASELS",
        "TABGD",
        "EREGL",
        "AKBNK",
        "MPARK",
        "BIMAS",
        "TTKOM",
        "ANSGR",
    }

  try:
    # Google Sheets CSV'sini doğrudan pandas ile tek hamlede oku
    df = pd.read_csv(GOOGLE_SHEETS_CSV_URL.strip())
    df.columns = [str(c).strip().upper() for c in df.columns]

    hisse_col = None
    for col in df.columns:
      if col in [
          "HİSSE_KODU",
          "HISSE_KODU",
          "HİSSE",
          "HISSE",
          "SEMBOL",
          "KOD",
      ]:
        hisse_col = col
        break

    if not hisse_col:
      print("HATA: Google Sheets tablosunda 'Hisse_Kodu' kolonu bulunamadı.")
      return set()

    # Sayfadaki tüm hisse kodlarını al
    semboller = set(df[hisse_col].dropna().astype(str).str.strip().str.upper())
    # Toplam ve para piyasası etiketlerini temizle
    semboller = {
        s
        for s in semboller
        if s and s not in ["NAN", "TOPLAM", "GENEL TOPLAM", "OSL(B)", "OSL"]
    }

    print(
        f"Takip edilecek açık pozisyonlar ({len(semboller)} adet):"
        f" {', '.join(sorted(semboller))}"
    )
    return semboller

  except Exception as e:
    print(f"Google Sheets okuma hatası: {e}")
    # Bağlantı anlık koparsa boş dönüp taramayı kitlememek için çekirdek portföyü döndür
    return {
        "PETKM",
        "ASELS",
        "TABGD",
        "EREGL",
        "AKBNK",
        "MPARK",
        "BIMAS",
        "TTKOM",
        "ANSGR",
    }


def load_seen_ids():
  """Daha önce işlenmiş bildirim ID'lerini yükler."""
  if os.path.exists(STATE_FILE):
    try:
      with open(STATE_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))
    except Exception:
      return set()
  return set()


def save_seen_ids(seen_ids):
  """İşlenen bildirim ID'lerini kaydeder (Son 1000 ID)."""
  with open(STATE_FILE, "w", encoding="utf-8") as f:
    json.dump(list(seen_ids)[-1000:], f, ensure_ascii=False, indent=2)


def fetch_from_bigpara(session, hisse):
  """Bigpara üzerinden hissenin son KAP bildirimlerini çeker."""
  url = f"https://bigpara.hurriyet.com.tr/api/v1/hisse/kaphaberleri/{hisse}"
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"
          " Safari/537.36"
      ),
      "Referer": "https://bigpara.hurriyet.com.tr/",
  }
  res = session.get(url, headers=headers, timeout=12)
  if res.status_code == 200:
    data = res.json()
    raw_list = (
        data.get("data", [])
        if isinstance(data, dict)
        else (data if isinstance(data, list) else [])
    )
    sonuclar = []
    for d in raw_list:
      b_id = str(d.get("id") or d.get("disclosureIndex") or "")
      if not b_id:
        continue
      sonuclar.append({
          "id": b_id,
          "symbol": hisse,
          "title": d.get("title") or d.get("baslik") or "KAP Bildirimi",
          "date": (
              d.get("date")
              or d.get("tarih")
              or datetime.now().strftime("%d.%m.%Y %H:%M")
          ),
          "summary": d.get("spot") or d.get("ozet") or d.get("title") or "",
          "link": d.get("url") or f"https://www.kap.org.tr/tr/Bildirim/{b_id}",
      })
    return sonuclar
  return []


def fetch_from_tradingview(session, hisse):
  """TradingView BIST akışı üzerinden KAP bildirimlerini çeker (Yedek kaynak)."""
  url = (
      "https://news-headlines.tradingview.com/v2/headlines?lang=tr&symbol=BIST%3A"
      f"{hisse}"
  )
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"
          " Safari/537.36"
      )
  }
  res = session.get(url, headers=headers, timeout=12)
  if res.status_code == 200:
    data = res.json()
    items = data.get("items", []) if isinstance(data, dict) else []
    sonuclar = []
    for it in items:
      b_id = str(it.get("id") or "")
      pub_ts = it.get("published")
      pub_str = (
          datetime.fromtimestamp(pub_ts).strftime("%d.%m.%Y %H:%M")
          if pub_ts
          else datetime.now().strftime("%d.%m.%Y %H:%M")
      )
      link = it.get("link") or (
          f"https://www.tradingview.com{it.get('storyPath')}"
          if it.get("storyPath")
          else ""
      )
      sonuclar.append({
          "id": b_id,
          "symbol": hisse,
          "title": it.get("title") or "KAP Bildirimi",
          "date": pub_str,
          "summary": it.get("shortDescription") or it.get("title") or "",
          "link": link,
      })
    return sonuclar
  return []


def fetch_company_disclosures(session, hisse):
  """Bulut sunucularını engellemeyen kaynaklardan sırayla bildirim çeker."""
  try:
    veriler = fetch_from_bigpara(session, hisse)
    if veriler:
      return veriler
  except Exception as e:
    print(f"[{hisse}] Bigpara sorgusu geçildi: {e}")

  try:
    veriler = fetch_from_tradingview(session, hisse)
    if veriler:
      return veriler
  except Exception as e:
    print(f"[{hisse}] TradingView sorgusu geçildi: {e}")

  return []


def send_to_make(payload):
  """Bildirimi Make.com Webhook'una iletir."""
  if not MAKE_WEBHOOK_URL:
    return False
  try:
    res = requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=15)
    return res.status_code == 200
  except Exception as e:
    print(f"Make.com iletim hatası: {e}")
    return False


def filtreye_uyuyor_mu(baslik, ozet):
  """Başlık veya özet metninde kritik gruptan biri geçiyor mu kontrol eder."""
  if not FILTRE_KELIMELER:
    return True
  birlesik = f"{baslik} {ozet}".lower()
  return any(k in birlesik for k in FILTRE_KELIMELER)


def main():
  print(
      f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Şirket bazlı KAP"
      " taraması başlatıldı."
  )

  acik_hisseler = get_open_positions()
  if not acik_hisseler:
    print("Takip edilecek açık pozisyon bulunamadı. Tarama tamamlandı.")
    return

  seen_ids = load_seen_ids()
  session = requests.Session()
  yeni_sayac = 0

  for hisse in acik_hisseler:
    bildirimler = fetch_company_disclosures(session, hisse)

    for item in bildirimler:
      bildirim_id = str(item.get("id") or "")
      sembol = str(item.get("symbol") or hisse).strip().upper()
      baslik = item.get("title") or "KAP Bildirimi"
      zaman = item.get("date") or datetime.now().strftime("%d.%m.%Y %H:%M")
      ozet = str(item.get("summary") or baslik).strip()
      link = (
          item.get("link") or f"https://www.kap.org.tr/tr/Bildirim/{bildirim_id}"
      )

      if not bildirim_id or bildirim_id in seen_ids:
        continue

      if filtreye_uyuyor_mu(baslik, ozet):
        payload = {
            "sembol": sembol,
            "baslik": baslik,
            "zaman": zaman,
            "kap_link": link,
            "ozet": ozet,
        }
        print(f"  [KRİTİK BİLDİRİM] {sembol}: {baslik}")
        basarili = send_to_make(payload)
        if basarili:
          seen_ids.add(bildirim_id)
          yeni_sayac += 1
      else:
        seen_ids.add(bildirim_id)

  save_seen_ids(seen_ids)
  print(
      f"Tarama tamamlandı. {yeni_sayac} adet kritik bildirim Make.com'a"
      " aktarıldı."
  )


if __name__ == "__main__":
  main()
