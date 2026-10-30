import os
import io
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# AYARLAR (POWER BI HAFIZALI MOTOR)
# ==========================================
ONEDRIVE_EXCEL_URL = (
    os.getenv("ONEDRIVE_EXCEL_URL") 
    or "https://1drv.ms/x/c/cb9e9d1c772ef382/IQD2WvVMDCAOSJKa6ur72EdJAQ8UWGwRYYQ-zFsJO2pbYOw?e=Obf4U8"
)

OSE_CSV_PATH = "ziraat_carpanlar.csv"
KAP_CSV_OUTPUT = "kap_haberler.csv"

# Arşivde ve taramada tutulacak gün penceresi (Son 10 gün)
GUN_LIMITI = 10

# Şirket Değerini ve Riskini Etkileyen Seçili Kritik Kategoriler
FILTRE_KELIMELER = [
    # 1. Ticari Operasyonlar & Siparişler
    "yeni iş ilişkisi",
    "sözleşme",
    "ihale",
    "sipariş",
    "üretim başlangıcı",
    "seri üretim",
    
    # 2. Yatırım, Büyüme & Teşvikler
    "yatırım",
    "yatırım teşvik",
    "teşvik belgesi",
    "kapasite artır",
    "yeni tesis",
    "ruhsat",
    "lisans",
    
    # 3. Finansal Tablolar & Denetim
    "finansal rapor",
    "faaliyet raporu",
    "sorumluluk beyanı",
    "kredi derecelendirme",
    "derecelendirme notu",
    
    # 4. Sermaye, Temettü & Şirket Aksiyonları
    "sermaye artırımı",
    "bedelli",
    "bedelsiz",
    "tahsisli",
    "kâr payı",
    "temettü",
    "geri alım",
    "pay alım satım",
    "birleşme",
    "devralma",
    "şirket kuruluşu",
    "bağlı ortaklık",
    
    # 5. SPK & Borsa Tedbirleri
    "vbts",
    "brüt takas",
    "tedbir",
    
    # 6. Genel Özel Durum Açıklamaları
    "özel durum açıklaması"
]

# Aracı kurum bültenleri, piyasa anketleri ve hedef fiyat yorumları
KARA_LISTE = [
    "bülteni",
    "anketi",
    "hedef fiyat",
    "model portföy",
    "öneri listesi",
    "hisse analizi",
    "beklentileri"
]

def download_excel_file(url):
    session = requests.Session()
    target_url = url if "download=1" in url else f"{url}&download=1"
    try:
        res = session.get(target_url, allow_redirects=True, timeout=25)
        if "view.aspx" in res.url:
            direct_url = res.url.replace("view.aspx", "download.aspx")
            res = session.get(direct_url, timeout=25)
        if res.content.startswith(b'PK'):
            return res.content
        live_download_url = "https://onedrive.live.com/download?cid=CB9E9D1C772EF382&resid=CB9E9D1C772EF382!s4cf55af6200c480e929aeaeafbd84749"
        res_live = session.get(live_download_url, allow_redirects=True, timeout=25)
        if res_live.content.startswith(b'PK'):
            return res_live.content
    except Exception as e:
        print(f"Excel indirme hatası: {e}")
    return None

def get_open_positions():
    try:
        content = download_excel_file(ONEDRIVE_EXCEL_URL)
        if not content:
            return set()
        excel_file = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
        target_sheet = next((s for s in excel_file.sheet_names if "İŞLEM" in s.upper() or "ISLEM" in s.upper()), excel_file.sheet_names[0])
        df = pd.read_excel(excel_file, sheet_name=target_sheet)
        df.columns = [str(c).strip() for c in df.columns]

        hisse_col = next((c for c in df.columns if c.upper() in ["HİSSE", "HISSE", "SEMBOL", "KOD"]), None)
        durum_col = next((c for c in df.columns if "DURUM" in c.upper()), None)

        if not hisse_col:
            return set()

        if durum_col:
            df_acik = df[df[durum_col].astype(str).str.strip().str.upper().isin(["AÇIK", "ACIK"])]
            semboller = set(df_acik[hisse_col].dropna().astype(str).str.strip().str.upper())
        else:
            semboller = set(df[hisse_col].dropna().astype(str).str.strip().str.upper())

        return {s for s in semboller if s and s != "NAN"}
    except Exception as e:
        print(f"OneDrive okuma hatası: {e}")
        return set()

