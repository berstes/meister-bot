import streamlit as st
import osimport streamlit as st
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
st.set_page_config(page_title="MeisterBot: DATEV Vorlage", page_icon="📝")

# JSON-Cleaner (Reparatur-Funktion)
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
        
    blatt_name = st.text_input("Tabelle", value="Auftragsbuch")
    
    if email_sender_default: st.success("📧 E-Mail aktiv")
    else: st.info("E-Mail manuell:"); # ... (Manuell)
    email_sender = email_sender_default or st.text_input("E-Mail")
    email_password = email_password_default or st.text_input("Passwort", type="password")
    smtp_server = smtp_server_default or st.text_input("SMTP Server", value="smtp.ionos.de")
    smtp_port = smtp_port_default or st.number_input("SMTP Port", value=465)
    email_receiver = st.text_input("Empfänger (Büro/DATEV)", value=email_sender)

client = None
if api_key: client = OpenAI(api_key=api_key)

# --- 2. INTELLIGENZ (KI mit MwSt) ---

def audio_zu_text(dateipfad):
    audio_file = open(dateipfad, "rb")
    return client.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")

def text_zu_daten(rohtext):
    preisliste = """
    PREISLISTE (NETTO-Preise):
    - Anfahrt: 22.00 EUR
    - Arbeitszeit / Stunde: 77.00 EUR
    - Toner: ca. 155.00 EUR
    - Pauschale Kleinmaterial: 15.00 EUR
    """
    
    system_befehl = f"""
    Du bist ein Assistent für Handwerker (Interwark). Erstelle einen Arbeitsbericht für die Buchhaltung.
    {preisliste}
    
    Aufgabe:
    1. Liste alle Positionen auf (mit Netto-Einzelpreisen).
    2. Berechne die Summe Netto.
    3. Berechne 19% MwSt.
    4. Berechne die Summe Brutto.
    
    Gib JSON zurück:
    {{
      "kunde_name": "...",
      "adresse": "...",
      "problem_titel": "...",
      "positionen": [
        {{ "text": "Anfahrt", "menge": 1, "einzel_netto": 22.00, "gesamt_netto": 22.00 }}
      ],
      "summe_netto": 100.00,
      "mwst_betrag": 19.00,
      "summe_brutto": 119.00
    }}
    """
    response = client.chat.completions.create(
        model="gpt-4o", 
        messages=[{"role": "system", "content": system_befehl}, {"role": "user", "content": rohtext}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

# --- 3. PDF (ARBEITSBERICHT) ---

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
    
    # Info-Block
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 5, txt(f"Kunde: {daten.get('kunde_name')}"), 0, 1)
    pdf.set_font("Arial", '', 12)
    pdf.multi_cell(0, 6, txt(f"{daten.get('adresse')}"))
    
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 16)
    # TITEL GEÄNDERT FÜR DATEV
    pdf.cell(0, 10, txt("Arbeitsbericht / Leistungsnachweis"), 0, 1)
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 5, txt(f"Betreff: {daten.get('problem_titel')} | Datum: {datetime.now().strftime('%d.%m.%Y')}"), 0, 1)
    
    pdf.ln(10)
    
    # Tabelle Kopf
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(10, 8, "#", 1, 0, 'C', 1)
    pdf.cell(90, 8, "Leistung", 1, 0, 'L', 1)
    pdf.cell(20, 8, "Menge", 1, 0, 'C', 1)
    pdf.cell(30, 8, "Einzel (Netto)", 1, 0, 'R', 1)
    pdf.cell(30, 8, "Gesamt (Netto)", 1, 1, 'R', 1)
    
    # Positionen
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
        
    # Rechenblock (Netto / MwSt / Brutto)
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
    pdf.cell(150, 10, "Gesamtsumme (Brutto):", 0, 0, 'R')
    pdf.cell(30, 10, f"{brutto} EUR", 0, 1, 'R')
    
    # Rechtlicher Hinweis für DATEV
    pdf.ln(10)
    pdf.set_font("Arial", 'I', 8)
    pdf.multi_cell(0, 5, txt("Hinweis: Dies ist ein Leistungsnachweis/Arbeitsbericht. Dient als Vorlage zur Rechnungserstellung in DATEV. Keine Rechnung im Sinne des §14 UStG."))

    dateiname = "arbeitsbericht.pdf"
    pdf.output(dateiname)
    return dateiname

