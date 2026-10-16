import os
import json
import io
import time
import requests
import pandas as pd
from datetime import datetime

# ==========================================
# AYARLAR VE ÇEVRE DEĞİŞKENLERİ
# (Secrets tanımlı olmasa veya boş gelse bile linki garantiye alan 'or' yapısı)
# ==========================================
MAKE_WEBHOOK_URL = (
    os.getenv("MAKE_WEBHOOK_URL") 
    or "https://hook.eu1.make.com/w2bw4cexf24z4huxs3nikopnofif1t1j"
)
ONEDRIVE_EXCEL_URL = (
    os.getenv("ONEDRIVE_EXCEL_URL") 
    or "https://1drv.ms/x/c/cb9e9d1c772ef382/IQD2WvVMDCAOSJKa6ur72EdJAQ8UWGwRYYQ-zFsJO2pbYOw?e=Obf4U8"
)
STATE_FILE = "son_bildirimler.json"

# ==========================================
# HİSSE DEĞERİNİ ETKİLEYEN 5 KRİTİK FİLTRE
# ==========================================
FILTRE_KELIMELER = [
    # 1. Ciro ve İş Hacmi (Yeni Nakit Akışı)
    "yeni iş ilişkisi",
    "sözleşme",
    "ihale",
    "sipariş",

    # 2. Finansal Sonuçlar & Raporlama
    "finansal rapor",
    "faaliyet raporu",
    "sorumluluk beyanı",

    # 3. Sermaye & Temettü (Hisse Başı Değer / Sulandırma)
    "sermaye artırımı",
    "bedelli",
    "bedelsiz",
    "kâr payı",
    "temettü",

    # 4. Pay Piyasası & Güven Hamleleri
    "geri alım",
    "pay alım satım",

    # 5. Kritik Gelişmeler & Yapısal Hamleler
    "özel durum açıklaması (genel)",
    "yatırım",
    "birleşme",
    "devralma"
]

KAP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.kap.org.tr/"
}

def download_excel_file(url):
    """OneDrive bağlantısını doğrudan saf .xlsx verisine dönüştürerek indirir (Orijinal çalışan sürüm)."""
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
        print(f"Excel indirme denemesi sırasında hata: {e}")

    return None

def get_open_positions():
    """OneDrive Excel'in 'İşlem_Günlüğü' sayfasından durumu 'AÇIK' olan hisseleri çeker."""
    try:
        content = download_excel_file(ONEDRIVE_EXCEL_URL)
        if not content:
            print("HATA: Excel dosyası indirilemedi.")
            return set()

        excel_file = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
        
        target_sheet = None
        for name in excel_file.sheet_names:
            if "İŞLEM" in name.upper() or "ISLEM" in name.upper():
                target_sheet = name
                break
        
        if not target_sheet:
            target_sheet = excel_file.sheet_names[0]

        df = pd.read_excel(excel_file, sheet_name=target_sheet)
        df.columns = [str(c).strip() for c in df.columns]

        hisse_col = None
        durum_col = None

        for col in df.columns:
            c_upper = col.upper()
            if c_upper in ["HİSSE", "HISSE", "SEMBOL", "KOD"]:
                hisse_col = col
            if "DURUM" in c_upper:
                durum_col = col

        if not hisse_col:
            print(f"HATA: '{target_sheet}' sayfasında 'Hisse' kolonu bulunamadı.")
            return set()

        if durum_col:
            df_acik = df[df[durum_col].astype(str).str.strip().str.upper().isin(["AÇIK", "ACIK"])]
            semboller = set(df_acik[hisse_col].dropna().astype(str).str.strip().str.upper())
        else:
            semboller = set(df[hisse_col].dropna().astype(str).str.strip().str.upper())

        semboller = {s for s in semboller if s and s != "NAN"}
        print(f"Takip edilecek açık pozisyonlar ({len(semboller)} adet): {', '.join(semboller)}")
        return semboller
    except Exception as e:
        print(f"OneDrive Excel okuma hatası: {e}")
        return set()

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
    """İşlenen bildirim ID'lerini kaydeder (Son 1000 ID saklanır)."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_ids)[-1000:], f, ensure_ascii=False, indent=2)

def fetch_company_disclosures(session, hisse_kodu):
    """Belirli bir hissenin bildirimlerini çeker."""
    url = "https://www.kap.org.tr/tr/api/disclosures"
    params = {"stockCodes": hisse_kodu}
    
    for attempt in range(1, 3):
        try:
            res = session.get(url, params=params, headers=KAP_HEADERS, timeout=20)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    return data
            print(f"[{hisse_kodu}] KAP yanıtı: HTTP {res.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"[{hisse_kodu}] Bağlantı denemesi ({attempt}/2): {e}")
            time.sleep(2)
            
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
    """Başlık veya özet metninde 5 kritik gruptan biri geçiyor mu kontrol eder."""
    if not FILTRE_KELIMELER:
        return True
    birlesik_metin = f"{baslik} {ozet}".lower()
    return any(kelime in birlesik_metin for kelime in FILTRE_KELIMELER)

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Şirket bazlı KAP taraması başlatıldı.")
    
    acik_hisseler = get_open_positions()
    if not acik_hisseler:
        print("Takip edilecek açık pozisyon bulunamadı. Tarama tamamlandı.")
        return

    seen_ids = load_seen_ids()
    session = requests.Session()
    yeni_sayac = 0

    for hisse in acik_hisseler:
        print(f"-> {hisse} taranıyor...")
        bildirimler = fetch_company_disclosures(session, hisse)
        
        for item in bildirimler:
            disclosure = item.get("basic", {}) if "basic" in item else item
            
            bildirim_id = str(disclosure.get("disclosureIndex") or disclosure.get("id") or "")
            sembol = str(disclosure.get("stockCodes") or disclosure.get("companyOid") or hisse).strip().upper()
            baslik = disclosure.get("title") or disclosure.get("disclosureType") or "KAP Bildirimi"
            zaman = disclosure.get("publishDate") or datetime.now().strftime("%d.%m.%Y %H:%M")
            ozet = str(disclosure.get("summary") or baslik).strip()

            if not bildirim_id or bildirim_id in seen_ids:
                continue

            if filtreye_uyuyor_mu(baslik, ozet):
                kap_link = f"https://www.kap.org.tr/tr/Bildirim/{bildirim_id}"
                payload = {
                    "sembol": sembol,
                    "baslik": baslik,
                    "zaman": zaman,
                    "kap_link": kap_link,
                    "ozet": ozet
                }
                print(f"  [KRİTİK BİLDİRİM] {sembol}: {baslik}")
                basarili = send_to_make(payload)
                if basarili:
                    seen_ids.add(bildirim_id)
                    yeni_sayac += 1
            else:
                seen_ids.add(bildirim_id)

    save_seen_ids(seen_ids)
    print(f"Tarama tamamlandı. {yeni_sayac} adet kritik bildirim Make.com'a aktarıldı.")

if __name__ == "__main__":
    main()