def get_radar_candidates(limit=150):
    if not os.path.exists(OSE_CSV_PATH):
        return set()
    try:
        df = pd.read_csv(OSE_CSV_PATH)
        mask = df["Veto_Durum"].astype(str).str.contains("GEÇTİ|GECTI", case=False, na=False)
        df_filtered = df[mask]
        if "OSE_Skor" in df_filtered.columns:
            df_sorted = df_filtered.sort_values(by="OSE_Skor", ascending=False)
            return set(df_sorted["Hisse"].dropna().head(limit).astype(str).str.strip().str.upper())
        return set(df_filtered["Hisse"].dropna().head(limit).astype(str).str.strip().str.upper())
    except Exception as e:
        print(f"Ziraat çarpanlar okuma hatası: {e}")
        return set()

def load_existing_archive():
    """Mevcut kap_haberler.csv dosyasını hafızaya yükler ve kimlik kümesi üretir."""
    if not os.path.exists(KAP_CSV_OUTPUT):
        return [], set()
    try:
        df = pd.read_csv(KAP_CSV_OUTPUT)
        if df.empty or "Hisse" not in df.columns or "Baslik" not in df.columns:
            return [], set()

        # Kayıtları sözlük listesine dönüştür
        arsiv_listesi = df.to_dict("records")
        
        # Benzersiz anahtar: "Hisse__Baslik"
        hafiza_kumesi = {
            f"{str(row.get('Hisse', '')).strip().upper()}__{str(row.get('Baslik', '')).strip().lower()}"
            for row in arsiv_listesi
        }
        return arsiv_listesi, hafiza_kumesi
    except Exception as e:
        print(f"Arşiv okuma hatası: {e}")
        return [], set()

def parse_date_and_check(date_val):
    cutoff = datetime.now() - timedelta(days=GUN_LIMITI)
    dt = None

    if isinstance(date_val, (int, float)):
        dt = datetime.fromtimestamp(date_val)
    elif isinstance(date_val, str):
        date_str = date_val.strip()
        try:
            dt = datetime.strptime(date_str, "%d.%m.%Y %H:%M")
        except Exception:
            pass
        if not dt:
            try:
                dt = datetime.strptime(date_str, "%d.%m.%Y")
            except Exception:
                pass
        if not dt:
            try:
                dt = parsedate_to_datetime(date_str).replace(tzinfo=None)
            except Exception:
                pass

    if dt and dt >= cutoff:
        return True, dt.strftime("%d.%m.%Y %H:%M"), dt
    return False, "", None

def filtreye_uyuyor_mu(baslik, ozet):
    metin = f"{baslik} {ozet}".lower()
    if any(k in metin for k in KARA_LISTE):
        return False
    return any(k in metin for k in FILTRE_KELIMELER)

def fetch_from_tradingview(session, hisse, hafiza_kumesi):
    url = f"https://news-headlines.tradingview.com/v2/headlines?client=web&lang=tr&symbol=BIST%3A{hisse}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.tradingview.com/"
    }
    try:
        res = session.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            items = res.json().get("items", [])
            sonuclar = []
            for it in items:
                baslik = (it.get("title") or "KAP Bildirimi").strip()
                
                # HAFIZA KONTROLÜ: Zaten kayıtlıysa hiç uğraşma, atla
                kimlik = f"{hisse.upper()}__{baslik.lower()}"
                if kimlik in hafiza_kumesi:
                    continue

                pub_ts = it.get("published")
                gecerli, tarih_str, _ = parse_date_and_check(pub_ts)
                if not gecerli:
                    continue

                ozet = (it.get("shortDescription") or baslik).strip()
                if not filtreye_uyuyor_mu(baslik, ozet):
                    continue

                link = it.get("link") or (f"https://www.tradingview.com{it.get('storyPath')}" if it.get("storyPath") else "")
                sonuclar.append({
                    "Hisse": hisse,
                    "Tarih": tarih_str,
                    "Baslik": baslik,
                    "Ozet": ozet,
                    "KAP_Linki": link
                })
            return sonuclar
    except Exception:
        pass
    return []