# --- 4. SPEICHERN & SENDEN ---

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
        st.error(f"Google Fehler: {e}")
        return False

def sende_email_mit_pdf(pdf_pfad, daten):
    try:
        msg = MIMEMultipart()
        msg['From'] = email_sender
        msg['To'] = email_receiver
        msg['Subject'] = f"Bericht: {daten.get('kunde_name')}"
        body = f"Moin,\n\nanbei der Arbeitsbericht für {daten.get('kunde_name')}.\n\nNetto: {daten.get('summe_netto')} EUR\nBrutto: {daten.get('summe_brutto')} EUR\n\nGruß,\nMeisterBot"
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
    except Exception as e:
        st.error(f"Mail Fehler: {e}")
        return False

# --- APP START ---
st.title("📝 MeisterBot: Bericht")
st.info("Erstellt einen Arbeitsbericht (Netto/MwSt) für DATEV.")

uploaded_file = st.file_uploader("Sprachnachricht", type=["mp3", "wav", "m4a", "ogg", "opus"])

if uploaded_file and api_key:
    with st.spinner("⏳ Erstelle Bericht..."):
        with open(f"temp.{uploaded_file.name.split('.')[-1]}", "wb") as f:
            f.write(uploaded_file.getbuffer())
        try:
            transkript = audio_zu_text(f.name)
            st.caption(f"Text: {transkript}")
            
            daten = text_zu_daten(transkript)
            
            # Vorschau der Zahlen
            col1, col2, col3 = st.columns(3)
            col1.metric("Netto", f"{daten.get('summe_netto'):.2f} €")
            col2.metric("MwSt (19%)", f"{daten.get('mwst_betrag'):.2f} €")
            col3.metric("Brutto", f"{daten.get('summe_brutto'):.2f} €")
            
            pdf_datei = erstelle_bericht_pdf(daten)
            
            if speichere_in_google_sheets(daten): 
                st.success("✅ Tabelle aktualisiert")
            
            if email_sender and email_password:
                if sende_email_mit_pdf(pdf_datei, daten): 
                    st.toast("📧 An Büro gesendet!")
            
            with open(pdf_datei, "rb") as pdf_file:
                st.download_button("📄 Bericht laden", pdf_file, "Arbeitsbericht.pdf", "application/pdf")
                
        except Exception as e:
            st.error(f"Fehler: {e}")
import json
import pandas as pd
import gspread
import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from openai import OpenAI
from fpdf import FPDF

# --- 1. KONFIGURATION ---
st.set_page_config(page_title="MeisterBot Pro", page_icon="🧾")

# Funktion zum Reparieren von kaputtem JSON
def clean_json_string(s):
    if not s: return ""
    try:
        return json.loads(s)
    except:
        try:
            return json.loads(s, strict=False)
        except:
            pass
    fixed = s.replace('\n', '\\n').replace('\r', '')
    try:
        return json.loads(fixed)
    except:
        return None

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
    if api_key_default:
        st.success("✅ KI-System bereit")
        api_key = api_key_default
    else:
        st.error("❌ KI-Key fehlt")
        api_key = st.text_input("Key", type="password")
    
    google_creds = clean_json_string(google_json_raw)
    if google_creds:
        st.success("☁️ Cloud Speicher aktiv")
    else:
        st.error("❌ Google Key Fehler")
        
    blatt_name = st.text_input("Tabelle", value="Auftragsbuch")
    
    if email_sender_default:
        st.success("📧 E-Mail aktiv")
        email_sender = email_sender_default
        email_password = email_password_default
        smtp_server = smtp_server_default
        smtp_port = smtp_port_default
        email_receiver = st.text_input("Empfänger", value=email_sender)
    else:
        st.info("E-Mail manuell:")
        # ... (Manuelle Felder wie gehabt)

