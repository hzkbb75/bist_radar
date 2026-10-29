# ==============================================================================
# HAFTALIK ZİRAAT BİST TÜM PİYASA ÇARPANLARI & SEKTÖREL MEDYAN MOTORU
# ==============================================================================
import os
import json
import requests
import statistics
import csv
import urllib3
from datetime import datetime, timedelta

# SSL ve Güvenlik Uyarılarını Sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. KURULUM KONTROLÜ ---
try:
    import pdfplumber
except ImportError:
    import subprocess
    subprocess.check_call(["pip", "install", "pdfplumber"])
    import pdfplumber

import pandas as pd

# --- 2. AYARLAR & ENTEGRASYONLAR ---
MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/wa77gag3g9hqdubo8tn401h7yssknf7c"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8897693829:AAEHKHoRKSN-h3RRRU60bDCq3wcuLstivI4")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "932085366")
PDF_DOSYA_ADI = "bulten.pdf"
MASTER_BILANCO_DOSYASI = "master_bilanco_bist_tum.csv"

# --- 3. BÜLTENİ OTOMATİK İNDİRME MOTORU (GÜÇLENDİRİLMİŞ) ---
def bulten_indir(hedef_dosya="bulten.pdf"):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Referer": "https://www.ziraatyatirim.com.tr/"
    }
    bugun = datetime.today()
    # Tatil günlerini ve hafta sonlarını rahatça aşabilmesi için geriye dönük 10 gün tarama
    for i in range(10):
        tarih = bugun - timedelta(days=i)
        tarih_str = tarih.strftime("%d%m%Y")
        url = f"https://www.ziraatyatirim.com.tr/documents/category/GG_{tarih_str}.pdf"
        try:
            res = requests.get(url, headers=headers, timeout=30, verify=False)
            if res.status_code == 200 and len(res.content) > 5000:
                with open(hedef_dosya, "wb") as f:
                    f.write(res.content)
                print(f"🎯 Güncel bülten indirildi: GG_{tarih_str}.pdf ({len(res.content)} bayt)")
                return True
            else:
                print(f"ℹ️ {tarih_str} denendi (Durum Kodu: {res.status_code})")
        except Exception as e:
            print(f"⚠️ {tarih_str} bağlantı denemesi: {e}")
            continue
    return False

def sayi_donustur(deger):
    if not deger or deger == "a.d.": return 0.0
    temiz = str(deger).replace("%", "").replace(".", "").replace(",", ".").strip()
    try: return float(temiz)
    except: return 0.0

# --- 4. PIOTROSKI SKORLARINI MASTER DOSYADAN OKUMA ---
piotroski_sozluk = {}
if os.path.exists(MASTER_BILANCO_DOSYASI):
    try:
        df_m = pd.read_csv(MASTER_BILANCO_DOSYASI, sep=None, engine='python')
        df_m.columns = [str(c).strip().upper() for c in df_m.columns]
        h_col = next((c for c in df_m.columns if "HISSE" in c), None)
        p_col = next((c for c in df_m.columns if "PIOT" in c), None)
        if h_col and p_col:
            for _, r in df_m.iterrows():
                if pd.notna(r[h_col]) and pd.notna(r[p_col]):
                    piotroski_sozluk[str(r[h_col]).strip().upper()] = r[p_col]
            print(f"✅ {len(piotroski_sozluk)} hisse için Piotroski skoru yüklendi.")
    except Exception as e:
        print(f"⚠️ Master bilanço okuma hatası: {e}")

# --- 5. ZİRAAT BÜLTENİ SEKTÖRLERİYLE KAZIMA & PİKSEL MOTORU ---
print("🚀 BİST TÜM Çarpan Motoru Başlatıldı...")
if not bulten_indir(PDF_DOSYA_ADI):
    raise FileNotFoundError("❌ Ziraat bülteni indirilemedi, işlem durduruldu.")

ZIRAAT_SEKTORLER = [
    "GİRİŞİM SERMAYESİ YATIRIM ORTAKLIKLARI", "MESLEKİ, BİLİMSEL VE TEKNİK FAALİYETLER", 
    "PETROL & PETRO-KİMYA & GAZ", "TEKSTİL & TEKSTİL YAN SANAYİ", 
    "KÜÇÜK VE ORTA ÖLÇEKLİ BANKALAR", "GAYRİMENKUL YATIRIM ORTAKLIKLARI",
    "GAYRİMENKUL FAALİYETLERİ", "TURİZM, OTEL, EĞLENCE", "ELEKTRİK MALZEMELERİ",
    "BİLGİSAYAR & YAZILIM", "TELEKOM TEKNOLOJİLERİ", "OTOMOTİV YAN SANAYİ",
    "KİMYASAL MADDELER", "YAPI MALZEMELERİ", "DAYANIKLI TÜKETİM", 
    "YATIRIM ORTAKLIKLARI", "BÜYÜK BANKALAR", "MENKUL DEĞERLER", "CAM & SERAMİK",
    "DEMİR & ÇELİK", "DİĞER İMALAT", "İLAÇ & SAĞLIK", "ENERJİ İMALAT",
    "VARLIK YÖNETİMİ", "FAKTORING", "PERAKENDE", "MADENCİLİK", "OTOMOTİV", 
    "SİGORTA", "LEASING", "HOLDİNG", "HOLDING", "ÇİMENTO", "İNŞAAT", "MAKİNE", 
    "İÇECEK", "MEDYA", "TARIM", "ENERJİ", "GIDA", "SPOR", "TELEKOM", "BANKALAR"
]

