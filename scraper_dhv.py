import os
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

def get_dhv_forecasts():
    url = "https://www.dhv.de/wetter/dhv-wetter/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        
        # Wait for the page to render completely
        page.wait_for_timeout(5000) 
        
        # Get the full HTML content as the browser sees it
        html_content = page.content()
        browser.close()
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Map each region to its exact HTML ID based on your findings
    region_ids = {
        "Deutschland": "accordion-578",
        "Nordalpen": "accordion-579",
        "Südalpen": "accordion-580"
    }
    
    forecasts = {}
    
    for region, acc_id in region_ids.items():
        # Find the specific div container
        accordion_div = soup.find('div', id=acc_id)
        
        if accordion_div:
            # Extract text, forcing newlines to maintain readability
            text = accordion_div.get_text(separator='\n', strip=True)
            
            # Clean up the output by removing excessive blank lines
            cleaned_text = '\n'.join([line for line in text.split('\n') if line.strip()])
            
            # Add a nice header for the Telegram message
            forecasts[region] = f"🌤 --- {region} ---\n{cleaned_text}"
        else:
            print(f"Warning: Container with id '{acc_id}' for {region} was not found.")
            
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
    # To drop Germany later, simply change this list to: ["Nordalpen", "Südalpen"]
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
        print("Error: No data extracted. Check if the HTML IDs on the website have changed.")
    else:
        send_to_telegram(extracted_forecasts)
