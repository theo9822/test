import streamlit as st
from PIL import Image
import pyzbar.pyzbar as pyzbar
import pytesseract
import re
import requests
from gtts import gTTS
import io
from deep_translator import GoogleTranslator

# --- HARDCODED LOCAL DATABASE ---
HARDCODED_PRODUCTS = {
    "5941047805911": { 
        "name": "ROM | Chocolate bar with rum cream",
        "weight": "30g",
        "expiry": "14.01.2027",
        "nutrition": "Protein 3.5g, Fat 23.9g, Carbs 62.2g, 480 kcal/100g",
        "ingredients": "Sugar, hydrogenated vegetable fat, fat-reduced cocoa powder, cocoa mass, glucose syrup, humectant (sorbitol syrup), refined ethyl alcohol, whey powder, skimmed milk powder, rum (0.1%), stabilizer (invertase), emulsifier (soy lecithin), flavors. Allergens: Contains milk and soy."
    },
    "5941006101566": {
        "name": "Eugenia | Biscuits with cocoa cream",
        "weight": "36g",
        "expiry": "11.02.27", 
        "nutrition": "Protein 4.6 g, Fat 20.8 g, Carbohydrates 66.3 g, 472 kcal/100 g, Fiber 0.64 g, Salt 0.63 g, Saturated fat 3.2 g",
        "ingredients": "White WHEAT flour 650, sugar, palm fat, water, fat-reduced cocoa (3%), raising agents (ammonium hydrogen carbonate, sodium hydrogen carbonate), iodized salt, flavors (rum, vanillin). Cream content 40%. Allergens: Wheat. May contain traces of milk, soy."
    }
}

# --- MULTI-LANGUAGE DICTIONARIES ---
LANGUAGES = {
    "English": "en",
    "German": "de",
    "French": "fr",
    "Italian": "it",
    "Spanish": "es"
}

UI = {
    "en": {"title": "🛒 Smart Product Scanner", "cam": "Scan Barcode or Expiration Date", "b1": "1. Scan Barcode", "b2": "2. Scan Expiry", "b3": "3. Ask AI", "b4": "🔊 Read Info", "res": "Data Result", "prod": "Product:", "wgt": "Weight:", "exp": "Expiration Date:", "ai": "AI Insight", "wait": "Waiting for action..."},
    "de": {"title": "🛒 Intelligenter Produktscanner", "cam": "Barcode oder Ablaufdatum scannen", "b1": "1. Barcode scannen", "b2": "2. Ablaufdatum", "b3": "3. KI fragen", "b4": "🔊 Vorlesen", "res": "Ergebnis", "prod": "Produkt:", "wgt": "Gewicht:", "exp": "Haltbarkeitsdatum:", "ai": "KI-Erkenntnis", "wait": "Warten auf Aktion..."},
    "fr": {"title": "🛒 Scanner Intelligent", "cam": "Scanner le code-barres ou la date", "b1": "1. Scanner Code", "b2": "2. Date d'exp", "b3": "3. Demander à l'IA", "b4": "🔊 Lire", "res": "Résultat", "prod": "Produit :", "wgt": "Poids :", "exp": "Date d'expiration :", "ai": "Aperçu IA", "wait": "En attente..."},
    "it": {"title": "🛒 Scanner Intelligente", "cam": "Scansiona codice a barre o scadenza", "b1": "1. Scansiona Codice", "b2": "2. Scadenza", "b3": "3. Chiedi all'IA", "b4": "🔊 Leggi", "res": "Risultato", "prod": "Prodotto:", "wgt": "Peso:", "exp": "Data di Scadenza:", "ai": "Insight IA", "wait": "In attesa..."},
    "es": {"title": "🛒 Escáner Inteligente", "cam": "Escanear código o caducidad", "b1": "1. Escanear Código", "b2": "2. Caducidad", "b3": "3. Preguntar a la IA", "b4": "🔊 Leer", "res": "Resultado", "prod": "Producto:", "wgt": "Peso:", "exp": "Fecha de Caducidad:", "ai": "Análisis IA", "wait": "Esperando acción..."}
}

