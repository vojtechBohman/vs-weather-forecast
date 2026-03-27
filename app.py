import os
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from google import genai

# =====================================================================
# KONFIGURACE AI INSTRUKTORA
# =====================================================================
# Zde můžeš libovolně ladit chování a tón umělé inteligence. 
# Značky {region} a {forecast_text} skript automaticky nahradí reálnými daty.
AI_PROMPT_TEMPLATE = """
Jsi zkušený instruktor paraglidingu. Přečti si předpověď počasí pro oblast: '{region}'.
Napiš stručné zhodnocení letových podmínek (max 3-4 věty).
Publikum jsou zkušení paraglidový piloti s cca 5 lety praxe létání v ČR i Alpách.
Zaměř se i na předpověd pro nadcházející dny a na bezpečnost, termiku a sílu větru. 
Zmiň případné varování, na které by měl pilot myslet.
Rychlost větru udávej v km/h místo knotů, výšku v metrech místo stop.
Vynech oslovení, text je součástí stránky, kde není třeba.
Neformátuj text pomocí markdownu (hvězdičky apod.), piš čistý text.

Předpověď:
{forecast_text}
"""
# =====================================================================

def translate_to_czech(text):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return text
        
    try:
        client = genai.Client(api_key=api_key)
        
        # Prompt instructs the AI to translate everything, including the section headers, 
        # while keeping the meteorological terminology accurate.
        prompt = f"""
        Translate the following Slovenian aviation weather forecast into Czech. 
        Maintain the exact formatting, including the '--- Section Name ---' dividers, 
        but translate the section names into Czech as well. 
        Ensure all meteorological and aviation terminology is correctly translated.
        
        Text to translate:
        {text}
        """
        
        # Using version 2.5 as instructed
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"Translation failed: {e}")
        return text

def get_slovenia_forecast(browser):
    page = browser.new_page()
    page.goto("https://meteo.arso.gov.si/met/sl/aviation/")
    page.wait_for_timeout(3000)
    
    forecast_text = ""
    
    try:
        # Out-of-the-box approach: We bypass the entire hover/click UI 
        # and directly execute the underlying JavaScript function that fetches the data.
        page.evaluate("load_napoved()")
        
        # We wait for the specific data container (e.g., 'vremenska_slika') to become visible
        page.locator("div#vremenska_slika").wait_for(state="visible", timeout=5000)
        
        # Get the fully rendered HTML content
        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Dictionary mapping English section titles to their specific HTML IDs on the Slovenian site
        sections = {
            "Weather Picture": "vremenska_slika",
            "Surface Wind": "veter",
            "Visibility": "vidnost",
            "Phenomena": "pojavi",
            "Clouds": "oblaki",
            "Warnings": "opozorilo",
            "Glider Forecast": "prognoza",
            "Outlook for Tomorrow": "obeti"
        }
        
        # Extract the text cleanly using the predefined IDs
        for section_title, html_id in sections.items():
            div_element = soup.find(id=html_id)
            if div_element:
                # Extract text, replacing any breaks with spaces, and stripping outer whitespace
                clean_text = div_element.get_text(separator=' ', strip=True)
                forecast_text += f"--- {section_title} ---\n{clean_text}\n\n"
                
    except Exception as e:
        print(f"Failed to load Slovenia data: {e}")
        forecast_text = "Error: Could not load the forecast for Slovenia."
        
    finally:
        page.close()

    raw_text = forecast_text.strip()
    
    # Send the raw Slovenian text to the translator before returning
    if raw_text:
        print("Translating Slovenia forecast to Czech...")
        translated_text = translate_to_czech(raw_text)
        return translated_text
        
    return raw_text

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

def get_all_data():
    data = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        print("Stahuji Česko...")
        data["Česko"] = get_chmi_forecast(browser)
        print("Stahuji Rakousko...")
        data["Rakousko"] = get_austro_forecasts(browser)
        print("Stahuji DHV...")
        data.update(get_dhv_forecasts(browser))
        print("Stahuji Slovinsko...")
        data["Slovinsko"] = get_slovenia_forecast(browser)
        browser.close()
    return data

