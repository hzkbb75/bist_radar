import requests

payload = {
    "sembol": "FROTO", 
    "baslik": "TEST: Acil Patron Satışı Bildirimi!", 
    "zaman": "Bugün", 
    "kap_link": "https://www.kap.org.tr/", 
    "ozet": "Patron yüklü miktarda hisse sattı."
}
requests.post("https://hook.eu1.make.com/w2bw4cexf24z4huxs3nikopnofif1t1j", json=payload)
print("Sahte sinyal gönderildi!")
