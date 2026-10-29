# ==============================================================================
# HAFTALIK ZİRAAT & BİST ANALİTİK MOTORU (OKAN DNA + SERKAN ÜNAL SİSTEMİ)
# ==============================================================================
import os
import json
import requests
import statistics
import csv
import urllib3
from datetime import datetime, timedelta

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
JSON_SEKTOR_DOSYASI = "bist_sektorler.json"

# --- 3. BÜLTENİ OTOMATİK İNDİRME MOTORU ---
def bulten_indir(hedef_dosya="bulten.pdf"):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Referer": "https://www.ziraatyatirim.com.tr/"
    }
    bugun = datetime.today()
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
        except Exception:
            continue
    return False

def sayi_donustur(deger):
    if not deger or deger == "a.d.": return 0.0
    temiz = str(deger).replace("%", "").replace(".", "").replace(",", ".").strip()
    try: return float(temiz)
    except: return 0.0

# --- 4. MASTER BİLANÇO DOSYASINI OKUMA ---
bilanco_sozluk = {}
if os.path.exists(MASTER_BILANCO_DOSYASI):
    try:
        df_m = pd.read_csv(MASTER_BILANCO_DOSYASI, sep=None, engine='python')
        df_m.columns = [str(c).strip().upper() for c in df_m.columns]
        h_col = next((c for c in df_m.columns if "HISSE" in c), "HISSE")
        
        for _, r in df_m.iterrows():
            kod = str(r[h_col]).strip().upper()
            if kod and kod != "NAN":
                bilanco_sozluk[kod] = {
                    "PIOTROSKI": sayi_donustur(r.get("PIOTROSKI_SKOR", 0)),
                    "ALTMAN_Z": sayi_donustur(r.get("ALTMAN_Z", 0)),
                    "ROA": sayi_donustur(r.get("ROA", 0)),
                    "BRUT_MARJ": sayi_donustur(r.get("BRUT_MARJ", 0)),
                    "ROE": sayi_donustur(r.get("ROE", 0)),
                    "NET_KAR_MARJI": sayi_donustur(r.get("NET_KAR_MARJI", 0)),
                    "AKTIF_DEVIR": sayi_donustur(r.get("AKTIF_DEVIR", 0)),
                    "KALDIRAC": sayi_donustur(r.get("KALDIRAC", 0)),
                    "TEMEL_SKOR": sayi_donustur(r.get("TEMEL_SKOR", 0)),
                    "ILISKILI_TARAF": str(r.get("ILISKILI_TARAF", "Temiz")).strip()
                }
        print(f"✅ {len(bilanco_sozluk)} hisse için master bilanço metrikleri yüklendi.")
    except Exception as e:
        print(f"⚠️ Master bilanço okuma hatası: {e}")

# --- 5. BİST SEKTÖR SÖZLÜĞÜNÜ (JSON) YÜKLEME ---
sektor_sozluk = {}
if os.path.exists(JSON_SEKTOR_DOSYASI):
    try:
        with open(JSON_SEKTOR_DOSYASI, "r", encoding="utf-8") as f:
            sektor_sozluk = json.load(f)
        print(f"✅ {len(sektor_sozluk)} hisselik BİST sektör sözlüğü başarıyla yüklendi.")
    except Exception as e:
        print(f"⚠️ Sektör JSON dosyası okuma hatası: {e}")

# --- 6. KOORDİNAT BAZLI PDF KAZIMA MOTORU ---
print("🚀 BİST TÜM Çarpan Motoru Başlatıldı...")
if not bulten_indir(PDF_DOSYA_ADI):
    raise FileNotFoundError("❌ Ziraat bülteni indirilemedi, işlem durduruldu.")

def metin_temizle(m):
    return m.replace("İ","I").replace("Ğ","G").replace("Ü","U").replace("Ş","S").replace("Ö","O").replace("Ç","C").strip()