st.set_page_config(page_title="Smart Product Scanner", page_icon="🛒", layout="centered")

# --- LANGUAGE SELECTOR ---
selected_lang = st.selectbox("🌍 Choose Language / Wähle eine Sprache / Choisissez la langue / Scegli la lingua / Elige idioma", list(LANGUAGES.keys()))
lang_code = LANGUAGES[selected_lang]
ui = UI[lang_code]

# --- SESSION STATE ---
if 'product_name' not in st.session_state:
    st.session_state.product_name = "None"
if 'product_weight' not in st.session_state:
    st.session_state.product_weight = "None"
if 'product_expiry' not in st.session_state:
    st.session_state.product_expiry = "None"
if 'product_details' not in st.session_state:
    st.session_state.product_details = ""
if 'ai_insight' not in st.session_state:
    st.session_state.ai_insight = ui["wait"]
if 'is_hardcoded' not in st.session_state:
    st.session_state.is_hardcoded = False
if 'current_barcode' not in st.session_state:
    st.session_state.current_barcode = None

# Helper to translate status messages instantly
def set_status(msg_en):
    if lang_code == "en":
        st.session_state.ai_insight = msg_en
    else:
        st.session_state.ai_insight = GoogleTranslator(source='en', target=lang_code).translate(msg_en)

st.title(ui["title"])

# --- CAMERA INPUT ---
img_file_buffer = st.camera_input(ui["cam"])

col1, col2, col3, col4 = st.columns(4)

# --- BUTTON 1: BARCODE SCANNER ---
if col1.button(ui["b1"]):
    if img_file_buffer is not None:
        set_status("Scanning barcode...")
        image = Image.open(img_file_buffer)
        decoded_objects = pyzbar.decode(image)
        
        if decoded_objects:
            barcode_data = decoded_objects[0].data.decode("utf-8")
            st.session_state.current_barcode = barcode_data 
            
            if barcode_data in HARDCODED_PRODUCTS:
                prod = HARDCODED_PRODUCTS[barcode_data]
                st.session_state.product_name = prod["name"]
                st.session_state.product_weight = prod["weight"]
                st.session_state.product_expiry = "None" 
                st.session_state.product_details = f"Nutrition: {prod['nutrition']}. Ingredients: {prod['ingredients']}"
                st.session_state.is_hardcoded = True
                set_status(f"✅ Barcode {barcode_data} recognized locally. Now scan the expiration date.")
            else:
                st.session_state.is_hardcoded = False
                st.session_state.product_details = "" 
                st.session_state.product_expiry = "None" 
                set_status(f"Barcode {barcode_data} found. Looking up online...")
                try:
                    response = requests.get(f"https://world.openfoodfacts.org/api/v0/product/{barcode_data}.json")
                    data = response.json()
                    
                    if data.get("status") == 1:
                        product = data.get("product", {})
                        st.session_state.product_name = product.get("product_name", "Unknown Name")
                        st.session_state.product_weight = product.get("quantity", "Unknown Weight")
                        set_status("Product found online. Now scan the expiration date.")
                    else:
                        set_status("Product not found.")
                except Exception as e:
                    set_status(f"Error: {e}")
        else:
            set_status("No barcode detected.")
    else:
        st.warning("Please capture an image first." if lang_code == 'en' else GoogleTranslator(source='en', target=lang_code).translate("Please capture an image first."))

# --- BUTTON 2: SCAN EXPIRATION DATE (OCR) ---
if col2.button(ui["b2"]):
    if st.session_state.is_hardcoded and st.session_state.current_barcode in HARDCODED_PRODUCTS:
        st.session_state.product_expiry = HARDCODED_PRODUCTS[st.session_state.current_barcode]["expiry"]
        set_status("Hardcoded expiration date loaded successfully!")
    else:
        if img_file_buffer is not None:
            set_status("Extracting text from image...")
            image = Image.open(img_file_buffer)
            text = pytesseract.image_to_string(image)
            date_match = re.findall(r'\b\d{2}[\/\.-]\d{2}[\/\.-]\d{2,4}\b|\b\d{2}[\/\.-]\d{4}\b', text)
            
            if date_match:
                st.session_state.product_expiry = date_match[0]
                set_status("Expiration date found!")
            else:
                set_status("Could not clearly read an expiration date.")
        else:
            st.warning("Please take a picture of the expiration date first!" if lang_code == 'en' else GoogleTranslator(source='en', target=lang_code).translate("Please take a picture of the expiration date first!"))

