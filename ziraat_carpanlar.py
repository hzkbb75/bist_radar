# ==============================================================================
# HAFTALIK ZİRAAT BİST TÜM PİYASA ÇARPANLARI & SEKTÖREL MEDYAN MOTORU
# ==============================================================================
import os
import json
import requests
import statistics
import csv
from datetime import datetime, timedelta

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

# --- 3. BÜLTENİ OTOMATİK İNDİRME ---
def bulten_indir(hedef_dosya="bulten.pdf"):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://www.ziraatyatirim.com.tr/"
    }
    bugun = datetime.today()
    for i in range(7):
        tarih = bugun - timedelta(days=i)
        tarih_str = tarih.strftime("%d%m%Y")
        url = f"https://www.ziraatyatirim.com.tr/documents/category/GG_{tarih_str}.pdf"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200 and len(res.content) > 5000:
                with open(hedef_dosya, "wb") as f:
                    f.write(res.content)
                print(f"🎯 Güncel bülten indirildi: GG_{tarih_str}.pdf")
                return True
        except Exception:
            continue
    return False

def sayi_donustur(deger):
    if not deger or deger == "a.d.": return 0.0
    temiz = str(deger).replace("%", "").replace(".", "").replace(",", ".").strip()
    try: return float(temiz)
    except: return 0.0

# --- 4. MASTER BİLANÇO ÜZERİNDEN SEKTÖR VE PİOTROSKİ SÖZLÜKLERİNİ KURMA ---
sektor_sozluk = {}
piotroski_sozluk = {}

if os.path.exists(MASTER_BILANCO_DOSYASI):
    # Ayırıcıyı (, veya ;) otomatik tespit et ve Türkçe karakterleri normalize et
    try:
        df_m = pd.read_csv(MASTER_BILANCO_DOSYASI, sep=None, engine='python', encoding='utf-8-sig')
    except Exception:
        df_m = pd.read_csv(MASTER_BILANCO_DOSYASI, sep=';', encoding='latin1')

    # Kolon isimlerindeki boşlukları sil ve büyük harfe çevir
    df_m.columns = [str(c).strip().upper().replace("İ", "I") for c in df_m.columns]
    
    hisse_kol = next((c for c in df_m.columns if "HISSE" in c or "KOD" in c), None)
    sektor_kol = next((c for c in df_m.columns if "SEKT" in c), None)
    piot_kol = next((c for c in df_m.columns if "PIOT" in c), None)
    
    if hisse_kol and sektor_kol:
        for _, r in df_m.iterrows():
            kod = str(r[hisse_kol]).strip().upper()
            if kod and pd.notna(r[sektor_kol]):
                sektor_sozluk[kod] = str(r[sektor_kol]).strip().upper()
            if piot_kol and pd.notna(r[piot_kol]):
                piotroski_sozluk[kod] = r[piot_kol]
        print(f"✅ Sektörler CSV'den başarıyla yüklendi: {len(sektor_sozluk)} hisse")
    else:
        print(f"⚠️ Sütunlar eşleşmedi! Mevcut kolonlar: {list(df_m.columns)}")
else:
    print(f"⚠️ {MASTER_BILANCO_DOSYASI} bulunamadı!")

# --- 5. KOORDİNAT BAZLI (PİKSEL) PARÇALAMA & VETO MOTORU ---
print("🚀 BİST TÜM PDF Çarpan Çekme Motoru Başlatıldı...")
if not bulten_indir(PDF_DOSYA_ADI):
    raise FileNotFoundError("❌ Ziraat bülteni indirilemedi, işlem durduruldu.")

hisse_verileri = []
aktif_pazar = "YILDIZ_ANA"