def metin_temizle(m):
    return m.replace("İ","I").replace("Ğ","G").replace("Ü","U").replace("Ş","S").replace("Ö","O").replace("Ç","C").strip()

TEMIZ_SEKTORLER = [metin_temizle(s) for s in ZIRAAT_SEKTORLER]

hisse_verileri = []
aktif_pazar = "YILDIZ_ANA"
aktif_sektor = "GENEL"

with pdfplumber.open(PDF_DOSYA_ADI) as pdf:
    for page in pdf.pages:
        words = page.extract_words(x_tolerance=2, y_tolerance=3)
        if not words: continue
        satirlar_dict = {}
        for w in words:
            y = round(w['top'] / 4) * 4 
            if y not in satirlar_dict: satirlar_dict[y] = []
            satirlar_dict[y].append(w)
            
        for y in sorted(satirlar_dict.keys()):
            satir = " ".join([w['text'] for w in sorted(satirlar_dict[y], key=lambda x: x['x0'])])
            satir_upper = satir.upper().strip()
            satir_upper_temiz = metin_temizle(satir_upper)

            # Pazar Filtreleri
            if any(p in satir_upper_temiz for p in ["YAKIN IZLEME", "ALT PAZAR", "PIYASA ONCESI"]):
                aktif_pazar = "VETO"
                continue

            parcalar = satir.split()

            # Sektör Başlığı Kontrolü
            bulunan_sektor = next((orijinal for temiz, orijinal in zip(TEMIZ_SEKTORLER, ZIRAAT_SEKTORLER) if satir_upper_temiz.startswith(temiz)), None)
            if bulunan_sektor and len(satir_upper) < 45:
                aktif_sektor = bulunan_sektor
                aktif_pazar = "YILDIZ_ANA"
                continue

            # Hisse Kodu Tespiti
            kod = ""
            if len(parcalar) >= 10:
                for p in parcalar:
                    if len(p) in [4, 5] and p.isalpha() and p == p.upper():
                        kod = p
                        break
                        
            if kod and aktif_pazar != "VETO":
                try:
                    offset = 1 if parcalar[-1].isalpha() else 0
                    hisse_verileri.append({
                        "Hisse": kod,
                        "Sektor": aktif_sektor,
                        "Halka_Aciklik": sayi_donustur([p for p in parcalar if "%" in p][1]) if len([p for p in parcalar if "%" in p]) >= 2 else 0.0,
                        "FK": sayi_donustur(parcalar[-5 - offset]),
                        "PDDD": sayi_donustur(parcalar[-4 - offset]),
                        "FD_FAVOK": sayi_donustur(parcalar[-3 - offset]),
                        "PDS": sayi_donustur(parcalar[-2 - offset]),
                        "NetBorc_FAVOK": sayi_donustur(parcalar[-1 - offset])
                    })
                except Exception:
                    pass

# --- 6. DİNAMİK SEKTÖR MEDYANLARI (HESAPLANMIŞ MEDYAN) ---
sektor_havuzu = {}
for h in hisse_verileri:
    s = h["Sektor"]
    if s not in sektor_havuzu:
        sektor_havuzu[s] = {"fk": [], "pddd": [], "fd_favok": [], "pds": [], "nbf": []}
    if h["FK"] > 0: sektor_havuzu[s]["fk"].append(h["FK"])
    if h["PDDD"] > 0: sektor_havuzu[s]["pddd"].append(h["PDDD"])
    if h["FD_FAVOK"] > 0: sektor_havuzu[s]["fd_favok"].append(h["FD_FAVOK"])
    if h["PDS"] > 0: sektor_havuzu[s]["pds"].append(h["PDS"])
    if h["NetBorc_FAVOK"] > 0: sektor_havuzu[s]["nbf"].append(h["NetBorc_FAVOK"])

sektor_medyanlari = {}
for s, vals in sektor_havuzu.items():
    sektor_medyanlari[s] = {
        "m_fk": statistics.median(vals["fk"]) if vals["fk"] else 12.0,
        "m_pddd": statistics.median(vals["pddd"]) if vals["pddd"] else 1.5,
        "m_fd_favok": statistics.median(vals["fd_favok"]) if vals["fd_favok"] else 8.0,
        "m_pds": statistics.median(vals["pds"]) if vals["pds"] else 1.0,
        "m_nbf": statistics.median(vals["nbf"]) if vals["nbf"] else 2.0
    }