hisse_verileri = []
aktif_pazar = "YILDIZ_ANA"

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

            if any(p in satir_upper_temiz for p in ["YAKIN IZLEME", "ALT PAZAR", "PIYASA ONCESI"]):
                aktif_pazar = "VETO"
                continue

            parcalar = satir.split()
            if 0 < len(parcalar) <= 4 and not any(c.isdigit() for c in satir):
                if not any(p in satir_upper_temiz for p in ["YAKIN IZLEME", "ALT PAZAR", "PIYASA ONCESI"]):
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
                    sektor = sektor_sozluk.get(kod, "DİĞER")
                    
                    hisse_verileri.append({
                        "Hisse": kod,
                        "Sektor": sektor,
                        "Halka_Aciklik": sayi_donustur([p for p in parcalar if "%" in p][1]) if len([p for p in parcalar if "%" in p]) >= 2 else 0.0,
                        "FK": sayi_donustur(parcalar[-5 - offset]),
                        "PDDD": sayi_donustur(parcalar[-4 - offset]),
                        "FD_FAVOK": sayi_donustur(parcalar[-3 - offset]),
                        "PDS": sayi_donustur(parcalar[-2 - offset]),
                        "NetBorc_FAVOK": sayi_donustur(parcalar[-1 - offset])
                    })
                except Exception:
                    pass

# --- 7. DİNAMİK SEKTÖR MEDYANLARI ---
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

# --- 8. OKAN DNA & SERKAN ÜNAL MATEMATİKSEL KARAR MOTORU ---
FINANS_SEKTORLERI = ["BANKA", "SİGORTA", "FAKTORİNG", "LEASİNG", "ARACI KURUM & FİNANS", "YATIRIM ORTAKLIĞI", "GYO"]
guncellenecek_paketler = []

