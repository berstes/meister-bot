import streamlit as st
import os
import json
from openai import OpenAI
from fpdf import FPDF

# --- KONFIGURATION ---
api_key = st.text_input("Gib hier deinen OpenAI API Key ein:", type="password")
client = None

if api_key:
    client = OpenAI(api_key=api_key)

# --- FUNKTIONEN (KI) ---
def audio_zu_text(dateipfad):
    audio_file = open(dateipfad, "rb")
    return client.audio.transcriptions.create(
        model="whisper-1", file=audio_file, response_format="text"
    )

def text_zu_daten(rohtext):
    system_befehl = """
    Du bist ein Assistent für Handwerker. Extrahiere Daten als JSON:
    - kunde_name, adresse, problem_titel, problem_detail, dringlichkeit
    """
    response = client.chat.completions.create(
        model="gpt-4o", 
        messages=[{"role": "system", "content": system_befehl}, {"role": "user", "content": rohtext}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

# --- PDF KLASSE (MIT LOGO) ---
class PDF(FPDF):
    def header(self):
        # 1. LOGO EINFÜGEN (falls vorhanden)
        # Wir platzieren es oben rechts (x=150, y=8, Breite=40)
        if os.path.exists("logo.png"):
            self.image("logo.png", 150, 8, 40)
        elif os.path.exists("logo.jpg"):
            self.image("logo.jpg", 150, 8, 40)
            
        # 2. BRIEFKOPF (Links)
        self.set_font('Arial', 'B', 15)
        self.cell(80, 10, 'INTERWARK', 0, 1, 'L')
        self.set_font('Arial', '', 10)
        self.cell(80, 5, 'Bernhard Stegemann-Klammt', 0, 1, 'L')
        self.cell(80, 5, 'Hohe Str. 28, 26725 Emden', 0, 1, 'L')
        
        # Linie
        self.set_draw_color(200, 200, 200)
        self.line(10, 35, 200, 35)
        self.ln(20)

    def footer(self):
        self.set_y(-30)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        
        # Fußzeile Daten
        self.cell(60, 5, 'Interwark', 0, 0, 'L')
        self.cell(60, 5, 'Bankverbindung:', 0, 0, 'L')
        self.cell(0, 5, 'Steuernummer:', 0, 1, 'L')
        
        self.cell(60, 5, 'Tel: +49 4921 997130', 0, 0, 'L')
        self.cell(60, 5, 'Sparkasse Emden', 0, 0, 'L')
        self.cell(0, 5, '58/143/02484', 0, 1, 'L')
        
        self.cell(60, 5, '', 0, 0, 'L')
        self.cell(60, 5, 'IBAN: DE92 2845 0000 0018 0048 61', 0, 0, 'L')
        self.cell(0, 5, 'USt-IdNr.: DE226723406', 0, 1, 'L')

def erstelle_pdf(daten):
    pdf = PDF()
    pdf.add_page()
    
    def txt(t): return str(t).encode('latin-1', 'replace').decode('latin-1')
    
    # Empfänger
    pdf.set_text_color(0)
    pdf.set_font("Arial", '', 10)
    pdf.ln(5)
    pdf.set_font("Arial", 'U', 8)
    pdf.cell(0, 5, txt("Interwark - Hohe Str. 28 - 26725 Emden"), 0, 1)
    
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 5, txt(daten.get('kunde_name', 'Kunde')), 0, 1)
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 5, txt(daten.get('adresse', '')), 0, 1)
    
    # Titel
    pdf.ln(20)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt(f"Auftrag / Rapport"), 0, 1)
    
    # Inhalt
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 11)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 8, txt("Problembeschreibung / Meldung:"), 0, 1, fill=True)
    pdf.set_font("Arial", '', 11)
    pdf.multi_cell(0, 6, txt(daten.get('problem_detail', '')))
    
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(40, 8, txt("Dringlichkeit:"), 0, 0)
    pdf.set_font("Arial", '', 11)
    pdf.cell(0, 8, txt(daten.get('dringlichkeit', '-')), 0, 1)

    # Unterschriften
    pdf.ln(30)
    pdf.line(10, pdf.get_y(), 90, pdf.get_y())
    pdf.line(110, pdf.get_y(), 190, pdf.get_y())
    pdf.set_font("Arial", '', 8)
    pdf.cell(90, 5, "Datum, Unterschrift Monteur", 0, 0, 'C')
    pdf.cell(10, 5, "", 0, 0)
    pdf.cell(90, 5, "Datum, Unterschrift Kunde", 0, 1, 'C')

    dateiname = "auftrag.pdf"
    pdf.output(dateiname)
    return dateiname

# --- WEBSEITE ---
st.title("🛠️ MeisterBot")
st.write("Lade eine WhatsApp-Sprachnachricht hoch (MP3, M4A, OGG, OPUS).")

# HIER IST DAS UPDATE: Wir erlauben jetzt mehr Dateitypen!
uploaded_file = st.file_uploader("Datei wählen", type=["mp3", "wav", "m4a", "ogg", "opus"])

if uploaded_file and api_key:
    st.info("⏳ Datei wird verarbeitet...")
    
    # Endung herausfinden (wichtig für Whisper)
    endung = uploaded_file.name.split('.')[-1]
    temp_name = f"temp_upload.{endung}"
    
    with open(temp_name, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    try:
        # 1. Hören
        transkript = audio_zu_text(temp_name)
        st.success("Erkannt!")
        st.text_area("Text:", transkript, height=100)
        
        # 2. Verstehen
        daten = text_zu_daten(transkript)
        st.subheader("Extrahierte Daten:")
        st.json(daten)
        
        # 3. PDF
        pdf_datei = erstelle_pdf(daten)
        
        with open(pdf_datei, "rb") as pdf_file:
            st.download_button(
                label="📄 PDF-Auftrag herunterladen",
                data=pdf_file,
                file_name="Auftrag.pdf",
                mime="application/pdf"
            )
            
    except Exception as e:

        st.error(f"Ein Fehler ist aufgetreten: {e}")

