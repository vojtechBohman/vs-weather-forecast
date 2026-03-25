import os
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from google import genai

def get_chmi_forecast(browser):
    url = "https://www.chmi.cz/letectvi/textove-predpovedi-pro-letani/predpoved-pro-sportovni-letani-v-cr"
    page = browser.new_page()
    page.goto(url)
    page.wait_for_timeout(5000)
    text_content = page.locator('body').inner_text()
    page.close()
    
    start_marker = "Předpověď vydána:"
    if start_marker in text_content:
        start_idx = text_content.find(start_marker)
        forecast_text = text_content[start_idx:]
        end_marker = "Odbor letecké meteorologie"
        if end_marker in forecast_text:
            end_idx = forecast_text.find(end_marker) + len(end_marker)
            forecast_text = forecast_text[:end_idx]
        return forecast_text.strip()
    return "Chyba: Předpověď ČHMÚ nenalezena."

def get_dhv_forecasts(browser):
    url = "https://www.dhv.de/wetter/dhv-wetter/"
    page = browser.new_page()
    page.goto(url)
    page.wait_for_timeout(5000) 
    html_content = page.content()
    page.close()
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Mapování německých ID rovnou na české názvy
    region_ids = {
        "Německo": "accordion-578",
        "Severní Alpy": "accordion-579",
        "Jižní Alpy": "accordion-580"
    }
    
    forecasts = {}
    for region, acc_id in region_ids.items():
        accordion_div = soup.find('div', id=acc_id)
        if accordion_div:
            text = accordion_div.get_text(separator='\n', strip=True)
            cleaned_text = '\n'.join([line for line in text.split('\n') if line.strip()])
            forecasts[region] = cleaned_text
            
    return forecasts

def get_all_data():
    data = {}
    with sync_playwright() as p:
        # Spustíme jeden prohlížeč pro oba weby, ušetří to čas a výkon
        browser = p.chromium.launch(headless=True)
        
        # 1. Stažení Česka (ČHMÚ)
        data["Česko"] = get_chmi_forecast(browser)
        
        # 2. Stažení DHV (Německo, Alpy)
        dhv_data = get_dhv_forecasts(browser)
        data.update(dhv_data) # Spojení slovníků dohromady
        
        browser.close()
    return data

def get_ai_evaluation(region, forecast_text):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "AI hodnocení není dostupné (chybí API klíč)."
        
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""
        Jsi zkušený instruktor paraglidingu. Přečti si předpověď počasí pro oblast: '{region}'.
        Napiš stručné zhodnocení letových podmínek (max 3-4 věty).
        Publikum jsou zkušení paraglidový piloti s cca 5 lety praxe létání v ČR i Alpách.
        Německou textovou předpověd (z DHV) ber trochu s rezervou, přehání.
        Zaměř se i na předpověd pro nadcházející dny.
        Zaměř se na bezpečnost, termiku a sílu větru. Přidej 'out-of-the-box' tip nebo varování, které z textu přímo nekřičí, ale pilot by na něj měl myslet.
        Rychlost udávej v m/s nebo kmph místo knotů, výšky v metrech místo stop.
        Neformátuj text pomocí markdownu (hvězdičky apod.), piš čistý text.
        
        Předpověď:
        {forecast_text}
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"AI chyba pro {region}: {e}")
        return "Nepodařilo se vygenerovat AI hodnocení."

