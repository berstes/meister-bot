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
st.set_page_config(page_title="MeisterBot: Safe Mode", page_icon="🛡️")

def clean_json_string(s):
    if not s: return ""
    try: return json.loads(s)
    except:
        try: return json.loads(s, strict=False)
        except: pass
    fixed = s.replace('\n', '\\n').replace('\r', '')
    try: return json.loads(fixed)
    except: return None

# Secrets laden
api_key_default = st.secrets.get("openai_api_key", "")
email_sender_default = st.secrets.get("email_sender", "")
email_password_default = st.secrets.get("email_password", "")
smtp_server_default = st.secrets.get("smtp_server", "smtp.ionos.de")
smtp_port_default = st.secrets.get("smtp_port", 465)
google_json_raw = st.secrets.get("google_json", "")

# --- SEITENLEISTE ---
with st.sidebar:
    st.header("⚙️ Status")
    if api_key_default: st.success("✅ KI-System bereit")
    else: st.error("❌ KI-Key fehlt")
    api_key = api_key_default or st.text_input("Key", type="password")
    
    google_creds = clean_json_string(google_json_raw)
    if google_creds: st.success("☁️ Google Sheets aktiv")
    else: st.error("❌ Google Key Fehler")
        
    blatt_name = st.text_input("Google-Datei Name", value="Auftragsbuch")
    
    if email_sender_default: st.success("📧 E-Mail aktiv")
    else: st.info("E-Mail manuell:"); 
    email_sender = email_sender_default or st.text_input("E-Mail")
    email_password = email_password_default or st.text_input("Passwort", type="password")
    smtp_server = smtp_server_default or st.text_input("SMTP Server", value="smtp.ionos.de")
    smtp_port = smtp_port_default or st.number_input("SMTP Port", value=465)
    email_receiver = st.text_input("Empfänger", value=email_sender)

client = None
if api_key: client = OpenAI(api_key=api_key)

# --- 2. FUNKTIONEN: Live-Preise (ROBUST) ---

def lade_preise_sicher():
    # Standard-Preise als Fallback (falls Google streikt)
    fallback_text = """
    STANDARD-PREISLISTE (Fallback):
    - Anfahrt: 22.00 EUR
    - Arbeitszeit / Stunde: 77.00 EUR
    - Toner: ca. 155.00 EUR
    - Kleinmaterial: 15.00 EUR
    """
    
    if not google_creds:
        return fallback_text, "Google Key fehlt."

    try:
        gc = gspread.service_account_from_dict(google_creds)
        # Datei öffnen
        try:
            sh = gc.open(blatt_name)
        except:
            return fallback_text, f"Konnte Datei '{blatt_name}' nicht finden."

        # Blatt suchen
        try:
            ws = sh.worksheet("Preisliste")
        except:
            # Zeige dem Nutzer, welche Blätter da sind
            vorhandene = [s.title for s in sh.worksheets()]
            return fallback_text, f"Blatt 'Preisliste' fehlt! Gefunden: {vorhandene}"
            
        # Daten holen
        daten = ws.get_all_records()
        if not daten:
            return fallback_text, "Blatt 'Preisliste' ist leer oder Spaltenüberschriften fehlen (Zeile 1: Artikel, Preis)."

        # Erfolg!
        live_text = "AKTUELLE PREISLISTE (Live aus Cloud):\n"
        for zeile in daten:
            # Wir suchen flexibel nach Spaltennamen (Groß/Kleinschreibung egal machen wir hier manuell)
            # Wir nehmen an Spalte 1 = Artikel, Spalte 2 = Preis
            artikel = list(zeile.values())[0]
            preis = list(zeile.values())[1]
            live_text += f"- {artikel}: {preis} EUR\n"
            
        return live_text, None # None bedeutet: Kein Fehler

    except Exception as e:
        return fallback_text, f"Unbekannter Fehler: {e}"

# --- 3. INTELLIGENZ (KI) ---

