import os
import requests
from playwright.sync_api import sync_playwright

def get_austro_forecasts(browser):
    username = os.environ.get("AUSTRO_USERNAME")
    password = os.environ.get("AUSTRO_PASSWORD")
    
    if not username or not password:
        return {"Error": "Missing Austro credentials in GitHub Secrets."}

    page = browser.new_page()
    page.goto("https://www.austrocontrol.at/flugwetter/index.php")
    page.fill("#httpd_username", username)
    page.fill("#httpd_password", password)
    page.locator("input[name='login']").click()
    page.wait_for_load_state("networkidle")
    
    page.goto("https://www.austrocontrol.at/flugwetter/index.php?id=550&lang=en")
    page.wait_for_timeout(3000)
    
    forecasts = {}
    for i in range(1, 6):
        tab_id = f"#ui-id-{i}"
        panel_id = f"#FXOS4{i}_www"
        try:
            tab_element = page.locator(tab_id)
            tab_name = tab_element.inner_text().strip().split('\n')[0]
            tab_element.click()
            
            text_locator = page.locator(f"{panel_id} p.flreq")
            text_locator.wait_for(state="visible", timeout=5000)
            text = text_locator.inner_text()
            
            # --- TEXT CLEANING ---
            
            # 1. Remove the header (keep everything AFTER the first "WETTERLAGE:")
            header_marker = "WETTERLAGE:"
            if header_marker in text:
                text = text.split(header_marker, 1)[1]
            
            # 2. Remove the footer (keep everything BEFORE the first "Detaillierte Vorhersagen")
            footer_marker = "Detaillierte Vorhersagen"
            if footer_marker in text:
                text = text.split(footer_marker, 1)[0]
            
            # 3. Clean up whitespace and any trailing dots safely
            text = text.strip()
            while text.endswith('.'):
                text = text[:-1].strip()
                
            forecasts[tab_name] = text
            
        except Exception as e:
            print(f"Failed to load day {i} from Austro: {e}")
            
    page.close()
    return forecasts if forecasts else {"Error": "Failed to download any data."}

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

def get_all_data():
    data = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        print("Stahuji Rakousko...")
        data["Rakousko"] = get_austro_forecasts(browser)
        browser.close()
    return data

if __name__ == "__main__":
    data = get_all_data()
    send_to_telegram(data)