with pdfplumber.open(PDF_DOSYA_ADI) as pdf:
    for page in pdf.pages:
        words = page.extract_words(x_tolerance=2, y_tolerance=3)
        if not words: continue
        
        satirlar_dict = {}
        for w in words:
            y = round(w['top'] / 4) * 4 
            if y not in satirlar_dict:
                satirlar_dict[y] = []
            satirlar_dict[y].append(w)
            
        for y in sorted(satirlar_dict.keys()):
            sirali_kelimeler = sorted(satirlar_dict[y], key=lambda x: x['x0'])
            satir = " ".join([w['text'] for w in sirali_kelimeler])
            satir_upper = satir.upper().strip()
            
            # Pazar Filtreleri
            if any(p in satir_upper for p in ["YAKIN İZLEME PAZARI", "ALT PAZAR", "PİYASA ÖNCESİ", "YATIRIM ORTAKLIKLARI"]):
                aktif_pazar = "VETO"
                continue

            parcalar = satir.split()
            if 0 < len(parcalar) <= 4 and not any(c.isdigit() for c in satir):
                aktif_pazar = "YILDIZ_ANA"
                continue

            kod = ""
            if len(parcalar) >= 10:
                for p in parcalar:
                    if len(p) in [4, 5] and p.isalpha() and p == p.upper():
                        kod = p
                        break
                        
            if kod and aktif_pazar != "VETO":
                try:
                    offset = 1 if parcalar[-1].isalpha() else 0
                    
                    # Sektörü doğrudan master bilançodan çek
                    sektor = sektor_sozluk.get(kod, "DİĞER")
                    
                    net_borc_favok = sayi_donustur(parcalar[-1 - offset])
                    pd_s = sayi_donustur(parcalar[-2 - offset])
                    fd_favok = sayi_donustur(parcalar[-3 - offset])
                    pddd = sayi_donustur(parcalar[-4 - offset])
                    fk = sayi_donustur(parcalar[-5 - offset])
                    
                    yuzdeler = [p for p in parcalar if "%" in p]
                    halka_aciklik = sayi_donustur(yuzdeler[1]) if len(yuzdeler) >= 2 else 0.0
                    
                    hisse_verileri.append({
                        "Hisse": kod,
                        "Sektor": sektor,
                        "Halka_Aciklik": halka_aciklik,
                        "FK": fk,
                        "PDDD": pddd,
                        "FD_FAVOK": fd_favok,
                        "PDS": pd_s,
                        "NetBorc_FAVOK": net_borc_favok
                    })
                except:
                    pass

# --- 6. CSV SEKTÖRLERİNE GÖRE DİNAMİK MEDYAN HESABI ---
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

    f_skor = piotroski_sozluk.get(h["Hisse"], "-")
    try:
        g = (float(f_skor) - 4.5) * 0.06
        h["Prospektif_FK"] = max(round(fk / (1.0 + g), 2), 0.5) if fk > 0 else 0.0
    except:
        h["Prospektif_FK"] = fk

    h["Sektor_FK"] = sec_fk
    h["Sektor_PDDD"] = sec_pddd
    h["Sektor_FDFAVOK"] = sektor_medyanlari[sektor]["m_fd_favok"]
    h["Sektor_PDS"] = sektor_medyanlari[sektor]["m_pds"]
    h["Sektor_NBF"] = sektor_medyanlari[sektor]["m_nbf"]

    guncellenecek_paketler.append(h)

guncellenecek_paketler.sort(key=lambda x: x["Hisse"])

# --- 8. POWER BI İÇİN CSV ÇIKTISI (GITHUB) ---
csv_dosya = "ziraat_carpanlar.csv"
csv_basliklar = ["Hisse", "Sektor", "Halka_Aciklik", "FK", "PDDD", "FD_FAVOK", "PDS", "NetBorc_FAVOK", 
                 "Prospektif_FK", "Durum", "Sektor_FK", "Sektor_PDDD", "Sektor_FDFAVOK", "Sektor_PDS", "Sektor_NBF"]

try:
    with open(csv_dosya, mode="w", encoding="utf-8-sig", newline="") as dosya:
        yazici = csv.DictWriter(dosya, fieldnames=csv_basliklar, extrasaction='ignore')
        yazici.writeheader()
        yazici.writerows(guncellenecek_paketler)
except Exception as e:
    print(f"⚠️ CSV hatası: {e}")

# --- 9. MAKE.COM WEBHOOK İLE EXCEL'E AKTARIM ---
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
    requests.post(MAKE_WEBHOOK_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
    print("🎉 15 Sütunluk Zengin Veri Excel'e Aktarıldı!")
except Exception as e:
    print(f"⚠️ Make.com hatası: {e}")

# --- 10. TELEGRAM RAPORU ---
iskontolular = [x for x in guncellenecek_paketler if x["Durum"] == "🟢 İskontolu" and x["FK"] > 0]
top_10 = sorted(iskontolular, key=lambda x: x["FK"])[:10]

mesaj = f"📊 *BİST TÜM DEĞERLEME RAPORU*\n🔎 Analiz Edilen: `{len(guncellenecek_paketler)}` Hisse\n\n🏆 *Top 10 İskonto:*\n"
for h in top_10:
    mesaj += f"• *{h['Hisse']}* ({h['Sektor']}): F/K: `{h['FK']}` | PD/DD: `{h['PDDD']}`\n"

try:
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                  json={"chat_id": TELEGRAM_CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}, timeout=15)
except Exception:
    pass