def audio_zu_text(dateipfad):
    audio_file = open(dateipfad, "rb")
    return client.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")

def text_zu_daten(rohtext, preisliste_text):
    system_befehl = f"""
    Du bist ein Assistent für Handwerker. Erstelle einen Arbeitsbericht für DATEV.
    
    {preisliste_text}
    
    Aufgabe:
    1. Analysiere den Text.
    2. WICHTIG: Wenn ein Artikel aus der Liste genannt wird, nutze EXAKT diesen Preis.
    3. Berechne Netto, 19% MwSt und Brutto.
    
    Gib JSON zurück:
    {{
      "kunde_name": "...",
      "adresse": "...",
      "problem_titel": "...",
      "positionen": [
        {{ "text": "...", "menge": 1, "einzel_netto": 0.00, "gesamt_netto": 0.00 }}
      ],
      "summe_netto": 0.00,
      "mwst_betrag": 0.00,
      "summe_brutto": 0.00
    }}
    """
    response = client.chat.completions.create(
        model="gpt-4o", 
        messages=[{"role": "system", "content": system_befehl}, {"role": "user", "content": rohtext}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

# --- 4. PDF ---

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

def erstelle_bericht_pdf(daten):
    pdf = PDF()
    pdf.add_page()
    def txt(t): return str(t).encode('latin-1', 'replace').decode('latin-1') if t else ""
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 5, txt(f"Kunde: {daten.get('kunde_name')}"), 0, 1)
    pdf.set_font("Arial", '', 12)
    pdf.multi_cell(0, 6, txt(f"{daten.get('adresse')}"))
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt("Arbeitsbericht / Leistungsnachweis"), 0, 1)
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 5, txt(f"Betreff: {daten.get('problem_titel')} | Datum: {datetime.now().strftime('%d.%m.%Y')}"), 0, 1)
    pdf.ln(10)
    
    # Tabelle
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(10, 8, "#", 1, 0, 'C', 1)
    pdf.cell(90, 8, "Leistung", 1, 0, 'L', 1)
    pdf.cell(20, 8, "Menge", 1, 0, 'C', 1)
    pdf.cell(30, 8, "Einzel", 1, 0, 'R', 1)
    pdf.cell(30, 8, "Gesamt", 1, 1, 'R', 1)
    
    pdf.set_font("Arial", '', 10)
    i = 1
    for pos in daten.get('positionen', []):
        text = txt(pos.get('text', ''))
        menge = str(pos.get('menge', ''))
        einzel = f"{pos.get('einzel_netto', 0):.2f}".replace('.', ',')
        gesamt = f"{pos.get('gesamt_netto', 0):.2f}".replace('.', ',')
        
        pdf.cell(10, 8, str(i), 1, 0, 'C')
        pdf.cell(90, 8, text, 1, 0, 'L')
        pdf.cell(20, 8, menge, 1, 0, 'C')
        pdf.cell(30, 8, einzel, 1, 0, 'R')
        pdf.cell(30, 8, gesamt, 1, 1, 'R')
        i += 1
        
    netto = f"{daten.get('summe_netto', 0):.2f}".replace('.', ',')
    mwst = f"{daten.get('mwst_betrag', 0):.2f}".replace('.', ',')
    brutto = f"{daten.get('summe_brutto', 0):.2f}".replace('.', ',')
    
    pdf.ln(5)
    pdf.set_font("Arial", '', 11)
    pdf.cell(150, 6, "Summe Netto:", 0, 0, 'R')
    pdf.cell(30, 6, f"{netto} EUR", 0, 1, 'R')
    pdf.cell(150, 6, "+ 19% MwSt:", 0, 0, 'R')
    pdf.cell(30, 6, f"{mwst} EUR", 0, 1, 'R')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(150, 10, "Gesamtsumme:", 0, 0, 'R')
    pdf.cell(30, 10, f"{brutto} EUR", 0, 1, 'R')
    
    pdf.ln(10)
    pdf.set_font("Arial", 'I', 8)
    pdf.multi_cell(0, 5, txt("Hinweis: Dient als Vorlage für DATEV. Keine Rechnung i.S.d. §14 UStG."))

    dateiname = "arbeitsbericht.pdf"
    pdf.output(dateiname)
    return dateiname

