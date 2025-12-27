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

# --- 1. KONFIGURATION ---
st.set_page_config(page_title="MeisterBot", page_icon="🛠️")

# Wir laden die Geheimnisse direkt (ohne [general])
# .get() verhindert Abstürze, falls doch mal was fehlt
api_key_default = st.secrets.get("openai_api_key", "")
email_sender_default = st.secrets.get("email_sender", "")
email_password_default = st.secrets.get("email_password", "")
smtp_server_default = st.secrets.get("smtp_server", "smtp.ionos.de")
smtp_port_default = st.secrets.get("smtp_port", 465)
google_json_str = st.secrets.get("google_json", "")

# --- SEITENLEISTE (STATUS-CHECK) ---
with st.sidebar:
    st.header("⚙️ Status")
    
    # 1. OpenAI
    if api_key_default:
        st.success("✅ KI-Schlüssel geladen")
        api_key = api_key_default
    else:
        st.error("❌ KI-Schlüssel fehlt")
        api_key = st.text_input("API Key manuell", type="password")
    
    st.markdown("---")
    
    # 2. Google Sheets
    if google_json_str:
        st.success("☁️ Google Sheets bereit")
    else:
        st.warning("⚠️ Google Key fehlt")
        
    blatt_name = st.text_input("Name der Tabelle", value="Auftragsbuch")
    
    st.markdown("---")
    
    # 3. E-Mail
    if email_sender_default and email_password_default:
        st.success("📧 E-Mail bereit")
        email_sender = email_sender_default
        email_password = email_password_default
        smtp_server = smtp_server_default
        smtp_port = smtp_port_default
        email_receiver = st.text_input("Empfänger (Büro)", value=email_sender)
    else:
        st.info("Manuelle E-Mail Eingabe:")
        smtp_server = st.text_input("SMTP Server", value="smtp.ionos.de")
        smtp_port = st.number_input("SMTP Port", value=465)
        email_sender = st.text_input("Deine E-Mail")
        email_password = st.text_input("E-Mail Passwort", type="password")
        email_receiver = st.text_input("Empfänger (Büro)", value=email_sender)

# Client starten
client = None
if api_key:
    client = OpenAI(api_key=api_key)

# --- 2. FUNKTIONEN ---

def speichere_in_google_sheets(daten):
    try:
        if not google_json_str:
            st.error("Fehler: Kein Google-Schlüssel in Secrets.")
            return False
            
        # Den Text-Schlüssel wieder in echtes JSON verwandeln
        creds = json.loads(google_json_str)
        gc = gspread.service_account_from_dict(creds)
        
        sh = gc.open(blatt_name)
        worksheet = sh.get_worksheet(0)
        
        # Überschriften, falls leer
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

def sende_email_mit_pdf(pdf_pfad, daten):
    try:
        msg = MIMEMultipart()
        msg['From'] = email_sender
        msg['To'] = email_receiver
        msg['Subject'] = f"Auftrag: {daten.get('kunde_name')}"

        body = f"Moin,\n\nneuer Auftrag von {daten.get('kunde_name')}.\nProblem: {daten.get('problem_titel')}\n\nViele Grüße,\nMeisterBot"
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

class PDF(FPDF):
    def header(self):
        if os.path.exists("logo.png"): self.image("logo.png", 160, 8, 20)
        elif os.path.exists("logo.jpg"): self.image("logo.jpg", 160, 8, 20)
        self.set_font('Arial', 'B', 15)
        self.cell(80, 10, 'INTERWARK', 0, 1, 'L')
        self.set_font('Arial', '', 10)
        self.cell(80, 5, 'Bernhard Stegemann-Klammt', 0
