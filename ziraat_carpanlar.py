# ==============================================================================
# HAFTALIK ZİRAAT BİST TÜM PİYASA ÇARPANLARI & OTOMATİK ELEME MOTORU
# ==============================================================================
import os
import json
import requests
import statistics
from datetime import datetime, timedelta

# --- 1. KURULUM KONTROLÜ ---
try:
    import pdfplumber
except ImportError:
    import subprocess
    subprocess.check_call(["pip", "install", "pdfplumber"])
    import pdfplumber

# --- 2. AYARLAR & ENTEGRASYONLAR ---
MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/wa77gag3g9hqdubo8tn401h7yssknf7c"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8897693829:AAEHKHoRKSN-h3RRRU60bDCq3wcuLstivI4")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "932085366")
PDF_DOSYA_ADI = "bulten.pdf"

# --- 3. BÜLTENİ OTOMATİK İNDİRME ---
def bulten_indir(hedef_dosya="bulten.pdf"):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
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
                print(f"🎯 Güncel bülten indirildi: GG_{tarih_str}.pdf ({len(res.content)//1024} KB)")
                return True
        except Exception:
            continue
    return False

def sayi_donustur(deger):
    if not deger or deger == "a.d.": return 0.0
    temiz = str(deger).replace("%", "").replace(".", "").replace(",", ".").strip()
    try: return float(temiz)
    except: return 0.0

# --- 4. DİNAMİK PARÇALAMA & VETO MOTORU ---
print("🚀 BİST TÜM Motoru Başlatıldı...")
if not bulten_indir(PDF_DOSYA_ADI):
    raise FileNotFoundError("❌ Ziraat bülteni indirilemedi, işlem durduruldu.")

hisse_verileri = []
aktif_pazar = "YILDIZ_ANA"
aktif_sektor = "GENEL"

with pdfplumber.open(PDF_DOSYA_ADI) as pdf:
    for page in pdf.pages:
        metin = page.extract_text()
        if not metin: continue
        
        for satir in metin.split("\n"):
            satir_upper = satir.upper().strip()
            
            # --- VETO 1: PAZAR KONTROLÜ ---
            if "YAKIN İZLEME PAZARI" in satir_upper:
                aktif_pazar = "YIP"
                continue
            elif "ALT PAZAR" in satir_upper:
                aktif_pazar = "ALT"
                continue
            elif "PİYASA ÖNCESİ" in satir_upper:
                aktif_pazar = "POIP"
                continue
            elif "YATIRIM ORTAKLIKLARI" in satir_upper: # GYO Hariç YO'lar elenir
                aktif_pazar = "YO"
                continue

            parcalar = satir.split()
            
            # --- SEKTÖR BAŞLIĞI TESPİTİ ---
            if 0 < len(parcalar) <= 4 and satir_upper == satir.strip() and not any(c.isdigit() for c in satir):
                if satir_upper not in ["BİST-TÜM", "BİST-100", "BİST-30", "NOTLAR"]:
                    aktif_sektor = satir_upper
                    # Eğer yeni sektör başlarken pazar YİP veya ALT ise, artık normal pazara dönmüş olabilir
                    # (Ziraat Bülten formatında pazar başlıkları sektörleri ezer)
                continue

            # --- HİSSE VERİSİ TESPİTİ ---
            if len(parcalar) >= 10:
                kod = parcalar[-1].upper()
                # Ticker validasyonu (4-5 harf, sadece alfabetik)
                if len(kod) in [4, 5] and kod.isalpha():
                    # Kırmızı Çizgi Veto: Alt Pazar, YİP ve YO'lar listeye asla giremez
                    if aktif_pazar in ["YIP", "ALT", "POIP", "YO"]:
                        continue 
                    
                    try:
                        # Ziraat Bülten PDF Sağdan Sola Sütun Dizilimi:
                        roa = sayi_donustur(parcalar[-8])
                        roe = sayi_donustur(parcalar[-7])
                        net_borc_favok = sayi_donustur(parcalar[-6])
                        pddd = sayi_donustur(parcalar[-5])
                        fd_favok = sayi_donustur(parcalar[-4])
                        pd_s = sayi_donustur(parcalar[-3])
                        fk = sayi_donustur(parcalar[-2]) # DİKKAT: Eski kodunuzda -6 idi, düzeltildi.
                        
                        hisse_verileri.append({
                            "Hisse": kod,
                            "Sektor": aktif_sektor,
                            "ROA": roa,
                            "ROE": roe,
                            "FK": fk,
                            "PDDD": pddd,
                            "FD_FAVOK": fd_favok,
                            "NetBorc_FAVOK": net_borc_favok,
                            "PDS": pd_s
                        })
                    except:
                        pass