for h in hisse_verileri:
    kod = h["Hisse"]
    sektor = h["Sektor"]
    fk, pddd, nbf = h["FK"], h["PDDD"], h["NetBorc_FAVOK"]
    sec_fk = sektor_medyanlari[sektor]["m_fk"]
    sec_pddd = sektor_medyanlari[sektor]["m_pddd"]
    
    bil = bilanco_sozluk.get(kod, {
        "PIOTROSKI": 5.0, "ALTMAN_Z": 2.5, "ROA": 0.05, "BRUT_MARJ": 0.20,
        "ROE": 0.15, "NET_KAR_MARJI": 0.05, "AKTIF_DEVIR": 0.5, "KALDIRAC": 0.5,
        "TEMEL_SKOR": 50.0, "ILISKILI_TARAF": "Temiz"
    })
    
    # 1. SERKAN ÜNAL KIRMIZI ÇİZGİLER (VETO FİLTRESİ)
    is_veto = False
    veto_nedeni = "Yok"
    
    if "RİSKLİ" in bil["ILISKILI_TARAF"].upper() or "RISKLI" in bil["ILISKILI_TARAF"].upper():
        is_veto = True
        veto_nedeni = "İlişkili Taraf İşlemleri Güvensiz"
    elif sektor not in FINANS_SEKTORLERI and bil["ALTMAN_Z"] > 0 and bil["ALTMAN_Z"] < 1.1:
        is_veto = True
        veto_nedeni = "Altman-Z İflas / Temerrüt Riski"
    elif sektor not in FINANS_SEKTORLERI and nbf > 5.0:
        is_veto = True
        veto_nedeni = "Aşırı Kaldıraç (Net Borç/FAVÖK > 5)"

    # 2. OKAN DNA: SAĞLAMLIK SKORU (0 - 100)
    # A) Borç Puanı (0 - 40)
    if sektor in FINANS_SEKTORLERI:
        p_borc = 35.0
    else:
        if nbf <= 0: p_borc = 40.0
        else: p_borc = max(0.0, min(40.0, 40.0 - (nbf * 7.0)))
    
    # B) Piotroski Skor Gücü (0 - 35)
    p_piot = min(35.0, (bil["PIOTROSKI"] / 9.0) * 35.0)
    
    # C) Altman Z Temel Güven (0 - 25)
    if sektor in FINANS_SEKTORLERI:
        p_altman = 20.0
    else:
        if bil["ALTMAN_Z"] >= 3.0: p_altman = 25.0
        elif bil["ALTMAN_Z"] >= 1.8: p_altman = 15.0 + ((bil["ALTMAN_Z"] - 1.8) / 1.2) * 10.0
        else: p_altman = max(0.0, (bil["ALTMAN_Z"] / 1.8) * 10.0)
        
    saglamlik_skor = round(p_borc + p_piot + p_altman, 1)

    # 3. OKAN DNA: GİDİŞAT VE KÂRLILIK MOMENTUMU (0 - 100)
    # A) ROE Verimliliği (0 - 40)
    roe_val = max(0.0, bil["ROE"])
    p_roe = min(40.0, (roe_val / 0.35) * 40.0)
    
    # B) Net Kâr Marjı (0 - 30)
    nkm_val = max(0.0, bil["NET_KAR_MARJI"])
    p_nkm = min(30.0, (nkm_val / 0.20) * 30.0)
    
    # C) Aktif Devir Hızı / Varlık Dönüşü (0 - 30)
    ad_val = max(0.0, bil["AKTIF_DEVIR"])
    p_ad = min(30.0, (ad_val / 1.2) * 30.0)
    
    gidisat_skor = round(p_roe + p_nkm + p_ad, 1)

    # 4. DEĞERLEME & İSKONTO SKORU (0 - 100)
    if sektor in FINANS_SEKTORLERI:
        r_oran = (pddd / sec_pddd) if (pddd > 0 and sec_pddd > 0) else 1.0
    else:
        bilesenler = []
        if fk > 0 and sec_fk > 0: bilesenler.append(fk / sec_fk)
        if pddd > 0 and sec_pddd > 0: bilesenler.append(pddd / sec_pddd)
        r_oran = (sum(bilesenler) / len(bilesenler)) if bilesenler else 1.0

    if r_oran <= 0.65: degerleme_skor = 100.0
    elif r_oran <= 0.85: degerleme_skor = 85.0
    elif r_oran <= 1.00: degerleme_skor = 65.0
    elif r_oran <= 1.20: degerleme_skor = 40.0
    elif r_oran <= 1.40: degerleme_skor = 20.0
    else: degerleme_skor = 5.0

    # 5. NİHAİ OSE SKORU & SERKAN ÜNAL PORTFÖY PAYI
    ham_ose = (0.30 * saglamlik_skor) + (0.35 * gidisat_skor) + (0.35 * degerleme_skor)
    
    if is_veto:
        ose_skor = round(min(ham_ose, 35.0), 1)
        durum = "🔴 Pahalı"
        veto_durum = "⛔ VETO"
        portfoy_statusu = "⛔ Yasaklı / Veto"
        max_agirlik = 0.0
    else:
        ose_skor = round(ham_ose, 1)
        veto_durum = "✅ GEÇTİ"
        if r_oran <= 0.85: durum = "🟢 İskontolu"
        elif r_oran <= 1.15: durum = "🟡 Dengeli"
        else: durum = "🔴 Pahalı"

        if ose_skor >= 80:
            portfoy_statusu = "🏆 Çekirdek / Hendekli"
            max_agirlik = 10.0
        elif ose_skor >= 65:
            portfoy_statusu = "🛡️ Korunaklı Büyüme"
            max_agirlik = 6.0
        elif ose_skor >= 50:
            portfoy_statusu = "⚖️ Fırsat / Döngüsel"
            max_agirlik = 3.0
        else:
            portfoy_statusu = "👀 Takip / Zayıf"
            max_agirlik = 1.0

    # Serkan Hoca Prospektif F/K
    f_skor = bil["PIOTROSKI"]
    g = (float(f_skor) - 4.5) * 0.06
    prospektif_fk = max(round(fk / (1.0 + g), 2), 0.5) if fk > 0 else 0.0

    # Pakete ekle
    h.update({
        "Durum": durum,
        "Veto_Durum": veto_durum,
        "Veto_Nedeni": veto_nedeni,
        "Saglamlik_Skor": saglamlik_skor,
        "Gidisat_Skor": gidisat_skor,
        "Degerleme_Skor": degerleme_skor,
        "OSE_Skor": ose_skor,
        "Portfoy_Statusu": portfoy_statusu,
        "Max_Agirlik": max_agirlik,
        "Prospektif_FK": prospektif_fk,
        "Sektor_FK": sec_fk,
        "Sektor_PDDD": sec_pddd,
        "Sektor_FDFAVOK": sektor_medyanlari[sektor]["m_fd_favok"],
        "Piotroski_Skor": bil["PIOTROSKI"],
        "Altman_Z": bil["ALTMAN_Z"],
        "ROE": bil["ROE"],
        "Net_Kar_Marji": bil["NET_KAR_MARJI"],
        "Aktif_Devir": bil["AKTIF_DEVIR"],
        "Kaldirac": bil["KALDIRAC"],
        "Temel_Skor": bil["TEMEL_SKOR"],
        "Iliskili_Taraf": bil["ILISKILI_TARAF"]
    })
    guncellenecek_paketler.append(h)

