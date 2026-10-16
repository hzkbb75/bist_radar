import os
import json
import io
import time
import requests
import pandas as pd
from datetime import datetime

# ==========================================
# AYARLAR VE ÇEVRE DEĞİŞKENLERİ
# ==========================================
MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/w2bw4cexf24z4huxs3nikopnofif1t1j"
ONEDRIVE_EXCEL_URL = "https://1drv.ms/x/c/cb9e9d1c772ef382/IQD2WvVMDCAOSJKa6ur72EdJAQ8UWGwRYYQ-zFsJO2pbYOw?e=Obf4U8"
STATE_FILE = "son_bildirimler.json"

# KAP API Endpoint'i
KAP_API_URL = "https://www.kap.org.tr/tr/api/disclosures"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.kap.org.tr/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
}

# İsteğe bağlı: Sadece belirli başlıkları almak isterseniz kelimeleri ekleyebilirsiniz.
# Boş liste [] bırakırsanız açık pozisyondaki hissenin TÜM haberleri Telegram'a iletilir.
FILTRE_BASLIKLAR = []  # Örn: ["Özel Durum Açıklaması", "Finansal Rapor", "Sözleşme"]

def download_excel_file(url):
    """OneDrive bağlantısını doğrudan saf .xlsx verisine dönüştürerek indirir."""
    session = requests.Session()
    target_url = url if "download=1" in url else f"{url}&download=1"
    
    for attempt in range(3):
        try:
            res = session.get(target_url, allow_redirects=True, timeout=30)
            if "view.aspx" in res.url:
                direct_url = res.url.replace("view.aspx", "download.aspx")
                res = session.get(direct_url, timeout=30)
                
            if res.content.startswith(b'PK'):
                return res.content

            live_download_url = "https://onedrive.live.com/download?cid=CB9E9D1C772EF382&resid=CB9E9D1C772EF382!s4cf55af6200c480e929aeaeafbd84749"
            res_live = session.get(live_download_url, allow_redirects=True, timeout=30)
            if res_live.content.startswith(b'PK'):
                return res_live.content
        except requests.exceptions.RequestException:
            if attempt < 2:
                time.sleep(2)
    return None

def get_open_positions():
    """OneDrive Excel'in 'İşlem_Günlüğü' sayfasından Pozisyon Durumu 'AÇIK' olan hisseleri çeker."""
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
        print(f"Takip edilecek portföy hisseleri ({len(semboller)} adet): {', '.join(semboller)}")
        return semboller
    except Exception as e:
        print(f"OneDrive Excel okuma hatası: {e}")
        return set()

def load_seen_ids():
    """Daha önce gönderilmiş bildirim ID'lerini yükler."""
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

def fetch_kap_disclosures():
    """KAP üzerinden son bildirimleri 3 deneme ve 45sn timeout korumasıyla çeker."""
    for attempt in range(1, 4):
        try:
            response = requests.get(KAP_API_URL, headers=HEADERS, timeout=45)
            if response.status_code == 200:
                data = response.json()
                print(f"Canlı akıştan {len(data)} adet KAP bildirimi başarıyla çekildi.")
                return data
            print(f"[{attempt}/3] KAP API uyarısı: HTTP {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"[{attempt}/3] KAP bağlantı hatası (Tekrar deneniyor): {e}")
        
        if attempt < 3:
            time.sleep(3)
            
    print("KAP verisi 3 deneme sonucunda alınamadı.")
    return []

def send_to_make(payload):
    """Eşleşen bildirimi Make.com Webhook'una iletir."""
    if not MAKE_WEBHOOK_URL:
        print("HATA: MAKE_WEBHOOK_URL tanımlı değil!")
        return False
    try:
        res = requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=20)
        return res.status_code == 200
    except Exception as e:
        print(f"Make.com Webhook gönderim hatası: {e}")
        return False

def baslik_uygun_mu(baslik):
    """Konu/başlık filtresi tanımlıysa kontrol eder, boşsa tümünü onaylar."""
    if not FILTRE_BASLIKLAR:
        return True
    return any(f.lower() in baslik.lower() for f in FILTRE_BASLIKLAR)

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Canlı KAP taraması başlatıldı.")
    
    portfoy_sembolleri = get_open_positions()
    if not portfoy_sembolleri:
        print("Açık pozisyon bulunamadı veya liste çekilemedi. Tarama sonlandırılıyor.")
        return

    seen_ids = load_seen_ids()
    bildirimler = fetch_kap_disclosures()
    
    yeni_sayac = 0
    for item in bildirimler:
        disclosure = item.get("basic", {}) if "basic" in item else item
        
        bildirim_id = str(disclosure.get("disclosureIndex") or disclosure.get("id") or "")
        sembol = str(disclosure.get("stockCodes") or disclosure.get("companyOid") or "").strip().upper()
        baslik = disclosure.get("title") or disclosure.get("disclosureType") or "KAP Bildirimi"
        zaman = disclosure.get("publishDate") or datetime.now().strftime("%d.%m.%Y %H:%M")
        ozet = disclosure.get("summary") or baslik
        
        if not bildirim_id or bildirim_id in seen_ids:
            continue
            
        ilgili_hisseler = [s.strip() for s in sembol.replace(";", ",").split(",") if s.strip()]
        eslesen = any(h in portfoy_sembolleri for h in ilgili_hisseler)
        
        if eslesen:
            if baslik_uygun_mu(baslik):
                kap_link = f"https://www.kap.org.tr/tr/Bildirim/{bildirim_id}"
                payload = {
                    "sembol": sembol,
                    "baslik": baslik,
                    "zaman": zaman,
                    "kap_link": kap_link,
                    "ozet": ozet
                }
                print(f"Eşleşme bulundu: {sembol} - {baslik}")
                basarili = send_to_make(payload)
                if basarili:
                    seen_ids.add(bildirim_id)
                    yeni_sayac += 1
            else:
                # İlgili hisse ama filtrenin dışındaki bir haber türü olduğu için işaretlenip geçilir
                seen_ids.add(bildirim_id)
        else:
            seen_ids.add(bildirim_id)

    save_seen_ids(seen_ids)
    print(f"Tarama tamamlandı. {yeni_sayac} adet yeni bildirim Telegram'a aktarıldı.")

if __name__ == "__main__":
    main()