client = None
if api_key:
    client = OpenAI(api_key=api_key)

# --- 2. INTELLIGENZ (KI) ---

def audio_zu_text(dateipfad):
    audio_file = open(dateipfad, "rb")
    return client.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")

def text_zu_daten(rohtext):
    # HIER IST DIE NEUE MAGIE: Wir geben der KI deine Preisliste!
    preisliste = """
    PREISLISTE (Nutze diese Werte, wenn passend):
    - Anfahrt: 22.00 EUR
    - Arbeitszeit / Stunde: 77.00 EUR
    - Toner: ca. 155.00 EUR
    - Pauschale Kleinmaterial: 15.00 EUR
    """
    
    system_befehl = f"""
    Du bist ein intelligenter Buchhalter für Handwerker (Interwark).
    {preisliste}
    
    Deine Aufgabe:
    1. Analysiere den gesprochenen Text.
    2. Erstelle eine Liste von Positionen (Rechnungsposten).
    3. Wenn der Nutzer Preise nennt, nimm diese. Wenn er nur "Anfahrt" sagt, nimm 22.00 aus der Liste.
    4. Berechne die Summen.
    
    Gib JSON zurück:
    {{
      "kunde_name": "...",
      "adresse": "...",
      "problem_titel": "...",
      "datum": "...",
      "positionen": [
        {{ "text": "Anfahrt Zone A3", "menge": 1, "einzelpreis": 22.00, "gesamt": 22.00 }},
        {{ "text": "Arbeitszeit vor Ort", "menge": 2.5, "einzelpreis": 77.00, "gesamt": 192.50 }}
      ],
      "endsumme": 214.50
    }}
    """
    
    response = client.chat.completions.create(
        model="gpt-4o", 
        messages=[{"role": "system", "content": system_befehl}, {"role": "user", "content": rohtext}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

# --- 3. PDF DESIGN (MIT TABELLE) ---

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

def erstelle_rechnungs_pdf(daten):
    pdf = PDF()
    pdf.add_page()
    def txt(t): return str(t).encode('latin-1', 'replace').decode('latin-1') if t else ""
    
    # Kunde
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 5, txt(f"Kunde: {daten.get('kunde_name')}"), 0, 1)
    pdf.set_font("Arial", '', 12)
    pdf.multi_cell(0, 6, txt(f"{daten.get('adresse')}"))
    
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt("Auftrag / Rechnung"), 0, 1)
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 5, txt(f"Betreff: {daten.get('problem_titel')}"), 0, 1)
    
    pdf.ln(10)
    
    # --- TABELLE KOPFZEILE ---
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(10, 8, "#", 1, 0, 'C', 1)
    pdf.cell(90, 8, "Beschreibung", 1, 0, 'L', 1)
    pdf.cell(20, 8, "Menge", 1, 0, 'C', 1)
    pdf.cell(30, 8, "Einzel (EUR)", 1, 0, 'R', 1)
    pdf.cell(30, 8, "Gesamt (EUR)", 1, 1, 'R', 1)
    
    # --- POSITIONEN ---
    pdf.set_font("Arial", '', 10)
    i = 1
    positionen = daten.get('positionen', [])
    
    for pos in positionen:
        text = txt(pos.get('text', ''))
        menge = str(pos.get('menge', ''))
        einzel = f"{pos.get('einzelpreis', 0):.2f}".replace('.', ',')
        gesamt = f"{pos.get('gesamt', 0):.2f}".replace('.', ',')
        
        pdf.cell(10, 8, str(i), 1, 0, 'C')
        pdf.cell(90, 8, text, 1, 0, 'L')
        pdf.cell(20, 8, menge, 1, 0, 'C')
        pdf.cell(30, 8, einzel, 1, 0, 'R')
        pdf.cell(30, 8, gesamt, 1, 1, 'R')
        i += 1
        
    # --- SUMME ---
    endsumme = f"{daten.get('endsumme', 0):.2f}".replace('.', ',')
    pdf.ln(2)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(150, 10, "Gesamtsumme:", 0, 0, 'R')
    pdf.cell(30, 10, f"{endsumme} EUR", 0, 1, 'R')
    
    # Klein gedruckt
    pdf.ln(5)
    pdf.set_font("Arial", 'I', 8)
    pdf.cell(0, 5, txt("Leistungszeitraum entspricht Rechnungsdatum. Zahlbar sofort ohne Abzug."), 0, 1)

    dateiname = "rechnung.pdf"
    pdf.output(dateiname)
    return dateiname

