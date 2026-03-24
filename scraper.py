import os
import requests
from playwright.sync_api import sync_playwright

def get_forecast():
    url = "https://www.chmi.cz/letectvi/textove-predpovedi-pro-letani/predpoved-pro-sportovni-letani-v-cr"
    
    with sync_playwright() as p:
        # Spuštění prohlížeče na pozadí
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        
        # Klíčový krok: počkáme 5 vteřin, než se dynamický obsah z API načte
        page.wait_for_timeout(5000) 
        
        # Vezmeme veškerý viditelný text ze stránky
        text_content = page.locator('body').inner_text()
        browser.close()
        
        # Oříznutí textu jen na samotnou předpověď
        start_marker = "Předpověď vydána:"
        if start_marker in text_content:
            start_idx = text_content.find(start_marker)
            forecast_text = text_content[start_idx:]
            
            # Odstřihnutí patičky stránky
            end_marker = "Odbor letecké meteorologie"
            if end_marker in forecast_text:
                end_idx = forecast_text.find(end_marker) + len(end_marker)
                forecast_text = forecast_text[:end_idx]
                
            return forecast_text.strip()
            
        return "Předpověď na stránce nebyla nalezena. Struktura webu se možná změnila."

def send_to_telegram(text):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    requests.post(url, json=payload)

if __name__ == "__main__":
    forecast = get_forecast()
    send_to_telegram(forecast)
