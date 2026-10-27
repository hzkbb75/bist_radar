import os
import yfinance as yf
import pandas as pd
from openai import OpenAI

# ==============================================================================
# 1. API VE AYARLAR
# ==============================================================================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("❌ HATA: OPENAI_API_KEY bulunamadı! Lütfen GitHub Secrets'a ekleyin.")
    exit(1)

client = OpenAI(api_key=OPENAI_API_KEY)
MIN_TEMEL_PUAN = 60  

# ==============================================================================
# 2. HİSSE FİLTRELEME (GÜÇLÜ RADAR)
# ==============================================================================
print("🔍 Bilanço master dosyası okunuyor...")
try:
    df = pd.read_csv("master_bilanco_bist_tum.csv")
    df['Temel_Skor'] = pd.to_numeric(df['Temel_Skor'], errors='coerce').fillna(0)
    
    hedef_hisseler = df[(df['Temel_Skor'] >= MIN_TEMEL_PUAN) & (df['Iliskili_Taraf'] == "✅ Temiz")]["Hisse"].tolist()
    
    print(f"🎯 Güçlü Radar'a takılan {len(hedef_hisseler)} hisse bulundu: {hedef_hisseler}")
except Exception as e:
    print(f"❌ Veri dosyası okunamadı: {e}")
    exit(1)

if not hedef_hisseler:
    print("✅ Bu hafta teftiş edilecek yeni hisse bulunamadı.")
    exit(0)

# ==============================================================================
# 3. YF VERİ TOPLAMA VE OPENAI YAPAY ZEKA SORGUSU (TEKNİK DESTEKLİ)
# ==============================================================================
# KİLİT KALDIRILDI: Artık radardaki TÜM hisseler taranacak
for hisse in hedef_hisseler:  
    print(f"\n⚙️ {hisse} için yapay zeka teftiş raporu hazırlanıyor...")
    
    try:
        ticker = yf.Ticker(f"{hisse}.IS")
        info = ticker.info
        
        # TEKNİK VERİ HESAPLAMALARI
        current_price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
        high_52 = info.get('fiftyTwoWeekHigh', 0)
        ma_50 = info.get('fiftyDayAverage', 0)
        ma_200 = info.get('twoHundredDayAverage', 0)
        
        zirveye_uzaklik = "Bilinmiyor"
        if high_52 and current_price:
            dusus_orani = ((high_52 - current_price) / high_52) * 100
            zirveye_uzaklik = f"%{round(dusus_orani, 2)} düşmüş (Zirve: {high_52}, Anlık: {current_price})"
            
        trend_durumu = "Bilinmiyor"
        if current_price and ma_50 and ma_200:
            if current_price > ma_50 and ma_50 > ma_200:
                trend_durumu = "Güçlü Yükseliş Trendi (Fiyat > 50 HO > 200 HO)"
            elif current_price < ma_50 and ma_50 < ma_200:
                trend_durumu = "Düşüş Trendi (Fiyat < 50 HO < 200 HO)"
            else:
                trend_durumu = "Yatay veya Karışık Seyir"

        sirket_ozeti = f"""
        Şirket: {hisse} ({info.get('longName', 'Bilinmiyor')})
        Sektör: {info.get('sector', 'Bilinmiyor')}
        
        --- TEMEL VERİLER ---
        F/K Oranı: {info.get('trailingPE', 'Bilinmiyor')}
        PD/DD Oranı: {info.get('priceToBook', 'Bilinmiyor')}
        Kâr Marjı: {info.get('profitMargins', 'Bilinmiyor')}
        Özkaynak Kârlılığı (ROE): {info.get('returnOnEquity', 'Bilinmiyor')}
        Borç/Özkaynak Oranı: {info.get('debtToEquity', 'Bilinmiyor')}
        
        --- TEKNİK VERİLER ---
        52 Haftalık Zirveye Uzaklık: {zirveye_uzaklik}
        Teknik Trend Durumu: {trend_durumu}
        """
        
        prompt = f"""
        Sen, Serkan Ünal'ın 'Borsa İstanbul İçin Hisse Seçim Rehberi' kitabındaki değer yatırımı prensiplerini uygulayan uzman ve katı bir kantitatif finansal analistsin.
        
        Bana {hisse} kodlu hisse senedi için tam olarak aşağıdaki 5 başlıktan oluşan ve Markdown formatında şık bir 'Yatırım Teftiş Karnesi' yaz.
        Şirketin güncel temel ve teknik finansal verileri şunlardır:
        {sirket_ozeti}
        
        Eğer güncel verilerde bir eksiklik varsa, sektörel ve genel piyasa bilgini kullanarak destekle.
        Dilin ciddi, şüpheli ve sadece yatırımcıyı korumaya odaklı olmalı.
        Özellikle Bölüm 4'te (Fiyat ve Güvenlik Marjı) hissenin teknik olarak zirveden ne kadar düştüğünü ve trend durumunu değerlendirerek alım için güvenli bir bölgede olup olmadığını yorumla.
        
        Şablon Başlıkları (Birebir bu formatı ve Markdown'u kullan):
        ### 📄 YATIRIM TEFTİŞ KARNESİ: {hisse}
        
        **Bölüm 1 — Elemeler (Kırmızı Çizgiler)**
        **Bölüm 2 — İş Kalitesi (Hendek Testi)**
        **Bölüm 3 — Tablolar (Kârın Gerçekliği)**
        **Bölüm 4 — Fiyat, Teknik Görünüm ve Güvenlik Marjı**
        **Bölüm 5 — Nihai Karar & Portföy Rejimi**
        """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Sen usta bir kantitatif ve teknik analistsin."},
                {"role": "user", "content": prompt}
            ]
        )
        rapor_metni = response.choices[0].message.content
        
        dosya_adi = f"TEFTIS_{hisse}.md"
        with open(dosya_adi, "w", encoding="utf-8") as f:
            f.write(rapor_metni)
            
        print(f"✅ {dosya_adi} başarıyla oluşturuldu ve kaydedildi!")
        
    except Exception as e:
        print(f"⚠️ {hisse} teftişinde hata: {e}")

print("\n🚀 Tüm yapay zeka teftiş işlemleri tamamlandı!")
