import os
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
# Importing the new GenAI library
from google import genai

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
        return "" 
        
    try:
        # Using the new Google GenAI client structure
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Act as an expert paragliding instructor. Read the following weather forecast for '{region}'.
        Write a short evaluation in Czech (max 3 sentences). 
        Assess thermal conditions, wind/storm risks, and overall safety for flying.
        Provide an out-of-the-box perspective or a slightly unconventional tip on how a pilot might approach these specific conditions today.
        
        Forecast:
        {forecast_text}
        """
        
        # Calling the latest model version
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
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

def create_html_page(forecasts):
    # Jednoduchá šablona pro moderní a čitelný vzhled i na mobilu
    html = """
    <!DOCTYPE html>
    <html lang="cs">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Letové Počasí DHV</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #f4f4f9; color: #333; margin: 0; padding: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            h1 { text-align: center; color: #2c3e50; }
            .card { background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            .region-title { color: #3498db; margin-top: 0; border-bottom: 2px solid #ecf0f1; padding-bottom: 10px; }
            .forecast-text { white-space: pre-wrap; line-height: 1.6; }
            .footer { text-align: center; font-size: 0.8em; color: #7f8c8d; margin-top: 30px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🌤 Aktuální letové podmínky</h1>
    """
    
    # Projdeme všechny stažené předpovědi a vložíme je do HTML "karet"
    for region, text in forecasts.items():
        html += f"""
            <div class="card">
                <h2 class="region-title">{region}</h2>
                <div class="forecast-text">{text}</div>
            </div>
        """
        
    html += """
        </div>
        <div class="footer">Automaticky generováno přes GitHub Actions</div>
    </body>
    </html>
    """
    
    # Uložíme vygenerované HTML do souboru
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML soubor úspěšně vytvořen.")

if __name__ == "__main__":
    extracted_forecasts = get_dhv_forecasts()
    if extracted_forecasts:
      create_html_page(extracted_forecasts)
      #send_to_telegram(extracted_forecasts)
    else:
        print("Error: No data extracted.")
