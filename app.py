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

# Secrets laden
api_key_default = st.secrets.get("openai_api_key", "")
email_sender_default = st.secrets.get("email_sender", "")
email_password_default = st.secrets.get("email_password", "")
smtp_server_default = st.secrets.get("smtp_server", "smtp.ionos.de")
smtp_port_default = st.secrets.get("smtp_port", 465)
google_json_str = st.secrets.get("google_json", "")

# --- SEITENLEISTE ---
with st.sidebar:
    st.header("⚙️ Status")
    
    if api_key_default:
        st.success("✅ KI-Schlüssel")
        api_key = api_key_default
    else:
        st.error("❌ KI-Schlüssel fehlt")
        api_key = st.text_input("Key manuell", type="password")
    
    if google_json_str:
        st.success("☁️ Google Sheets")
    else:
        st.warning("⚠️ Google Key fehlt")
        
    blatt_name = st.text_input("Tabellen-Name", value="Auftragsbuch")
    
    if email_sender_default and email_password_default:
        st.success("📧 E-Mail bereit")
        email_sender = email_sender_default
        email_password = email_password_default
        smtp_server = smtp_server_default
        smtp_port = smtp_port_default
        email_receiver = st.text_input("Empfänger", value=email_sender)
    else:
        st.info("E-Mail manuell:")
        smtp_server = st.text_input("SMTP Server", value="smtp.ionos.de")
        smtp_port = st.number_input("SMTP Port", value=465)
        email_sender = st.text_input("Deine E-Mail")
        email_password = st.text_input("Passwort", type="password")
        email_receiver = st.text_input("Empfänger", value=email_sender)

client = None
if api_key:
    client = OpenAI(api_key=api_key)

# --- 2. FUNKTIONEN ---

def speichere_in_google_sheets(daten):
    try:
        if not google_json_str:
            st.error("Fehler: Kein Google-Schlüssel.")
            return False
        creds = json.loads(google_json_str)
        gc = gspread.service_account_from_dict(creds)
        sh = gc.open(blatt_name)
        worksheet = sh.get_worksheet(0)
        
        if not worksheet.get_all_values():
            worksheet.append_row(["Datum", "Kunde", "Adresse", "Problem", "Dringlichkeit"])
            
        neue_zeile = [
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            daten.get('kunde_name'),
            daten.get('adresse'),
            daten.get('problem_titel'),
            daten.get('dringlichkeit')
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
        body = f"Neuer Auftrag.\nKunde: {daten.get('kunde_name')}\nProblem: {daten.get('problem_titel')}"
        msg.attach(MIMEText(body, 'plain'))

        with open(pdf_pfad, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(pdf_pfad)}")
        msg.attach(part)

        if int(smtp_port) == 465:
            server = smtplib.SMTP_SSL(smtp_server, int(smtp_port))
        else:
            server = smtplib.SMTP(smtp_server, int(smtp_port))
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
    system_befehl = "Extrahiere JSON: kunde_name, adresse, problem_titel, problem_detail, dringlichkeit, termin_wunsch"
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
        self.cell(80, 5, 'Bernhard Stegemann-Klammt', 0, 1, 'L')
        self.cell(80, 5, 'Hohe Str. 28, 26725 Emden', 0, 1, 'L')
        self.set_draw_color(200,200,200)
        self.line(10, 35, 200, 35)
        self.ln(20)
    def footer(self):
        self.set_y(-30)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(60, 4, 'Interwark | Sparkasse Emden | IBAN: DE92 2845 0000 0018 0048 61', 0, 1, 'L')

def erstelle_pdf(daten):
    pdf = PDF()
    pdf.add_page()
    def txt(t): return str(t).encode('latin-1', 'replace').decode('latin-1') if t else ""
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 5, txt(f"Kunde: {daten.get('kunde_name')}"), 0, 1)
    pdf.set_font("Arial", '', 12)
    pdf.multi_cell(0, 6, txt(f"Adresse: {daten.get('adresse')}"))
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt("Auftrag"), 0, 1)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    # HIER WAR DER FEHLER:
    pdf.set_fill_color(240, 240, 240) 
    pdf.cell(0, 8, txt("Problembeschreibung:"), 0, 1, fill=True)
    pdf.set_font("Arial", '', 11)
    pdf.multi_cell(0, 6, txt(daten.get('problem_detail', '')))
    dateiname = "auftrag.pdf"
    pdf.output(dateiname)
    return dateiname

# --- APP START ---
st.title("🛠️ MeisterBot")
uploaded_file = st.file_uploader("Datei wählen", type=["mp3", "wav", "m4a", "ogg", "opus"])

if uploaded_file and api_key:
    with st.spinner("Arbeite..."):
        with open(f"temp.{uploaded_file.name.split('.')[-1]}", "wb") as f:
            f.write(uploaded_file.getbuffer())
        try:
            transkript = audio_zu_text(f.name)
            daten = text_zu_daten(transkript)
            pdf_datei = erstelle_pdf(daten)
            
            if speichere_in_google_sheets(daten): 
                st.success("✅ Google Sheets gespeichert")
            
            if email_sender and email_password:
                if sende_email_mit_pdf(pdf_datei, daten): 
                    st.toast("📧 Mail gesendet!")
            
            with open(pdf_datei, "rb") as pdf_file:
                st.download_button("📄 PDF herunterladen", pdf_file, "Auftrag.pdf", "application/pdf")
        except Exception as e:
            st.error(f"Fehler: {e}")