def fetch_from_google_rss(session, hisse, hafiza_kumesi):
    url = f"https://news.google.com/rss/search?q={hisse}+kap+bildirimi&hl=tr&gl=TR&ceid=TR:tr"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    }
    try:
        res = session.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            sonuclar = []
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                
                # HAFIZA KONTROLÜ: Zaten kayıtlıysa atla
                kimlik = f"{hisse.upper()}__{title.lower()}"
                if kimlik in hafiza_kumesi:
                    continue

                pub_date = item.findtext("pubDate") or ""
                gecerli, tarih_str, _ = parse_date_and_check(pub_date)
                if not gecerli:
                    continue

                if not filtreye_uyuyor_mu(title, title):
                    continue

                link = item.findtext("link") or ""
                sonuclar.append({
                    "Hisse": hisse,
                    "Tarih": tarih_str,
                    "Baslik": title,
                    "Ozet": title,
                    "KAP_Linki": link
                })
            return sonuclar
    except Exception:
        pass
    return []

def fetch_company_disclosures(hisse, hafiza_kumesi):
    session = requests.Session()
    veriler = fetch_from_tradingview(session, hisse, hafiza_kumesi)
    if not veriler:
        veriler = fetch_from_google_rss(session, hisse, hafiza_kumesi)
    return hisse, veriler

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Hafızalı KAP Taraması Başlatıldı.")

    # 1. Mevcut Hafızayı Yükle
    mevcut_arsiv, hafiza_kumesi = load_existing_archive()
    print(f"Hafızadaki Mevcut Haber Sayısı: {len(mevcut_arsiv)}")

    # 2. Takip Listesi (Portföy + İlk 150 Radar Adayı + AKSA)
    aciklar = get_open_positions()
    radar_liderleri = get_radar_candidates(limit=150)
    tum_takip = aciklar.union(radar_liderleri).union({"AKSA"})

    print(f"Toplam Taranacak Hisse Sayısı: {len(tum_takip)}")

    yeni_haberler = []

    # 3. Paralel Tarama (Hafızada olanlar anında elenir)
    with ThreadPoolExecutor(max_workers=10) as executor:
        gelecek_sonuclar = {executor.submit(fetch_company_disclosures, h, hafiza_kumesi): h for h in tum_takip}
        for future in as_completed(gelecek_sonuclar):
            _, bildirimler = future.result()
            if bildirimler:
                for b in bildirimler:
                    # Yeni gelen haberi anlık hafızaya da kaydet (çift eklenmesin)
                    k = f"{b['Hisse'].upper()}__{b['Baslik'].lower()}"
                    if k not in hafiza_kumesi:
                        hafiza_kumesi.add(k)
                        yeni_haberler.append(b)

    print(f"Tarama Tamamlandı. Tespit Edilen YENİ Haber Sayısı: {len(yeni_haberler)}")

    # 4. Arşiv ile Yeni Haberleri Birleştir
    toplam_liste = mevcut_arsiv + yeni_haberler

    if toplam_liste:
        df_pbi = pd.DataFrame(toplam_liste).drop_duplicates(subset=["Hisse", "Baslik"])
        
        # Tarih formatını parse edip 10 günden eskiyenleri arşivden temizleme
        df_pbi["Tarih_DT"] = pd.to_datetime(df_pbi["Tarih"], format="%d.%m.%Y %H:%M", errors="coerce")
        
        # Son 10 gün sınırından eski olanları dosyadan düşür (Dosya şişmesini önler)
        zaman_esigi = datetime.now() - timedelta(days=GUN_LIMITI)
        df_pbi = df_pbi[(df_pbi["Tarih_DT"] >= zaman_esigi) | (df_pbi["Tarih_DT"].isna())]
        
        # En yeniden eskiye sırala
        df_pbi = df_pbi.sort_values(by="Tarih_DT", ascending=False).drop(columns=["Tarih_DT"])
    else:
        df_pbi = pd.DataFrame(columns=["Hisse", "Tarih", "Baslik", "Ozet", "KAP_Linki"])

    # 5. Güncellenmiş Dosyayı Kaydet
    df_pbi.to_csv(KAP_CSV_OUTPUT, index=False, encoding="utf-8-sig")
    print(f"[Power BI] Toplam {len(df_pbi)} adet güncel haber '{KAP_CSV_OUTPUT}' dosyasında saklanıyor.")

if __name__ == "__main__":
    main()
