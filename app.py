import streamlit as st
import os
import json
import pandas as pd
from datetime import datetime
from openai import OpenAI
from fpdf import FPDF

# --- 1. KONFIGURATION ---
st.set_page_config(page_title="MeisterBot", page_icon="🛠️")

api_key = st.text_input("Gib hier deinen OpenAI API Key ein:", type="password")
client = None

if api_key:
    client = OpenAI(api_key=api_key)

# --- 2. KI-FUNKTIONEN ---
def audio_zu_text(dateipfad):
    audio_file = open(dateipfad, "rb")
    return client.audio.transcriptions.create(
        model="whisper-1", 
        file=audio_file, 
        response_format="text"
    )

def text_zu_daten(rohtext):
    system_befehl = """
    Du bist ein Assistent für einen Handwerksbetrieb (Interwark).
    Extrahiere die Daten als JSON:
    - kunde_name, adresse, problem_titel, problem_detail, dringlichkeit, termin_wunsch
    """
    response = client.chat.completions.create(
        model="gpt-4o", 
        messages=[{"role": "system", "content": system_befehl}, {"role": "user", "content": rohtext}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

# --- 3. EXCEL FUNKTION (DAS GEDÄCHTNIS) ---
EXCEL_DATEI = "auftragsbuch.xlsx"

def speichere_in_excel(daten):
    # Wir bereiten die neue Zeile vor
    neuer_eintrag = {
        "Datum": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "Kunde": daten.get('kunde_name'),
        "Adresse": daten.get('adresse'),
        "Problem": daten.get('problem_titel'),
        "Dringlichkeit": daten.get('dringlichkeit'),
        "Terminwunsch": daten.get('termin_wunsch')
    }
    
    # Prüfen, ob Datei schon existiert
    if os.path.exists(EXCEL_DATEI):
        df = pd.read_excel(EXCEL_DATEI)
        # Neue Zeile anhängen
        df = pd.concat([df, pd.DataFrame([neuer_eintrag])], ignore_index=True)
    else:
        # Neue Datei erstellen
        df = pd.DataFrame([neuer_eintrag])
        
    # Speichern
    df.to_excel(EXCEL_DATEI, index=False)
    return df

# --- 4. PDF KLASSE ---
class PDF(FPDF):
    def header(self):
        if os.path.exists("logo.png"):
            self.image("logo.png", 160, 8, 20)
        elif os.path.exists("logo.jpg"):
            self.image("logo.jpg", 160, 8, 20)
            
        self.set_font('Arial', 'B', 15)
        self.cell(80, 10, 'INTERWARK', 0, 1, 'L')
        self.set_font('Arial', '', 10)
        self.cell(80, 5, 'Bernhard Stegemann-Klammt', 0, 1, 'L')
        self.cell(80, 5, 'Hohe Str. 28, 26725 Emden', 0, 1, 'L')
        self.set_draw_color(200, 200, 200)
        self.line(10, 35, 200, 35)
        self.ln(20)

    def footer(self):
        self.set_y(-30)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(60, 4, 'Interwark', 0, 0, 'L')
        self.cell(60, 4, 'Bankverbindung:', 0, 0, 'L')
        self.cell(0, 4, 'Steuernummer: 58/143/02484', 0, 1, 'L')
        self.cell(60, 4, 'Tel: +49 4921 997130', 0, 0, 'L')
        self.cell(60, 4, 'Sparkasse Emden', 0, 0, 'L')
        self.cell(0, 4, 'IBAN: DE92 2845 0000 0018 0048 61', 0, 1, 'L')

def erstelle_pdf(daten):
    pdf = PDF()
    pdf.add_page()
    def txt(t): return str(t).encode('latin-1', 'replace').decode('latin-1') if t else ""
    
    pdf.set_text_color(0)
    pdf.set_font("Arial", 'U', 8)
    pdf.ln(5)
    pdf.cell(0, 5, txt("Interwark - Hohe Str. 28 - 26725 Emden"), 0, 1)
    
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 5, txt(daten.get('kunde_name', 'Kunde')), 0, 1)
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 5, txt(daten.get('adresse', '')), 0, 1)
    
    pdf.ln(20)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt("Auftrag / Arbeitsbericht"), 0, 1)
    
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 8, txt("Problembeschreibung:"), 0, 1, fill=True)
    pdf.set_font("Arial", '', 11)
    pdf.multi_cell(0, 6, txt(daten.get('problem_detail', '')))
    
    pdf.ln(10)
    pdf.cell(0, 5, txt(f"Dringlichkeit: {daten.get('dringlichkeit', '-')}"), 0, 1)
    pdf.cell(0, 5, txt(f"Terminwunsch: {daten.get('termin_wunsch', '-')}"), 0, 1)

    dateiname = "auftrag.pdf"
    pdf.output(dateiname)
    return dateiname

# --- 5. START ---
st.title("🛠️ MeisterBot")
st.write("Lade eine WhatsApp-Sprachnachricht hoch.")
uploaded_file = st.file_uploader("Datei wählen", type=["mp3", "wav", "m4a", "ogg", "opus"])

if uploaded_file and api_key:
    st.info("Verarbeite...")
    with open(f"temp.{uploaded_file.name.split('.')[-1]}", "wb") as f:
        f.write(uploaded_file.getbuffer())
        
    try:
        # 1. Hören & Verstehen
        transkript = audio_zu_text(f.name)
        daten = text_zu_daten(transkript)
        
        # 2. PDF & Excel
        pdf_datei = erstelle_pdf(daten)
        df = speichere_in_excel(daten) # <--- Hier passiert das Speichern!
        
        st.success("Auftrag erfasst und gespeichert!")
        
        # 3. Downloads
        col1, col2 = st.columns(2)
        with col1:
            with open(pdf_datei, "rb") as pdf_file:
                st.download_button("📄 PDF Auftrag", pdf_file, "Auftrag.pdf", "application/pdf")
        
    except Exception as e:
        st.error(f"Fehler: {e}")

# --- 6. AUFTRAGSBUCH ANZEIGEN ---
st.markdown("---")
st.subheader("📊 Aktuelles Auftragsbuch")

if os.path.exists(EXCEL_DATEI):
    df_show = pd.read_excel(EXCEL_DATEI)
    st.dataframe(df_show)
    
    with open(EXCEL_DATEI, "rb") as f:
        st.download_button("💾 Excel-Liste herunterladen", f, "auftragsbuch.xlsx")
else:
    st.info("Noch keine Aufträge in dieser Sitzung gespeichert.")