# --- BUTTON 3: OLLAMA AI ---
if col3.button(ui["b3"]):
    name = st.session_state.product_name
    if name == "None":
        st.error("Scan a product first." if lang_code == 'en' else GoogleTranslator(source='en', target=lang_code).translate("Scan a product first."))
    else:
        set_status("Consulting local AI...")
        expiry_data = st.session_state.product_expiry
        details = st.session_state.product_details
        
        # Tell Ollama to output strictly in the selected language!
        prompt = f"Product: '{name}' ({st.session_state.product_weight}). Expiry: '{expiry_data}'. Details: {details}. Provide a concise health and storage summary. IMPORTANT: Write your response ONLY in {selected_lang}."
        
        try:
            url = "http://localhost:11434/api/generate"
            payload = {"model": "llama3", "prompt": prompt, "stream": False}
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                # We do not translate this because Ollama already wrote it in the target language!
                st.session_state.ai_insight = response.json().get("response", "No response.")
            else:
                set_status(f"Ollama Error: {response.text}")
        except:
             set_status("Is Ollama running locally?")

# --- BUTTON 4: TEXT TO SPEECH ---
if col4.button(ui["b4"]):
    if st.session_state.product_name == "None":
        st.error("Nothing to read yet. Scan a product!" if lang_code == 'en' else GoogleTranslator(source='en', target=lang_code).translate("Nothing to read yet. Scan a product!"))
    else:
        # Build the speech text in English first
        raw_speech = f"The product is {st.session_state.product_name}. The weight is {st.session_state.product_weight}. "
        if st.session_state.product_expiry != "None":
            raw_speech += f"The expiration date is: {st.session_state.product_expiry}. "
        if st.session_state.product_details:
            raw_speech += f"Here are the product details: {st.session_state.product_details}. "
            
        # Translate the base info into the target language
        if lang_code != 'en':
            speech_text = GoogleTranslator(source='en', target=lang_code).translate(raw_speech)
        else:
            speech_text = raw_speech

        # Append the AI insight (which is already in the target language)
        if st.session_state.ai_insight and st.session_state.ai_insight not in [u["wait"] for u in UI.values()]:
            intro = "Here is the AI Insight:" if lang_code == 'en' else GoogleTranslator(source='en', target=lang_code).translate("Here is the AI Insight:")
            speech_text += f" {intro} {st.session_state.ai_insight}"

        # Clean up text for better TTS reading
        speech_text = speech_text.replace("*", "").replace("\n", " ")

        try:
            # Generate the audio with the correct language accent!
            tts = gTTS(text=speech_text, lang=lang_code)
            audio_fp = io.BytesIO()
            tts.write_to_fp(audio_fp)
            audio_fp.seek(0)
            
            st.audio(audio_fp, format='audio/mp3', autoplay=True)
        except Exception as e:
            st.error(f"TTS Error: {e}" if lang_code == 'en' else GoogleTranslator(source='en', target=lang_code).translate(f"TTS Error: {e}"))

# --- DISPLAY OUTPUTS ---
st.divider()
st.subheader(ui["res"])

# Helper to instantly translate displayed text
def display_text(text):
    if not text or text == "None" or lang_code == "en":
        return text
    return GoogleTranslator(source='en', target=lang_code).translate(text)

st.markdown(f"**{ui['prod']}** {display_text(st.session_state.product_name)}")
st.markdown(f"**{ui['wgt']}** {st.session_state.product_weight}")
st.markdown(f"**{ui['exp']}** {st.session_state.product_expiry}")

if st.session_state.product_details:
    st.info(display_text(st.session_state.product_details))

st.subheader(ui["ai"])
st.success(st.session_state.ai_insight)
