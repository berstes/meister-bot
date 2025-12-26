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

# --- FUNKTIONEN (Kopiert von vorher) ---
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

def erstelle_pdf(daten):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 20)
    pdf.cell(190, 10, txt="MEISTERBETRIEB APP", ln=1, align='C')
    
    pdf.set_font("Arial", '', 12)
    def txt(t): return t.encode('latin-1', 'replace').decode('latin-1')
    
    pdf.ln(10)
    pdf.cell(0, 10, txt=f"Kunde: {txt(daten.get('kunde_name', ''))}", ln=1)
    pdf.multi_cell(0, 10, txt=f"Problem: {txt(daten.get('problem_detail', ''))}")
    
    dateiname = "auftrag.pdf"
    pdf.output(dateiname)
    return dateiname

# --- DIE WEBSEITE (UI) ---
st.title("🛠️ MeisterBot - Sprachnachricht zu Auftrag")
st.write("Lade eine WhatsApp-Sprachnachricht hoch, um automatisch einen Auftrag zu erstellen.")

uploaded_file = st.file_uploader("Wähle eine MP3 Datei", type=["mp3", "wav", "m4a"])

if uploaded_file and api_key:
    st.info("Datei wird verarbeitet... bitte warten.")
    
    # Datei temporär speichern
    with open("temp_upload.mp3", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # 1. Hören
    transkript = audio_zu_text("temp_upload.mp3")
    st.subheader("1. Erkannter Text:")
    st.text(transkript)
    
    # 2. Verstehen
    daten = text_zu_daten(transkript)
    st.subheader("2. Extrahierte Daten:")
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
    
    st.success("Fertig! Der Auftrag wurde erstellt.")