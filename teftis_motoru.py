import os
import yfinance as yf
import pandas as pd
import requests  # Kütüphane yerine doğrudan sunucuya bağlanacağız
from datetime import datetime

# ==============================================================================
# 1. API VE AYARLAR
# ==============================================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("❌ HATA: GEMINI_API_KEY bulunamadı! Lütfen GitHub Secrets'a ekleyin.")
    exit(1)

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
# 3. YF VERİ TOPLAMA VE GEMINI YAPAY ZEKA SORGUSU (DOĞRUDAN BAĞLANTI)
# ==============================================================================
for hisse in hedef_hisseler[:3]:  
    print(f"\n⚙️ {hisse} için yapay zeka teftiş raporu hazırlanıyor...")
    
    try:
        ticker = yf.Ticker(f"{hisse}.IS")
        info = ticker.info
        
        sirket_ozeti = f"""
        Şirket: {hisse} ({info.get('longName', 'Bilinmiyor')})
        Sektör: {info.get('sector', 'Bilinmiyor')}
        Piyasa Değeri: {info.get('marketCap', 'Bilinmiyor')}
        F/K Oranı: {info.get('trailingPE', 'Bilinmiyor')}
        PD/DD Oranı: {info.get('priceToBook', 'Bilinmiyor')}
        Kâr Marjı: {info.get('profitMargins', 'Bilinmiyor')}
        Özkaynak Kârlılığı (ROE): {info.get('returnOnEquity', 'Bilinmiyor')}
        Borç/Özkaynak Oranı: {info.get('debtToEquity', 'Bilinmiyor')}
        Halka Açıklık Oranı: %{round((info.get('floatShares', 0) / info.get('sharesOutstanding', 1)) * 100, 2) if info.get('sharesOutstanding') else 'Bilinmiyor'}
        """
        
        prompt = f"""
        Sen, Serkan Ünal'ın 'Borsa İstanbul İçin Hisse Seçim Rehberi' kitabındaki değer yatırımı prensiplerini uygulayan uzman ve katı bir kantitatif finansal analistsin.
        
        Bana {hisse} kodlu hisse senedi için tam olarak aşağıdaki 5 başlıktan oluşan ve Markdown formatında şık bir 'Yatırım Teftiş Karnesi' yaz.
        Şirketin güncel temel finansal verileri şunlardır:
        {sirket_ozeti}
        
        Eğer güncel verilerde bir eksiklik varsa, sektörel ve genel piyasa bilgini kullanarak (fakat yalan söylemeden, sadece mantıklı varsayımlarla) destekle.
        Dilin ciddi, şüpheli ve sadece yatırımcıyı korumaya odaklı olmalı.
        
        Şablon Başlıkları (Birebir bu formatı ve Markdown'u kullan):
        ### 📄 YATIRIM TEFTİŞ KARNESİ: {hisse}
        
        **Bölüm 1 — Elemeler (Kırmızı Çizgiler)**
        (Halka açıklık oranını değerlendir, imtiyaz veya patron riski olup olmadığını sorgula. Eğer borç çok yüksekse risk olarak belirt.)
        
        **Bölüm 2 — İş Kalitesi (Hendek Testi)**
        (Şirketin sektöründeki rekabet gücünü, korunaklı olup olmadığını ve kar sürekliliğini yorumla.)
        
        **Bölüm 3 — Tablolar (Kârın Gerçekliği)**
        (Şirketin kar üretme gücünü, ROE oranını ve marjlarını yorumla.)
        
        **Bölüm 4 — Fiyat ve Güvenlik Marjı**
        (F/K ve PD/DD oranlarına bakarak şirketin şu an ucuz mu yoksa değer tuzağı mı olduğunu hesapla.)
        
        **Bölüm 5 — Nihai Karar & Portföy Rejimi**
        (Şirketi 'Korunaklı/Kırılgan/Hendeksiz' olarak kategorize et ve portföye en fazla % kaç ağırlıkla alınabileceğini tavsiye et.)
        """
        
        # 4. KÜTÜPHANESİZ DOĞRUDAN API İSTEĞİ (En Garantili Yol)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {'Content-Type': 'application/json'}
        data = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        
        response = requests.post(url, headers=headers, json=data)
        response_json = response.json()
        
        if response.status_code == 200:
            rapor_metni = response_json['candidates'][0]['content']['parts'][0]['text']
            
            dosya_adi = f"TEFTIS_{hisse}.md"
            with open(dosya_adi, "w", encoding="utf-8") as f:
                f.write(rapor_metni)
                
            print(f"✅ {dosya_adi} başarıyla oluşturuldu ve kaydedildi!")
        else:
            print(f"⚠️ API Hatası ({hisse}): {response_json}")
            
    except Exception as e:
        print(f"⚠️ {hisse} teftişinde hata: {e}")

print("\n🚀 Tüm yapay zeka teftiş işlemleri tamamlandı!")
