import streamlit as st
import os
import json
from openai import OpenAI
from fpdf import FPDF

# --- 1. KONFIGURATION ---
api_key = st.text_input("Gib hier deinen OpenAI API Key ein:", type="password")
client = None

if api_key:
    client = OpenAI(api_key=api_key)

# --- 2. KI-FUNKTIONEN ---

def audio_zu_text(dateipfad):
    """Sendet die Audio-Datei an Whisper (Speech-to-Text)"""
    audio_file = open(dateipfad, "rb")
    return client.audio.transcriptions.create(
        model="whisper-1", 
        file=audio_file, 
        response_format="text"
    )

def text_zu_daten(rohtext):
    """Sendet den Text an GPT-4o, um saubere Daten zu bekommen"""
    system_befehl = """
    Du bist ein Assistent für einen Handwerksbetrieb (Interwark).
    Analysiere die Kundenanfrage.
    Gib das Ergebnis AUSSCHLIESSLICH als JSON-Objekt zurück mit den Feldern:
    - kunde_name (Name der Person)
    - adresse (Straße, Ort)
    - problem_titel (Kurze Überschrift)
    - problem_detail (Genaue Beschreibung)
    - dringlichkeit (Niedrig, Mittel, Hoch)
    - termin_wunsch (z.B. 'Nächste Woche', 'Morgen')
    """
    
    response = client.chat.completions.create(
        model="gpt-4o", 
        messages=[
            {"role": "system", "content": system_befehl},
            {"role": "user", "content": rohtext}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

# --- 3. PDF GENERATOR (Design-Klasse) ---

class PDF(FPDF):
    def header(self):
        # A) LOGO (Rechts oben, proportional verkleinert auf Breite=20mm)
        # Der Code prüft automatisch, ob ein Bild da ist
        if os.path.exists("logo.png"):
            self.image("logo.png", 160, 8, 20) 
        elif os.path.exists("logo.jpg"):
            self.image("logo.jpg", 160, 8, 20)
            
        # B) BRIEFKOPF (Links oben)
        self.set_font('Arial', 'B', 15)
        self.cell(80, 10, 'INTERWARK', 0, 1, 'L')
        
        self.set_font('Arial', '', 10)
        self.cell(80, 5, 'Bernhard Stegemann-Klammt', 0, 1, 'L')
        self.cell(80, 5, 'Hohe Str. 28, 26725 Emden', 0, 1, 'L')
        
        # Linie unter dem Kopf
        self.set_draw_color(200, 200, 200) # Hellgrau
        self.line(10, 35, 200, 35)
        self.ln(20) # Abstand nach unten

    def footer(self):
        # Position 3 cm von unten
        self.set_y(-30)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128) # Grau
        
        # Spalte 1: Adresse
        self.cell(60, 4, 'Interwark', 0, 0, 'L')
        self.cell(60, 4, 'Bankverbindung:', 0, 0, 'L')
        self.cell(0, 4, 'Steuernummer:', 0, 1, 'L')
        
        # Spalte 2: Kontakt & Bank
        self.cell(60, 4, 'Tel: +49 4921 997130', 0, 0, 'L')
        self.cell(60, 4, 'Sparkasse Emden', 0, 0, 'L')
        self.cell(0, 4, '58/143/02484', 0, 1, 'L')
        
        # Spalte 3: IBAN & USt-ID
        self.cell(60, 4, '', 0, 0, 'L')
        self.cell(60, 4, 'IBAN: DE92 2845 0000 0018 0048 61', 0, 0, 'L') # Deine IBAN
        self.cell(0, 4, 'USt-IdNr.: DE226723406', 0, 1, 'L')

def erstelle_pdf(daten):
    pdf = PDF()
    pdf.add_page()
    
    # Hilfsfunktion für deutsche Umlaute (ä,ö,ü)
    def txt(t): 
        if t: return str(t).encode('latin-1', 'replace').decode('latin-1')
        return ""
    
    # --- ABSENDERZEILE (für Fensterbriefumschlag) ---
    pdf.set_text_color(0) # Schwarz
    pdf.set_font("Arial", 'U', 8) # Unterstrichen, klein
    pdf.ln(5)
    pdf.cell(0, 5, txt("Interwark - Hohe Str. 28 - 26725 Emden"), 0, 1)
    
    # --- EMPFÄNGER ---
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 5, txt(daten.get('kunde_name', 'Kunde')), 0, 1)
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 5, txt(daten.get('adresse', '')), 0, 1)
    
    # --- TITEL ---
    pdf.ln(20)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt(f"Auftrag / Arbeitsbericht"), 0, 1)
    
    # --- PROBLEM-BOX ---
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.set_fill_color(240, 240, 240) # Hellgrau hinterlegt
    pdf.cell(0, 8, txt("Meldung / Problembeschreibung:"), 0, 1, fill=True)
    
    pdf.set_font("Arial", '', 11)
    pdf.multi_cell(0, 6, txt(daten.get('problem_detail', '')))
    
    # --- DRINGLICHKEIT ---
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(35, 8, txt("Dringlichkeit:"), 0, 0)
    pdf.set_font("Arial", '', 11)
    pdf.cell(0, 8, txt(daten.get('dringlichkeit', '-')), 0, 1)
    
    # --- TERMIN ---
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(35, 8, txt("Terminwunsch:"), 0, 0)
    pdf.set_font("Arial", '', 11)
    pdf.cell(0, 8, txt(daten.get('termin_wunsch', '-')), 0, 1)

    # --- UNTERSCHRIFTEN-BEREICH ---
    pdf.ln(30)
    # Linien zeichnen
    y = pdf.get_y()
    pdf.line(10, y, 90, y)   # Linie links
    pdf.line(110, y, 190, y) # Linie rechts
    
    pdf.set_font("Arial", '', 8)
    pdf.cell(90, 5, "Datum, Unterschrift Monteur", 0, 0, 'C')
    pdf.cell(10, 5, "", 0, 0) # Abstand
    pdf.cell(90, 5, "Datum, Unterschrift Kunde", 0, 1, 'C')

    # Speichern
    dateiname = "auftrag.pdf"
    pdf.output(dateiname)
    return dateiname

