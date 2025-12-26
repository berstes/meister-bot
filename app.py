import streamlit as st
import os
import json
import pandas as pd
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

# Seitenleiste für Einstellungen
with st.sidebar:
    st.header("⚙️ Einstellungen")
    api_key = st.text_input("OpenAI API Key", type="password")
    
    st.markdown("---")
    st.subheader("📧 E-Mail Versand (SMTP)")
    st.info("Hier kommen die Daten deines Webhosters rein (z.B. Strato, Ionos).")
    smtp_server = st.text_input("SMTP Server", value="smtp.ionos.de") # Beispiel-Wert
    smtp_port = st.number_input("SMTP Port (meist 465 oder 587)", value=465)
    email_sender = st.text_input("Deine E-Mail Adresse")
    email_password = st.text_input("Dein E-Mail Passwort", type="password")
    
    email_receiver = st.text_input("Empfänger (Dein Büro)", value=email_sender)

client = None
if api_key:
    client = OpenAI(api_key=api_key)

# --- 2. EMAIL FUNKTION ---
def sende_email_mit_pdf(pdf_pfad, daten):
    try:
        msg = MIMEMultipart()
        msg['From'] = email_sender
        msg['To'] = email_receiver
        msg['Subject'] = f"Neuer Auftrag: {daten.get('kunde_name', 'Kunde')}"

        body = f"""
        Moin,
        
        ein neuer Auftrag wurde automatisch erfasst.
        
        Kunde: {daten.get('kunde_name')}
        Problem: {daten.get('problem_titel')}
        Dringlichkeit: {daten.get('dringlichkeit')}
        
        Das PDF-Dokument liegt im Anhang.
        
        Viele Grüße,
        Dein MeisterBot
        """
        msg.attach(MIMEText(body, 'plain'))

        # PDF anhängen
        with open(pdf_pfad, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
        
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename= {os.path.basename(pdf_pfad)}")
        msg.attach(part)

        # Verbindung zum Server herstellen
        # Hinweis: Bei SSL Port 465 nutzen wir SMTP_SSL, bei 587 oft starttls()
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
        st.error(f"E-Mail Fehler: {e}")
        return False

# --- 3. KI & DATEN FUNKTIONEN ---
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

# --- 4. EXCEL FUNKTION ---
EXCEL_DATEI = "auftragsbuch.xlsx"
def speichere_in_excel(daten):
    neuer_eintrag = {
        "Datum": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "Kunde": daten.get('kunde_name'),
        "Problem": daten.get('problem_titel'),
        "Dringlichkeit": daten.get('dringlichkeit')
    }
    if os.path.exists(EXCEL_DATEI):
        df = pd.read_excel(EXCEL_DATEI)
        df = pd.concat([df, pd.DataFrame([neuer_eintrag])], ignore_index=True)
    else:
        df = pd.DataFrame([neuer_eintrag])
    df.to_excel(EXCEL_DATEI, index=False)
    return df

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
    st.info("Verarbeite...")
    with open(f"temp.{uploaded_file.name.split('.')[-1]}", "wb") as f:
        f.write(uploaded_file.getbuffer())
        
    try:
        transkript = audio_zu_text(f.name)
        daten = text_zu_daten(transkript)
        
        pdf_datei = erstelle_pdf(daten)
        df = speichere_in_excel(daten)
        
        st.success("✅ Auftrag erstellt & gespeichert!")
        
        # E-Mail Versand Check
        if email_sender and email_password:
            with st.spinner("Sende E-Mail..."):
                erfolg = sende_email_mit_pdf(pdf_datei, daten)
                if erfolg:
                    st.toast("📧 E-Mail wurde erfolgreich versendet!", icon="📨")
        
        col1, col2 = st.columns(2)
        with col1:
            with open(pdf_datei, "rb") as pdf_file:
                st.download_button("📄 PDF herunterladen", pdf_file, "Auftrag.pdf", "application/pdf")
            
    except Exception as e:
        st.error(f"Fehler: {e}")

st.markdown("---")
st.subheader("📊 Aktuelles Auftragsbuch")
if os.path.exists(EXCEL_DATEI):
    df_show = pd.read_excel(EXCEL_DATEI)
    st.dataframe(df_show)
    with open(EXCEL_DATEI, "rb") as f:
        st.download_button("💾 Excel herunterladen", f, "auftragsbuch.xlsx")
