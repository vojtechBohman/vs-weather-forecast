import os
import requests
from playwright.sync_api import sync_playwright
from google import genai

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

            # 1. Get the AI insight
            ai_text = get_ai_evaluation(forecast_text.strip())
                
            # 2. Combine AI insight with the original forecast        
            final_message = f"{forecast_text.strip()}\n{ai_text}"
            return 
            
        return "Předpověď na stránce nebyla nalezena. Struktura webu se možná změnila."

def get_ai_evaluation(forecast_text):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "" 
        
    try:
        # Using the new Google GenAI client structure
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Act as an expert paragliding instructor. Read the following weather forecast for Czech republic.
        Write a short evaluation in Czech (max 3 sentences). 
        Assess thermal conditions, wind/storm risks, and overall safety for flying. Listeners for this message are experienece pilots with more then 5 years of flying.
        Provide an out-of-the-box perspective or a slightly unconventional tip on how a pilot might approach these specific conditions today.
        
        Forecast:
        {forecast_text}
        """
        
        # Calling the latest model version
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return f"🤖 AI EXPERT (\n{response.text.strip()}\n\n"
    except Exception as e:
        print(f"AI evaluation failed: {e}")
        return ""

def send_to_telegram(text):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_ids_string = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not chat_ids_string:
        print("Chyba: Nenalezeno žádné Chat ID.")
        return

    # Rozsekání textu podle čárek na seznam jednotlivých ID
    chat_ids = chat_ids_string.split(",")
    
    # Smyčka, která projde každé ID v seznamu
    for chat_id in chat_ids:
        clean_chat_id = chat_id.strip() # Odstraní případné nechtěné mezery
        if not clean_chat_id:
            continue
            
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": clean_chat_id,
            "text": text
        }
        
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            print(f"Úspěšně odesláno do: {clean_chat_id}")
        else:
            print(f"Chyba při odesílání do {clean_chat_id}: {response.text}")
            
    requests.post(url, json=payload)

if __name__ == "__main__":
    forecast = get_forecast()
    send_to_telegram(forecast)