guncellenecek_paketler.sort(key=lambda x: x["OSE_Skor"], reverse=True)

# --- 9. POWER BI İÇİN CSV ÇIKTISI (GITHUB REPOSU) ---
csv_dosya = "ziraat_carpanlar.csv"
csv_basliklar = [
    "Hisse", "Sektor", "Durum", "Veto_Durum", "Veto_Nedeni",
    "OSE_Skor", "Saglamlik_Skor", "Gidisat_Skor", "Degerleme_Skor",
    "Portfoy_Statusu", "Max_Agirlik",
    "FK", "Prospektif_FK", "PDDD", "FD_FAVOK", "PDS", "NetBorc_FAVOK", "Halka_Aciklik",
    "Sektor_FK", "Sektor_PDDD", "Sektor_FDFAVOK",
    "Piotroski_Skor", "Altman_Z", "ROE", "Net_Kar_Marji", "Aktif_Devir", "Kaldirac", "Temel_Skor", "Iliskili_Taraf"
]

try:
    with open(csv_dosya, mode="w", encoding="utf-8-sig", newline="") as dosya:
        yazici = csv.DictWriter(dosya, fieldnames=csv_basliklar, extrasaction='ignore')
        yazici.writeheader()
        yazici.writerows(guncellenecek_paketler)
    print(f"📁 {csv_dosya} dosyası başarıyla üretildi ({len(guncellenecek_paketler)} hisse).")
except Exception as e:
    print(f"⚠️ CSV hatası: {e}")

# --- 10. MAKE.COM WEBHOOK İLE EXCEL AKTARIMI ---
matris_verisi = []
for h in sorted(guncellenecek_paketler, key=lambda x: x["Hisse"]):
    matris_verisi.append([
        h["Hisse"], h["Sektor"], h["Halka_Aciklik"], h["FK"], h["PDDD"], 
        h["FD_FAVOK"], h["PDS"], h["NetBorc_FAVOK"], h["Prospektif_FK"], h["Durum"],
        h["Sektor_FK"], h["Sektor_PDDD"], h["Sektor_FDFAVOK"], h["OSE_Skor"], h["Portfoy_Statusu"]
    ])

dinamik_aralik = f"A2:O{len(matris_verisi) + 1}"
payload = {
    "islem_turu": "Haftalik_Carpan_Guncelleme",
    "range_adresi": dinamik_aralik,
    "hazir_body_zb": json.dumps({"values": matris_verisi})
}
try:
    requests.post(MAKE_WEBHOOK_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
except Exception:
    pass

# --- 11. TELEGRAM RAPORU BİLDİRİMİ ---
gecenler = [x for x in guncellenecek_paketler if x["Veto_Durum"] == "✅ GEÇTİ"]
top_5 = gecenler[:5]

mesaj = f"🧠 *OKAN & SERKAN ANALİTİK MOTORU RAPORU*\n"
mesaj += f"📊 Toplam Taranan: `{len(guncellenecek_paketler)}` | Onaylanan: `{len(gecenler)}` Hisse\n\n"
mesaj += f"🏆 *Lider Çekirdek Hisseler (Top 5 OSE Skoru):*\n"
for h in top_5:
    mesaj += f"• *{h['Hisse']}* ({h['Sektor']}): OSE: `{h['OSE_Skor']}` | Durum: `{h['Durum']}` | Portföy Payı: `%{h['Max_Agirlik']}`\n"

try:
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
        json={"chat_id": TELEGRAM_CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}, 
        timeout=15
    )
except Exception:
    pass