# --- 4. SPEICHERN & SENDEN ---

def speichere_in_google_sheets(daten):
    try:
        if not google_creds: return False
        gc = gspread.service_account_from_dict(google_creds)
        sh = gc.open(blatt_name)
        worksheet = sh.get_worksheet(0)
        
        if not worksheet.get_all_values():
            worksheet.append_row(["Datum", "Kunde", "Problem", "Summe (EUR)"])
            
        neue_zeile = [
            datetime.now().strftime("%d.%m.%Y"),
            daten.get('kunde_name'),
            daten.get('problem_titel'),
            str(daten.get('endsumme')).replace('.', ',') # Summe als Text für Excel
        ]
        worksheet.append_row(neue_zeile)
        return True
    except Exception as e:
        st.error(f"Google Fehler: {e}")
        return False

def sende_email_mit_pdf(pdf_pfad, daten):
    try:
        msg = MIMEMultipart()
        msg['From'] = email_sender
        msg['To'] = email_receiver
        msg['Subject'] = f"Rechnung: {daten.get('kunde_name')}"
        body = f"Moin,\n\nanbei die Rechnung für {daten.get('kunde_name')}.\nSumme: {daten.get('endsumme'):.2f} EUR\n\nGruß,\nMeisterBot"
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
    except Exception as e:
        st.error(f"Mail Fehler: {e}")
        return False

# --- APP START ---
st.title("🧾 MeisterBot: Rechnungs-Modus")
st.info("💡 Tipp: Sag z.B. 'Kunde Müller, Heizung repariert, 2 Stunden Arbeit, einmal Anfahrt'.")

uploaded_file = st.file_uploader("Sprachnachricht", type=["mp3", "wav", "m4a", "ogg", "opus"])

if uploaded_file and api_key:
    with st.spinner("⏳ Analysiere & Rechne..."):
        with open(f"temp.{uploaded_file.name.split('.')[-1]}", "wb") as f:
            f.write(uploaded_file.getbuffer())
        try:
            # 1. Hören
            transkript = audio_zu_text(f.name)
            st.caption(f"Verstanden: '{transkript}'")
            
            # 2. Rechnen (GPT)
            daten = text_zu_daten(transkript)
            
            # Vorschau zeigen
            st.subheader("Gefundene Positionen:")
            df_pos = pd.DataFrame(daten.get('positionen', []))
            st.table(df_pos)
            st.metric("Gesamtsumme", f"{daten.get('endsumme'):.2f} €")
            
            # 3. PDF bauen
            pdf_datei = erstelle_rechnungs_pdf(daten)
            
            # 4. Speichern & Senden
            if speichere_in_google_sheets(daten): 
                st.success("✅ In Umsatz-Tabelle gespeichert")
            
            if email_sender and email_password:
                if sende_email_mit_pdf(pdf_datei, daten): 
                    st.toast("📧 Rechnung per Mail gesendet!")
            
            with open(pdf_datei, "rb") as pdf_file:
                st.download_button("📄 Rechnung herunterladen", pdf_file, "Rechnung.pdf", "application/pdf")
                
        except Exception as e:
            st.error(f"Fehler: {e}")