def get_ai_evaluation(region, forecast_text):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "AI hodnocení není dostupné (chybí API klíč)."
        
    try:
        client = genai.Client(api_key=api_key)
        # Použití dynamické šablony definované na začátku skriptu
        prompt = AI_PROMPT_TEMPLATE.format(region=region, forecast_text=forecast_text)
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"AI chyba pro {region}: {e}")
        return "Nepodařilo se vygenerovat AI hodnocení."

def create_html_page(processed_data):
    from datetime import datetime
    aktualni_cas = datetime.now().strftime("%d. %m. %Y v %H:%M")
    display_order = ["Česko", "Rakousko", "Severní Alpy", "Jižní Alpy", "Německo", "Slovinsko"]
    
    # 1. Dynamické vytvoření odkazů pro navigační lištu
    nav_links = ""
    for region in display_order:
        if region in processed_data:
            # Mezery v názvech (např. Severní Alpy) nahradíme pomlčkou, aby to fungovalo jako platné HTML ID
            safe_id = region.replace(" ", "-")
            nav_links += f'<a href="#{safe_id}">{region}</a>'

    html = f"""
    <!DOCTYPE html>
    <html lang="cs">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Letové Počasí - Dashboard</title>
        <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🪂</text></svg>">
        <style>
            /* Plynulé scrollování a odsazení, aby lišta nezakrývala nadpisy */
            html {{ scroll-behavior: smooth; scroll-padding-top: 80px; }}
            
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #f0f2f5; color: #1c1e21; margin: 0; padding: 0 0 20px 0; }}
            
            /* --- PŘILEPENÁ NAVIGAČNÍ LIŠTA --- */
            .sticky-nav {{
                position: sticky;
                top: 0;
                background-color: #2c3e50;
                padding: 15px 20px;
                display: flex;
                justify-content: center;
                gap: 15px;
                flex-wrap: wrap;
                z-index: 1000;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            .sticky-nav a {{
                color: #ecf0f1;
                text-decoration: none;
                font-weight: 600;
                padding: 8px 16px;
                border-radius: 20px;
                background-color: rgba(255,255,255,0.1);
                transition: background-color 0.2s, transform 0.2s;
            }}
            .sticky-nav a:hover {{
                background-color: #3498db;
                transform: translateY(-2px);
            }}
            /* --------------------------------- */
            
            .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
            h1 {{ text-align: center; color: #2c3e50; margin-top: 10px; margin-bottom: 5px; }}
            .publish-time {{ text-align: center; color: #7f8c8d; font-size: 0.9em; margin-top: 0; margin-bottom: 30px; font-style: italic; }}
            
            .region-card {{ background: white; border-radius: 12px; margin-bottom: 40px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); overflow: hidden; }}
            .region-header {{ background: #34495e; color: white; padding: 15px 25px; margin: 0; font-size: 1.5em; }}
            
            .col-ai {{ padding: 25px; background-color: #f8fcf8; border-bottom: 1px solid #eaeaea; }}
            .col-data {{ padding: 25px; }}
            
            .austro-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; padding: 20px; }}
            .day-col {{ background: #fafafa; padding: 15px; border: 1px solid #eaeaea; border-radius: 8px; }}
            .day-title {{ font-weight: 600; color: #34495e; border-bottom: 2px solid #ecf0f1; padding-bottom: 8px; margin-bottom: 12px; font-size: 0.9em; text-align: center; }}
            .day-text {{ white-space: pre-wrap; font-size: 0.85em; line-height: 1.5; color: #444; }}
            .austro-ai-col {{ background-color: #f8fcf8; padding: 15px; border: 1px solid #a3e4d7; border-radius: 8px; }}
            
            .col-title-data {{ color: #7f8c8d; font-size: 0.9em; text-transform: uppercase; letter-spacing: 1px; margin-top: 0; margin-bottom: 15px; border-bottom: 2px solid #ecf0f1; padding-bottom: 5px; }}
            .col-title-ai {{ color: #27ae60; font-size: 0.9em; text-transform: uppercase; letter-spacing: 1px; margin-top: 0; margin-bottom: 15px; border-bottom: 2px solid #a3e4d7; padding-bottom: 5px; }}
            .raw-text {{ white-space: pre-wrap; font-size: 0.95em; line-height: 1.5; color: #444; }}
            .ai-text {{ white-space: pre-wrap; font-size: 1.0em; line-height: 1.6; color: #1e8449; font-weight: 500; }}
            
            .footer {{ text-align: center; font-size: 0.8em; color: #95a5a6; margin-top: 40px; margin-bottom: 20px; }}
            
            @media (max-width: 1000px) {{ .austro-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
            @media (max-width: 650px) {{ 
                .austro-grid {{ grid-template-columns: 1fr; }} 
                .sticky-nav {{ padding: 10px; gap: 8px; }}
                .sticky-nav a {{ padding: 6px 12px; font-size: 0.9em; }}
            }}
        </style>
    </head>
    <body>
        <nav class="sticky-nav">
            {nav_links}
        </nav>
        
        <div class="container">
            <h1>🌤 Denní letový briefing</h1>
            <p class="publish-time">Aktualizováno: {aktualni_cas} UTC</p>
    """
    
    for region in display_order:
        if region in processed_data:
            raw_data = processed_data[region]['raw']
            ai_text = processed_data[region]['ai']
            
            # Bezpečné ID pro HTML (shodné s tím v navigační liště)
            safe_id = region.replace(" ", "-")
            
            # Přidání id="{safe_id}" přímo do obalu dané sekce
            html += f'<div class="region-card" id="{safe_id}"><h2 class="region-header">{region}</h2>'
            
            if isinstance(raw_data, dict):
                html += '<div class="austro-grid">'
                html += f'<div class="austro-ai-col"><h3 class="col-title-ai">🤖 AI Týdenní Instruktor</h3><div class="ai-text">{ai_text}</div></div>'
                for day, txt in raw_data.items():
                    html += f'<div class="day-col"><div class="day-title">{day}</div><div class="day-text">{txt}</div></div>'
                html += '</div>'
            else:
                html += f"""
                <div class="col-ai">
                    <h3 class="col-title-ai">🤖 AI Instruktor</h3>
                    <div class="ai-text">{ai_text}</div>
                </div>
                <div class="col-data">
                    <h3 class="col-title-data">📊 Surová předpověď</h3>
                    <div class="raw-text">{raw_data}</div>
                </div>
                """
            html += "</div>"
            
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
    display_order = ["Česko", "Rakousko", "Severní Alpy", "Jižní Alpy", "Slovinsko"] 
    
    for chat_id in chat_ids:
        clean_chat_id = chat_id.strip()
        if not clean_chat_id: 
            continue
            
        # 1. Send AI summaries for each region
        for region in display_order:
            if region in processed_data:
                ai_text = processed_data[region]['ai']
                message = f"🌤 *{region}*\n{ai_text}"
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                requests.post(url, json={"chat_id": clean_chat_id, "text": message[:4000]})
                
        # 2. Send the final message with the link to the web dashboard
        website_url = "https://vojtechbohman.github.io/vs-weather-forecast/"
        final_message = f"🚀 Kompletní letový briefing s detailními daty najdeš zde:\n{website_url}"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": clean_chat_id, "text": final_message})

if __name__ == "__main__":
    print("Startuji stahování dat ze všech zdrojů...")
    raw_data = get_all_data()
    processed_data = {}
    
    print("Zpracovávám data a žádám AI o hodnocení...")
    for region, text_or_dict in raw_data.items():
        if isinstance(text_or_dict, dict):
            combined_text = "\n\n".join([f"--- {day} ---\n{txt}" for day, txt in text_or_dict.items()])
            ai_evaluation = get_ai_evaluation(region, combined_text)
        else:
            ai_evaluation = get_ai_evaluation(region, text_or_dict)
            
        processed_data[region] = {
            'raw': text_or_dict,
            'ai': ai_evaluation
        }
        
    if processed_data:
        create_html_page(processed_data)
        # Volání Telegram funkce je aktuálně zakomentováno:
        send_to_telegram(processed_data)
        print("Hotovo! Webová stránka vygenerována.")
    else:
        print("Chyba: Žádná data nebyla stažena.")
