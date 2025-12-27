import streamlit as st
import os
import json
import pandas as pd
import gspread
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from openai import OpenAI
from fpdf import FPDF

# --- 1. KONFIGURATION & SECRETS LADEN ---
st.set_page_config(page_title="MeisterBot", page_icon="🛠️")

# Wir versuchen, ALLES aus dem Bereich [general] zu laden
try:
    secrets = st.secrets["general"]
    
    # API Key & E-Mail
    api_key_default = secrets.get("openai_api_key", "")
    email_sender_default = secrets.get("email_sender", "")
    email_password_default = secrets.get("email_password", "")
    smtp_server_default = secrets.get("smtp_server", "smtp.ionos.de")
    smtp_port_default = secrets.get("smtp_port", 465)
    
    # Google Sheets (Wir prüfen nur, ob der Schlüssel da ist)
    google_json_str = secrets.get("google_json", "")
    
except Exception as e:
    st.error(f"Fehler beim Laden der Secrets: {e}")
    api_key_default = ""
    email_sender_default = ""
    email_password_default = ""
    google_json_str = ""

# --- SEITENLEISTE (Automatisch oder Manuell) ---
with st.sidebar:
    st.header("⚙️ Einstellungen")
    
    # 1. OpenAI Key
    if api_key_default:
        st.success("✅ OpenAI Key geladen")
        api_key = api_key_default
    else:
        api_key = st.text_input("OpenAI API Key", type="password")
    
    st.markdown("---")
    
    # 2. Google Sheets
    if google_json_str:
        st.success("☁️ Google Sheets verbunden")
    else:
        st.warning("⚠️ Google Key fehlt in Secrets")
        
    blatt_name = st.text_input("Name der Tabelle", value="Auftragsbuch")
    
    st.markdown("---")
    
    # 3. E-Mail
    # Wir zeigen die Felder nur an, wenn sie NICHT im Tresor sind
    if email_sender_default and email_password_default:
        st.success(f"📧 E-Mail Versand aktiv ({email_sender_default})")
        email_sender = email_sender_default
        email_password = email_password_default
        smtp_server = smtp_server_default
        smtp_port = smtp_port_default
        email_receiver = st.text_input("Empfänger (Büro)", value=email_sender)
    else:
        st.subheader("📧 E-Mail Versand")
        smtp_server = st.text_input("SMTP Server", value="smtp.ionos.de")
        smtp_port = st.number_input("SMTP Port", value=465)
        email_sender = st.text_input("Deine E-Mail")
        email_password = st.text_input("E-Mail Passwort", type="password")
        email_receiver = st.text_input("Empfänger (Büro)", value=email_sender)

client = None
if api_key:
    client = OpenAI(api_key=api_key)

# --- 2. GOOGLE SHEETS FUNKTION (angepasst an neuen Tresor) ---
def speichere_in_google_sheets(daten):
    try:
        if not google_json_str:
            st.error("Kein Google-Schlüssel gefunden.")
            return False
            
        # Wir wandeln den Text aus den Secrets zurück in ein echtes Schlüssel-Objekt
        creds = json.loads(google_json_str)
        
        # Anmelden
        gc = gspread.service_account_from_dict(creds)
        
        # Tabelle öffnen
        sh = gc.open(blatt_name)
        worksheet = sh.get_worksheet(0)
        
        if not worksheet.get_all_values():
            worksheet.append_row(["Datum", "Kunde", "Adresse", "Problem", "Dringlichkeit", "Terminwunsch"])
            
        neue_zeile = [
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            daten.get('kunde_name'),
            daten.get('adresse'),
            daten.get('problem_titel'),
            daten.get('dringlichkeit'),
            daten.get('termin_wunsch')
        ]
        worksheet.append_row(neue_zeile)
        return True
    except Exception as e:
        st.error(f"Google Sheets Fehler: {e}")
        return False

# --- 3. E-MAIL FUNKTION ---
def sende_email_mit_pdf(pdf_pfad, daten):
    try:
        msg = MIMEMultipart()
        msg['From'] = email_sender
        msg['To'] = email_receiver
        msg['Subject'] = f"Auftrag: {daten.get('kunde_name')}"

        body = f"Moin,\n\nneuer Auftrag von {daten.get('kunde_name')}.\n\nProblem: {daten.get('problem_titel')}\nAdresse: {daten.get('adresse')}\n\nViele Grüße,\nMeisterBot"
        msg.attach(MIMEText(body, 'plain'))

        with open(pdf_pfad, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
        
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename= {os.path.basename(pdf_pfad)}")
        msg.attach(part)

        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            
        server.login(email_sender, email_password)
        text = msg.as_string()
        server.sendmail(email_sender, email_receiver, text)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Mail Fehler: {e}")
        return False

# --- 4. KI FUNKTIONEN ---
def audio_zu_text(dateipfad):
    audio_file = open(dateipfad, "rb")
    return client.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")

def text_zu_daten(rohtext):
    system_befehl = """
    Du bist ein Assistent für einen Handwerksbetrieb (Interwark).
    Extrahiere JSON: kunde_name, adresse, problem_titel, problem_detail, dringlichkeit, termin_wunsch
    """
    response = client.chat.completions.create(
        model="gpt-4o", 
        messages=[{"role": "system", "content": system_befehl}, {"role": "user", "content": rohtext}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

# --- 5. PDF KLASSE ---
class PDF(FPDF):
    def header(self):
        if os.path.exists("logo.png"): self.image("logo.png", 160, 8, 20)
        elif os.path.exists("logo.jpg"): self.image("logo.jpg", 160, 8, 20)
        self.set_font('Arial', 'B', 15)
        self.cell(80, 10, 'INTERWARK', 0, 1, 'L')
        self.set_font('Arial', '', 10)
        self.cell(80, 5, 'Bernhard Stegemann-Klammt', 0, 1, 'L')
        self.cell(80, 5, 'Hohe Str. 28, 26725 Emden', 0, 1, 'L')
        self.set_draw_color(200,200,200)
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

# --- 6. APP START ---
st.title("🛠️ MeisterBot")
st.write("Lade eine WhatsApp-Sprachnachricht hoch.")
uploaded_file = st.file_uploader("Datei wählen", type=["mp3", "wav", "m4a", "ogg", "opus"])

if uploaded_file and api_key:
    with st.spinner("⏳ Analysiere Audio..."):
        with open(f"temp.{uploaded_file.name.split('.')[-1]}", "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        try:
            transkript = audio_zu_text(f.name)
            daten = text_zu_daten(transkript)
            pdf_datei = erstelle_pdf(daten)
            
            # 1. Google Sheets
            if speichere_in_google_sheets(daten):
                st.success("✅ In Google Sheets gespeichert!")
            
            # 2. E-Mail
            if email_sender and email_password:
                if sende_email_mit_pdf(pdf_datei, daten):
                    st.toast("📧 E-Mail gesendet!", icon="📨")
            
            # 3. Download
            with open(pdf_datei, "rb") as pdf_file:
                st.download_button("📄 PDF herunterladen", pdf_file, "Auftrag.pdf", "application/pdf")
                
        except Exception as e:
            st.error(f"Fehler: {e}")