# --- 5. DİNAMİK SEKTÖR MEDYANLARI (OTOMATİK HESAPLAMA) ---
sektor_havuzu = {}
for h in hisse_verileri:
    s = h["Sektor"]
    if s not in sektor_havuzu:
        sektor_havuzu[s] = {"fk_list": [], "pddd_list": []}
    if h["FK"] > 0: sektor_havuzu[s]["fk_list"].append(h["FK"])
    if h["PDDD"] > 0: sektor_havuzu[s]["pddd_list"].append(h["PDDD"])

sektor_medyanlari = {}
for s, vals in sektor_havuzu.items():
    m_fk = statistics.median(vals["fk_list"]) if vals["fk_list"] else 12.0
    m_pddd = statistics.median(vals["pddd_list"]) if vals["pddd_list"] else 1.5
    sektor_medyanlari[s] = {"fk": m_fk, "pddd": m_pddd}

# --- 6. DEĞERLEME & PIOTROSki ENTEGRASYONU ---
piotroski_sozluk = {}
if os.path.exists("master_bilanco_bist100.csv"):
    import pandas as pd
    df_m = pd.read_csv("master_bilanco_bist100.csv")
    for _, r in df_m.iterrows():
        piotroski_sozluk[r["Hisse"]] = r["Piotroski_Skor"]

guncellenecek_paketler = []
for h in hisse_verileri:
    hisse = h["Hisse"]
    sektor = h["Sektor"]
    fk = h["FK"]
    pddd = h["PDDD"]
    
    sec_fk = sektor_medyanlari[sektor]["fk"]
    sec_pddd = sektor_medyanlari[sektor]["pddd"]

    # Banka ve GYO'larda sadece PD/DD dikkate alınır
    if "BANKA" in sektor or "GAYRİMENKUL" in sektor:
        oran = (pddd / sec_pddd) if (pddd > 0 and sec_pddd > 0) else 1.0
    else:
        bilesenler = []
        if fk > 0 and sec_fk > 0: bilesenler.append(fk / sec_fk)
        if pddd > 0 and sec_pddd > 0: bilesenler.append(pddd / sec_pddd)
        oran = (sum(bilesenler) / len(bilesenler)) if bilesenler else 1.0

    if oran <= 0.85: durum = "🟢 İskontolu"
    elif oran <= 1.15: durum = "🟡 Dengeli"
    else: durum = "🔴 Pahalı"

    f_skor = piotroski_sozluk.get(hisse, "-")
    try:
        skor_num = float(f_skor)
        g = (skor_num - 4.5) * 0.06
        prospektif_fk = round(fk / (1.0 + g), 2) if fk > 0 else 0.0
        prospektif_fk = max(prospektif_fk, 0.5) if fk > 0 else 0.0
    except:
        prospektif_fk = fk

    h["Durum"] = durum
    h["Prospektif_FK"] = prospektif_fk
    guncellenecek_paketler.append(h)

print(f"✅ Filtreden Geçen ve Temizlenen Hisse Sayısı: {len(guncellenecek_paketler)}")

# Bilanço kodunun okuması için hisse listesini repo içine kaydet
with open("bist_hisseleri.json", "w", encoding="utf-8") as f:
    json.dump([h["Hisse"] for h in guncellenecek_paketler], f)

