import os
import requests
from playwright.sync_api import sync_playwright

def test_austro_tabs():
    username = os.environ.get("AUSTRO_USERNAME")
    password = os.environ.get("AUSTRO_PASSWORD")
    
    if not username or not password:
        return {"Chyba": "Chybí hesla v GitHub Secrets."}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("1. Přihlašování...")
        page.goto("https://www.austrocontrol.at/flugwetter/index.php")
        page.fill("#httpd_username", username)
        page.fill("#httpd_password", password)
        page.locator("input[name='login']").click()
        page.wait_for_load_state("networkidle")
        
        print("2. Načítání předpovědi (id=550)...")
        page.goto("https://www.austrocontrol.at/flugwetter/index.php?id=550&lang=en")
        page.wait_for_timeout(3000)
        
        forecasts = {}
        
        print("3. Proklikávám jednotlivé dny...")
        # Smyčka projde všech 5 tlačítek na stránce
        for i in range(1, 6):
            tab_id = f"#ui-id-{i}"
            panel_id = f"#FXOS4{i}_www"
            
            try:
                # Zjistíme název záložky (např. "Tomorrow" nebo "27.03.")
                tab_element = page.locator(tab_id)
                tab_name = tab_element.inner_text().strip()
                # Kvůli responzivnímu designu weby někdy text duplikují, bereme jen první řádek
                tab_name = tab_name.split('\n')[0] 
                
                print(f" -> Klikám na záložku: {tab_name}")
                tab_element.click()
                
                # Zde je klíčový trik: čekáme, až se v panelu objeví textový odstavec
                page.locator(f"{panel_id} p.flreq").wait_for(state="visible", timeout=5000)
                
                # Přečteme text
                text = page.locator(f"{panel_id} p.flreq").inner_text()
                forecasts[tab_name] = text.strip()
            except Exception as e:
                print(f"Nepodařilo se načíst den {i}: {e}")
        
        browser.close()
        return forecasts

def send_to_telegram(forecasts):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_ids_string = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not chat_ids_string or not forecasts: 
        return
        
    final_message = "🇦🇹 *AUSTRO CONTROL TEST*\n\n"
    for day, text in forecasts.items():
        final_message += f"📅 --- {day} ---\n{text}\n\n"
        
    # Rozsekání kvůli limitu 4096 znaků (5 dnů dat bude velmi dlouhých)
    max_length = 4000 
    text_chunks = [final_message[i:i+max_length] for i in range(0, len(final_message), max_length)]
    
    for chat_id in chat_ids_string.split(","):
        clean_id = chat_id.strip()
        if not clean_id: 
            continue
            
        for chunk in text_chunks:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": clean_id, "text": chunk})

if __name__ == "__main__":
    data = test_austro_tabs()
    send_to_telegram(data)
