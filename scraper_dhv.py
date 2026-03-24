import os
import re
import requests
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def get_dhv_forecasts():
    url = "https://www.dhv.de/wetter/dhv-wetter/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        # Give it a bit more time (10 seconds) to ensure all external weather scripts load
        page.wait_for_timeout(10000) 
        
        # Extract HTML from the main page AND any possible iframes just to be 100% sure
        raw_html = ""
        for frame in page.frames:
            try:
                raw_html += frame.content()
            except:
                pass
                
        browser.close()
        
    # BeautifulSoup will extract ALL text, including text hidden inside closed accordions
    soup = BeautifulSoup(raw_html, 'html.parser')
    text_content = soup.get_text(separator='\n', strip=True)
    
    regions = ["Deutschland", "Nordalpen", "Südalpen"]
    forecasts = {}
    
    # Smart parsing: Find region name followed by a day abbreviation (Mo., Di., Mi., Do., Fr., Sa., So.)
    # This completely ignores navigation menus and finds the actual start of the data.
    days_regex = r"(Mo\.|Di\.|Mi\.|Do\.|Fr\.|Sa\.|So\.)"
    
    for i, region in enumerate(regions):
        # Build a regex pattern like: "Deutschland\s+(Mo.|Di.|...)"
        pattern = re.compile(rf"{region}\s+{days_regex}")
        match = pattern.search(text_content)
        
        if not match:
            continue
            
        start_idx = match.start()
        
        # Where does this section end? At the start of the next region's actual forecast
        end_idx = len(text_content)
        if i + 1 < len(regions):
            next_region = regions[i+1]
            next_pattern = re.compile(rf"{next_region}\s+{days_regex}")
            next_match = next_pattern.search(text_content)
            
            if next_match:
                end_idx = next_match.start()
                
        # Cut the text and save it
        forecast_text = text_content[start_idx:end_idx].strip()
        forecasts[region] = forecast_text
        
    return forecasts

def send_to_telegram(forecasts):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_ids_string = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not chat_ids_string:
        print("Error: No Chat ID found.")
        return

    chat_ids = chat_ids_string.split(",")
    
    # =================================================================
    # CONFIGURATION: Choose which regions to send. 
    # If you later want to drop Germany, just remove it from this list:
    # regions_to_send = ["Nordalpen", "Südalpen"]
    # =================================================================
    regions_to_send = ["Deutschland", "Nordalpen", "Südalpen"]
    
    for chat_id in chat_ids:
        clean_chat_id = chat_id.strip()
        if not clean_chat_id:
            continue
            
        for region in regions_to_send:
            if region in forecasts:
                text = forecasts[region]
                
                # Split chunks if text is longer than Telegram's 4096 character limit
                max_length = 4000 
                text_chunks = [text[i:i+max_length] for i in range(0, len(text), max_length)]
                
                for chunk in text_chunks:
                    url = f"https://api.telegram.org/bot{token}/sendMessage"
                    payload = {
                        "chat_id": clean_chat_id,
                        "text": chunk
                    }
                    response = requests.post(url, json=payload)
                    
                    if response.status_code == 200:
                        print(f"Successfully sent {region} to {clean_chat_id}.")
                    else:
                        print(f"Error sending to {clean_chat_id}: {response.text}")

if __name__ == "__main__":
    extracted_forecasts = get_dhv_forecasts()
    
    if not extracted_forecasts:
        print("Error: No forecasts could be parsed. The page structure might have changed drastically.")
    else:
        send_to_telegram(extracted_forecasts)
