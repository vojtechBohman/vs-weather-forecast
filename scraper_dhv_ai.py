import os
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import google.generativeai as genai

def get_dhv_forecasts():
    url = "https://www.dhv.de/wetter/dhv-wetter/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_timeout(5000) 
        html_content = page.content()
        browser.close()
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    region_ids = {
        "Deutschland": "accordion-578",
        "Nordalpen": "accordion-579",
        "Südalpen": "accordion-580"
    }
    
    forecasts = {}
    for region, acc_id in region_ids.items():
        accordion_div = soup.find('div', id=acc_id)
        if accordion_div:
            text = accordion_div.get_text(separator='\n', strip=True)
            cleaned_text = '\n'.join([line for line in text.split('\n') if line.strip()])
            forecasts[region] = cleaned_text
            
    return forecasts

def get_ai_evaluation(region, forecast_text):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "" # If no key is provided, just skip the AI part gracefully
        
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        Act as an expert paragliding instructor. Read the following weather forecast for '{region}'.
        Write a short evaluation in Czech (max 3 sentences). 
        Assess thermal conditions, wind/storm risks, and overall safety for flying.
        Provide an out-of-the-box perspective or a slightly unconventional tip on how a pilot might approach these specific conditions today.
        
        Forecast:
        {forecast_text}
        """
        
        response = model.generate_content(prompt)
        return f"🤖 AI EXPERT ({region}):\n{response.text.strip()}\n\n"
    except Exception as e:
        print(f"AI evaluation failed for {region}: {e}")
        return ""

def send_to_telegram(forecasts):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_ids_string = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not chat_ids_string:
        print("Error: No Chat ID found.")
        return

    chat_ids = chat_ids_string.split(",")
    regions_to_send = ["Deutschland", "Nordalpen", "Südalpen"]
    
    for chat_id in chat_ids:
        clean_chat_id = chat_id.strip()
        if not clean_chat_id:
            continue
            
        for region in regions_to_send:
            if region in forecasts:
                original_text = forecasts[region]
                
                # 1. Get the AI insight
                ai_text = get_ai_evaluation(region, original_text)
                
                # 2. Combine AI insight with the original forecast
                final_message = f"{ai_text}🌤 --- PŮVODNÍ DATA: {region} ---\n{original_text}"
                
                max_length = 4000 
                text_chunks = [final_message[i:i+max_length] for i in range(0, len(final_message), max_length)]
                
                for chunk in text_chunks:
                    url = f"https://api.telegram.org/bot{token}/sendMessage"
                    payload = {
                        "chat_id": clean_chat_id,
                        "text": chunk
                    }
                    requests.post(url, json=payload)

if __name__ == "__main__":
    extracted_forecasts = get_dhv_forecasts()
    if extracted_forecasts:
        send_to_telegram(extracted_forecasts)
    else:
        print("Error: No data extracted.")