def speichere_in_google_sheets(daten):
    try:
        if not google_creds: return False
        gc = gspread.service_account_from_dict(google_creds)
        sh = gc.open(blatt_name)
        worksheet = sh.get_worksheet(0)
        if not worksheet.get_all_values():
            worksheet.append_row(["Datum", "Kunde", "Arbeit", "Netto", "MwSt", "Brutto"])
        neue_zeile = [
            datetime.now().strftime("%d.%m.%Y"),
            daten.get('kunde_name'),
            daten.get('problem_titel'),
            str(daten.get('summe_netto')).replace('.', ','),
            str(daten.get('mwst_betrag')).replace('.', ','),
            str(daten.get('summe_brutto')).replace('.', ',')
        ]
        worksheet.append_row(neue_zeile)
        return True
    except Exception as e:
        return False

def sende_email_mit_pdf(pdf_pfad, daten):
    try:
        msg = MIMEMultipart()
        msg['From'] = email_sender
        msg['To'] = email_receiver
        msg['Subject'] = f"Bericht: {daten.get('kunde_name')}"
        body = f"Moin,\n\nneuer Bericht.\nBrutto: {daten.get('summe_brutto')} EUR"
        msg.attach(MIMEText(body, 'plain'))
        with open(pdf_pfad, "rb") as attachment:
            p = MIMEBase("application", "octet-stream")
            p.set_payload(attachment.read())
        encoders.encode_base64(p)
        p.add_header("Content-Disposition", f"attachment; filename={os.path.basename(pdf_pfad)}")
        msg.attach(p)
        if int(smtp_port) == 465: s = smtplib.SMTP_SSL(smtp_server, int(smtp_port))
        else: s = smtplib.SMTP(smtp_server, int(smtp_port)); s.starttls()
        s.login(email_sender, email_password)
        s.sendmail(email_sender, email_receiver, msg.as_string())
        s.quit()
        return True
    except: return False

# --- APP START ---
st.title("📝 MeisterBot")

uploaded_file = st.file_uploader("Sprachnachricht", type=["mp3", "wav", "m4a", "ogg", "opus"])

if uploaded_file and api_key:
    with st.spinner("⏳ Lade Preise & Analysiere..."):
        
        # 1. PREISE LADEN (Mit Fehlermeldung, falls was schiefgeht)
        aktuelle_preise, fehler = lade_preise_sicher()
        
        if fehler:
            st.warning(f"⚠️ Hinweis: Nutze Standard-Preise, weil: {fehler}")
            with st.expander("Details anzeigen"):
                st.write(fehler)
        else:
            st.success("✅ Live-Preise geladen!")

        with open(f"temp.{uploaded_file.name.split('.')[-1]}", "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        try:
            transkript = audio_zu_text(f.name)
            daten = text_zu_daten(transkript, aktuelle_preise)
            
            # Vorschau
            col1, col2 = st.columns(2)
            col1.metric("Netto", f"{daten.get('summe_netto'):.2f} €")
            col2.metric("Brutto", f"{daten.get('summe_brutto'):.2f} €")
            
            pdf_datei = erstelle_bericht_pdf(daten)
            if speichere_in_google_sheets(daten): st.success("✅ Tabelle gespeichert")
            if email_sender and email_password:
                if sende_email_mit_pdf(pdf_datei, daten): st.toast("📧 E-Mail raus!")
            
            with open(pdf_datei, "rb") as pdf_file:
                st.download_button("📄 PDF laden", pdf_file, "Bericht.pdf", "application/pdf")
                
        except Exception as e:
            st.error(f"Fehler: {e}")