# --- 4. DIE WEBSEITE (Frontend) ---
st.set_page_config(page_title="MeisterBot", page_icon="🛠️")

st.title("🛠️ MeisterBot")
st.write("Lade eine WhatsApp-Sprachnachricht hoch, um automatisch einen Auftrag zu erstellen.")

# Hier erlauben wir alle typischen Audio-Formate
uploaded_file = st.file_uploader("Sprachnachricht wählen", type=["mp3", "wav", "m4a", "ogg", "opus"])

if uploaded_file and api_key:
    st.info("⏳ Datei wird verarbeitet... einen Moment.")
    
    # Dateiendung ermitteln (wichtig, damit wir sie sauber speichern)
    dateiname = uploaded_file.name
    endung = dateiname.split('.')[-1]
    temp_filename = f"temp_audio.{endung}"
    
    # 1. Datei speichern
    with open(temp_filename, "wb") as f:
        f.write(uploaded_file.getbuffer())
        
    try:
        # 2. Hören (Whisper)
        transkript = audio_zu_text(temp_filename)
        st.success("Sprache erkannt!")
        with st.expander("Ganzen Text anzeigen"):
            st.write(transkript)
            
        # 3. Verstehen (GPT-4)
        daten = text_zu_daten(transkript)
        st.subheader("Extrahierte Auftragsdaten:")
        st.json(daten)
        
        # 4. Drucken (PDF)
        pdf_datei = erstelle_pdf(daten)
        
        with open(pdf_datei, "rb") as pdf_file:
            st.download_button(
                label="📄 PDF Auftrag herunterladen",
                data=pdf_file,
                file_name=f"Auftrag_{daten.get('kunde_name', 'Neu')}.pdf",
                mime="application/pdf"
            )
            
    except Exception as e:
        st.error(f"Hoppla, ein Fehler ist aufgetreten: {e}")