def create_html_page(processed_data):
    # CSS je upravené pro dva sloupce (na mobilech se sloupce zlomí pod sebe)
    html = """
    <!DOCTYPE html>
    <html lang="cs">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Letové Počasí - Dashboard</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #f0f2f5; color: #1c1e21; margin: 0; padding: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            h1 { text-align: center; color: #2c3e50; margin-bottom: 30px; }
            
            .region-card { background: white; border-radius: 12px; margin-bottom: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); overflow: hidden; }
            .region-header { background: #34495e; color: white; padding: 15px 25px; margin: 0; font-size: 1.5em; }
            
            .content-wrapper { display: flex; flex-wrap: wrap; }
            
            /* Levý sloupec - Surová data */
            .col-data { flex: 1; min-width: 300px; padding: 25px; border-right: 1px solid #eaeaea; }
            .col-title-data { color: #7f8c8d; font-size: 0.9em; text-transform: uppercase; letter-spacing: 1px; margin-top: 0; margin-bottom: 15px; border-bottom: 2px solid #ecf0f1; padding-bottom: 5px; }
            .raw-text { white-space: pre-wrap; font-size: 0.95em; line-height: 1.5; color: #444; }
            
            /* Pravý sloupec - AI Zhodnocení */
            .col-ai { flex: 1; min-width: 300px; padding: 25px; background-color: #f8fcf8; }
            .col-title-ai { color: #27ae60; font-size: 0.9em; text-transform: uppercase; letter-spacing: 1px; margin-top: 0; margin-bottom: 15px; border-bottom: 2px solid #a3e4d7; padding-bottom: 5px; display: flex; align-items: center; }
            .ai-text { white-space: pre-wrap; font-size: 1.1em; line-height: 1.6; color: #1e8449; font-weight: 500; }
            
            .footer { text-align: center; font-size: 0.8em; color: #95a5a6; margin-top: 40px; }
            
            /* Responzivita pro mobily */
            @media (max-width: 768px) {
                .col-data { border-right: none; border-bottom: 1px solid #eaeaea; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🌤 Denní letový briefing</h1>
    """
    
    # Pevné pořadí, v jakém chceme oblasti na stránce zobrazit
    display_order = ["Česko", "Severní Alpy", "Jižní Alpy", "Německo"]
    
    for region in display_order:
        if region in processed_data:
            raw_text = processed_data[region]['raw']
            ai_text = processed_data[region]['ai']
            
            html += f"""
            <div class="region-card">
                <h2 class="region-header">{region}</h2>
                <div class="content-wrapper">
                    <div class="col-data">
                        <h3 class="col-title-data">📊 Surová předpověď</h3>
                        <div class="raw-text">{raw_text}</div>
                    </div>
                    <div class="col-ai">
                        <h3 class="col-title-ai">🤖 AI Instruktor</h3>
                        <div class="ai-text">{ai_text}</div>
                    </div>
                </div>
            </div>
            """
            
    html += """
        </div>
        <div class="footer">Automaticky generováno přes GitHub Actions & Google Gemini API</div>
    </body>
    </html>
    """
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML stránka úspěšně vygenerována.")

def send_to_telegram(processed_data):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_ids_string = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not chat_ids_string:
        return

    chat_ids = chat_ids_string.split(",")
    display_order = ["Česko", "Severní Alpy", "Jižní Alpy"] # Do telegramu třeba Německo posílat nechceme, aby toho nebylo moc
    
    for chat_id in chat_ids:
        clean_chat_id = chat_id.strip()
        if not clean_chat_id:
            continue
            
        for region in display_order:
            if region in processed_data:
                ai_text = processed_data[region]['ai']
                # Do Telegramu teď pošleme jen krátké AI zhodnocení a odkaz na web pro detaily
                message = f"🌤 *{region}*\n{ai_text}\n\n👉 Detailní data najdeš na webu."
                
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                payload = {
                    "chat_id": clean_chat_id,
                    "text": message[:4000]
                }
                requests.post(url, json=payload)

if __name__ == "__main__":
    print("Stahuji data z webů...")
    raw_data = get_all_data()
    
    processed_data = {}
    
    print("Zpracovávám AI hodnocení...")
    for region, text in raw_data.items():
        ai_evaluation = get_ai_evaluation(region, text)
        processed_data[region] = {
            'raw': text,
            'ai': ai_evaluation
        }
        
    if processed_data:
        create_html_page(processed_data)
        # send_to_telegram(processed_data)
    else:
        print("Chyba: Žádná data nebyla stažena.")