# --- 7. DEĞERLEME MOTORU & PROSPEKTİF F/K ---
guncellenecek_paketler = []
for h in hisse_verileri:
    sektor = h["Sektor"]
    fk, pddd = h["FK"], h["PDDD"]
    sec_fk = sektor_medyanlari[sektor]["m_fk"]
    sec_pddd = sektor_medyanlari[sektor]["m_pddd"]

    if "BANKA" in sektor or "GYO" in sektor or "GAYRİMENKUL" in sektor:
        oran = (pddd / sec_pddd) if (pddd > 0 and sec_pddd > 0) else 1.0
    else:
        bilesenler = []
        if fk > 0 and sec_fk > 0: bilesenler.append(fk / sec_fk)
        if pddd > 0 and sec_pddd > 0: bilesenler.append(pddd / sec_pddd)
        oran = (sum(bilesenler) / len(bilesenler)) if bilesenler else 1.0

    if oran <= 0.85: h["Durum"] = "🟢 İskontolu"
    elif oran <= 1.15: h["Durum"] = "🟡 Dengeli"
    else: h["Durum"] = "🔴 Pahalı"

    f_skor = piotroski_sozluk.get(h["Hisse"], None)
    try:
        if f_skor is not None:
            g = (float(f_skor) - 4.5) * 0.06
            h["Prospektif_FK"] = max(round(fk / (1.0 + g), 2), 0.5) if fk > 0 else 0.0
        else:
            h["Prospektif_FK"] = fk
    except Exception:
        h["Prospektif_FK"] = fk

    h["Sektor_FK"] = sec_fk
    h["Sektor_PDDD"] = sec_pddd
    h["Sektor_FDFAVOK"] = sektor_medyanlari[sektor]["m_fd_favok"]
    h["Sektor_PDS"] = sektor_medyanlari[sektor]["m_pds"]
    h["Sektor_NBF"] = sektor_medyanlari[sektor]["m_nbf"]

    guncellenecek_paketler.append(h)

guncellenecek_paketler.sort(key=lambda x: x["Hisse"])

# --- 8. POWER BI İÇİN CSV ÇIKTISI (GITHUB REPOSU) ---
csv_dosya = "ziraat_carpanlar.csv"
csv_basliklar = [
    "Hisse", "Sektor", "Halka_Aciklik", "FK", "PDDD", "FD_FAVOK", "PDS", "NetBorc_FAVOK", 
    "Prospektif_FK", "Durum", "Sektor_FK", "Sektor_PDDD", "Sektor_FDFAVOK", "Sektor_PDS", "Sektor_NBF"
]
try:
    with open(csv_dosya, mode="w", encoding="utf-8-sig", newline="") as dosya:
        yazici = csv.DictWriter(dosya, fieldnames=csv_basliklar, extrasaction='ignore')
        yazici.writeheader()
        yazici.writerows(guncellenecek_paketler)
    print(f"📁 {csv_dosya} dosyası başarıyla üretildi.")
except Exception as e:
    print(f"⚠️ CSV hatası: {e}")

# --- 9. MAKE.COM WEBHOOK İLE EXCEL AKTARIMI ---
matris_verisi = []
for h in guncellenecek_paketler:
    matris_verisi.append([
        h["Hisse"], h["Sektor"], h["Halka_Aciklik"], h["FK"], h["PDDD"], 
        h["FD_FAVOK"], h["PDS"], h["NetBorc_FAVOK"], h["Prospektif_FK"], h["Durum"],
        h["Sektor_FK"], h["Sektor_PDDD"], h["Sektor_FDFAVOK"], h["Sektor_PDS"], h["Sektor_NBF"]
    ])

dinamik_aralik = f"A2:O{len(matris_verisi) + 1}"
payload = {
    "islem_turu": "Haftalik_Carpan_Guncelleme",
    "range_adresi": dinamik_aralik,
    "hazir_body_zb": json.dumps({"values": matris_verisi})
}
try:
    res = requests.post(MAKE_WEBHOOK_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
    print(f"🎉 15 Sütunluk Zengin Veri Excel'e Aktarıldı! (Durum Kodu: {res.status_code})")
except Exception as e:
    print(f"⚠️ Make.com hatası: {e}")

# --- 10. TELEGRAM RAPORU BİLDİRİMİ ---
iskontolular = [x for x in guncellenecek_paketler if x["Durum"] == "🟢 İskontolu" and x["FK"] > 0]
top_10 = sorted(iskontolular, key=lambda x: x["FK"])[:10]

mesaj = f"📊 *BİST TÜM DEĞERLEME RAPORU*\n🔎 Analiz Edilen: `{len(guncellenecek_paketler)}` Hisse\n\n🏆 *Top 10 İskonto:*\n"
for h in top_10:
    mesaj += f"• *{h['Hisse']}* ({h['Sektor']}): F/K: `{h['FK']}` | PD/DD: `{h['PDDD']}`\n"
try:
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
        json={"chat_id": TELEGRAM_CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}, 
        timeout=15
    )
except Exception:
    pass
