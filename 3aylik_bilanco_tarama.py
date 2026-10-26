import fitz
import re
import requests
import json
from datetime import datetime
import statistics
import time

MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/n14a8y2syls4m3u6v863o5468h654e5g"

# 1. ZİRAAT BÜLTENİ PDF İNDİRME
url = "https://www.ziraatyatirim.com.tr/arastirma-raporlari/haftalik-hisse-senedi-carpanlari"
res = requests.get(url, verify=False)
pdf_link_match = re.search(r'href="(/Files/.*?\.pdf)"', res.text)
if not pdf_link_match:
    raise Exception("Ziraat Bülteni PDF linki bulunamadı!")
pdf_url = "https://www.ziraatyatirim.com.tr" + pdf_link_match.group(1)
print(f"📥 PDF İndiriliyor: {pdf_url}")
pdf_res = requests.get(pdf_url, verify=False)
with open("ziraat_bulten.pdf", "wb") as f:
    f.write(pdf_res.content)

# 2. PDF METİN ÇIKARIMI
print("🔍 PDF'den veriler çıkarılıyor...")
doc = fitz.open("ziraat_bulten.pdf")
all_text = ""
for page in doc:
    all_text += page.get_text("text") + "\n"

# 3. VERİ ÇEKME & TEMİZLEME (F/K ve PD/DD)
satirlar = all_text.split("\n")
raw_data = []
for i in range(len(satirlar) - 2):
    row = satirlar[i].strip()
    if re.match(r'^[A-Z]{4,5}$', row) and len(row) <= 5:
        hisse = row
        try:
            fk_str = satirlar[i+1].strip().replace(",", ".")
            pddd_str = satirlar[i+2].strip().replace(",", ".")
            
            if "A.D." in fk_str or "A.D" in fk_str:
                fk = 0.0
            else:
                fk = float(fk_str)
                
            if "A.D." in pddd_str or "A.D" in pddd_str:
                pddd = 0.0
            else:
                pddd = float(pddd_str)
                
            raw_data.append({"Hisse": hisse, "FK": fk, "PDDD": pddd})
        except:
            continue

raw_data = [x for x in raw_data if x["PDDD"] != 0.0]

# 4. MEDYAN HESAPLAMA (TÜM BİST İÇİN)
if len(raw_data) > 0:
    fk_liste = [x["FK"] for x in raw_data if x["FK"] > 0]
    pddd_liste = [x["PDDD"] for x in raw_data if x["PDDD"] > 0]
    
    genel_medyan_fk = statistics.median(fk_liste) if fk_liste else 0
    genel_medyan_pddd = statistics.median(pddd_liste) if pddd_liste else 0
else:
    genel_medyan_fk, genel_medyan_pddd = 0, 0

print(f"📊 BİST TÜM Medyan F/K: {genel_medyan_fk:.2f} | Medyan PD/DD: {genel_medyan_pddd:.2f}")

# 5. UCUZLUK/PAHALILIK DEĞERLEMESİ
guncellenecek_paketler = []
for h in raw_data:
    if h["FK"] == 0.0:
        durum = "İskontolu" if h["PDDD"] < genel_medyan_pddd else "Pahalı"
    else:
        fk_isk = h["FK"] < genel_medyan_fk
        pddd_isk = h["PDDD"] < genel_medyan_pddd
        
        if fk_isk and pddd_isk:
            durum = "İskontolu"
        elif not fk_isk and not pddd_isk:
            durum = "Pahalı"
        else:
            durum = "Dengeli"

    guncellenecek_paketler.append({
        "Hisse": h["Hisse"],
        "FK": h["FK"],
        "PDDD": h["PDDD"],
        "Durum": durum
    })

guncellenecek_paketler.sort(key=lambda x: x["Hisse"])

# ==============================================================================
# 6. JSON DOSYASINA KAYIT (Bilanço kodunun BİST TÜM listesini okuması için)
# ==============================================================================
# Sadece hisse isimlerini alıp bist_hisseleri.json dosyasına kaydediyoruz.
hisse_isimleri_sadece = [h["Hisse"] for h in guncellenecek