# --- 7. MAKE.COM WEBHOOK İLE EXCEL'E AKTARIM (GÜNCELLENDİ) ---
guncellenecek_paketler.sort(key=lambda x: x["Hisse"])

matris_verisi = []
for h in guncellenecek_paketler:
    # Power BI'a giden verinin BİREBİR AYNISI Excel (Make.com) ham veri sayfasına gidiyor (9 Sütun)
    matris_verisi.append([
        h["Hisse"],           # A Sütunu
        h["Sektor"],          # B Sütunu
        h["FK"],              # C Sütunu
        h["PDDD"],            # D Sütunu
        h["FD_FAVOK"],        # E Sütunu
        h["NetBorc_FAVOK"],   # F Sütunu
        h["PDS"],             # G Sütunu
        h["Prospektif_FK"],   # H Sütunu
        h["Durum"]            # I Sütunu
    ])

# Dinamik aralık artık A'dan I'ya (9 Sütun) genişletildi
bitis_satiri = len(matris_verisi) + 1
dinamik_aralik = f"A2:I{bitis_satiri}"

payload = {
    "islem_turu": "Haftalik_Carpan_Guncelleme",
    "tarih": datetime.now().strftime("%d.%m.%Y"),
    "hisseler": guncellenecek_paketler,
    "range_adresi": dinamik_aralik,
    "hazir_body_zb": json.dumps({"values": matris_verisi})
}

res = requests.post(MAKE_WEBHOOK_URL, json=payload, headers={"Content-Type": "application/json"})
if res.status_code == 200:
    print(f"🎉 BİST TÜM Zengin Çarpanları ({dinamik_aralik} aralığına) Make.com üzerinden Excel'e aktarıldı!")
else:
    print(f"⚠️ Make.com Yanıt Kodu: {res.status_code}")

# --- 8. TELEGRAM BÜLTENİ GÖNDERİMİ ---
iskontolular = [x for x in guncellenecek_paketler if x["Durum"] == "🟢 İskontolu" and x["FK"] > 0]
iskontolular.sort(key=lambda x: x["FK"])
top_10 = iskontolular[:10]

mesaj = f"📊 *BİST TÜM HAFTALIK DEĞERLEME RAPORU*\n"
mesaj += f"📅 Tarih: {datetime.now().strftime('%d.%m.%Y')}\n"
mesaj += f"🔎 Analiz Edilen Temiz Hisse: `{len(guncellenecek_paketler)}`\n\n"
mesaj += "🏆 *En İskontolu Top 10 Fırsat (Sektörüne Göre):*\n"
for h in top_10:
    mesaj += f"• *{h['Hisse']}* ({h['Sektor']}): F/K: `{h['FK']}` | PD/DD: `{h['PDDD']}`\n"

mesaj += f"\n✅ Toplam `{len(iskontolular)}` hisse değerleme açısından iskontolu bölgede."

tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
try:
    requests.post(tg_url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mesaj, "parse_mode": "Markdown"})
except Exception as e:
    print(f"⚠️ Telegram gönderim hatası: {e}")

# --- 9. POWER BI İÇİN ZENGİNLEŞTİRİLMİŞ CSV ÇIKTISI (GITHUB'A KAYIT) ---
import csv

csv_dosya = "ziraat_carpanlar.csv"
# Yeni sütunlar CSV başlıklarına eklendi. Make.com listesine DOKUNULMADI.
csv_basliklar = ["Hisse", "Sektor", "FK", "PDDD", "FD_FAVOK", "NetBorc_FAVOK", "PDS", "Prospektif_FK", "Durum"]

try:
    with open(csv_dosya, mode="w", encoding="utf-8-sig", newline="") as dosya:
        yazici = csv.DictWriter(dosya, fieldnames=csv_basliklar, extrasaction='ignore')
        yazici.writeheader()
        yazici.writerows(guncellenecek_paketler)
    print(f"💾 Power BI terminali için {csv_dosya} (zenginleştirilmiş veriyle) başarıyla oluşturuldu!")
except Exception as e:
    print(f"⚠️ CSV oluşturma hatası: {e}")
