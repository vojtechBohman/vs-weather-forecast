import os
import requests
from playwright.sync_api import sync_playwright

def get_dhv_forecasts():
    url = "https://www.dhv.de/wetter/dhv-wetter/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_timeout(6000) 
        
        text_content = page.locator('body').inner_text()
        browser.close()
        
    # Define the regions we are looking for
    regions = ["Deutschland", "Nordalpen", "Südalpen"]
    forecasts = {}
    
    # Smart parsing: extract text between the region headers
    for i, region in enumerate(regions):
        start_idx = text_content.find(region)
        if start_idx == -1:
            continue # Region not found on the page
        
        # Find where this region's text ends (the start of the next region)
        if i + 1 < len(regions):
            next_region = regions[i+1]
            end_idx = text_content.find(next_region)
            if end_idx == -1:
                end_idx = len(text_content) # Fallback if next region is missing
        else:
            # For the last region (Südalpen), just take the rest of the text
            end_idx = len(text_content)
            
        # Store the extracted text in our dictionary (cleaning up extra spaces)
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
    # To stop sending Germany later, just delete "Deutschland" from this list.
    # Example: regions_to_send = ["Nordalpen", "Südalpen"]
    # =================================================================
    regions_to_send = ["Deutschland", "Nordalpen", "Südalpen"]
    
    for chat_id in chat_ids:
        clean_chat_id = chat_id.strip()
        if not clean_chat_id:
            continue
            
        for region in regions_to_send:
            if region in forecasts:
                text = forecasts[region]
                
                # We still keep the chunking logic just in case one region is extremely long
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
        print("Error: No forecasts could be parsed from the page.")
    else:
        send_to_telegram(extracted_forecasts)
