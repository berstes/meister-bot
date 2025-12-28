Das ist der Beweis, dass dein Handy oder der Server die alte Datei noch im Speicher festhält. Du führst gerade immer noch den Code von vor 5 Minuten aus, obwohl du vielleicht schon neuen eingefügt hast.

Das passiert manchmal bei Web-Apps. Wir müssen den Browser zwingen, alles zu vergessen und neu zu laden.

Bitte mache es exakt in dieser Reihenfolge:

Lösche den gesamten Code in deiner Datei.

Kopiere den Code unten (das ist der finale, saubere Code).

Füge ihn ein.

WICHTIG: Drücke nicht nur auf "Rerun", sondern lade die ganze Internetseite neu (Browser-Aktualisieren Button oder am Handy den Bildschirm nach unten ziehen).

Hier ist der Code, bei dem ich den Titel extra auf "✅ MeisterBot Final" gesetzt habe, damit du sofort siehst, wenn es geklappt hat.

Python

import streamlit as st
import os
import json
import time
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
# Titel der App im Browser-Tab
st.set_page_config(page_title="MeisterBot", page_icon="✅")

# --- HELFER & DATEV ---
def baue_datev_datei(daten):
    umsatz = f"{daten.get('summe_brutto', 0):.2f}".replace('.', ',')
    datum = datetime.now().strftime("%d%m")
    rechnungs_nr = daten.get('rechnungs_nr', datetime.now().strftime("%y%m%d%H%M"))
    raw_text = f"{daten.get('kunde_name')} {daten.get('problem_titel')}"
    buchungstext = raw_text.replace(";", " ")[:60]
    header = "Umsatz (ohne Soll/Haben-Kz);Soll/Haben-Kennzeichen;WKZ;Konto;Gegenkonto (ohne BU-Schlüssel);Belegdatum;Belegfeld 1;Buchungstext"
    line = f"{umsatz};S;EUR;8400;1410;{datum};{rechnungs_nr};{buchungstext}"
    return f"{header}\n{line}"

def clean_json_string(s):
    if not s: return ""
    try: return json.loads(s)
    except:
        try: return json.loads(s, strict=False)
        except: pass
    fixed = s.replace('\n', '\\n').replace('\r', '')
    try: return json.loads(fixed)
    except: return None

# --- 2. PDF KLASSE ---
class PDF(FPDF):
    def header(self):
        pass # Manuell gesteuert
    
    def footer(self):
        self.set_y(-30)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 4, 'Interwark | Vorlage für DATEV', 0, 1, 'L')

# --- 3. BERICHT ERSTELLEN ---
def erstelle_bericht_pdf(daten):
    pdf = PDF()
    pdf.add_page()
    
    def txt(t): return str(t).encode('latin-1', 'replace').decode('latin-1') if t else ""

    # --- KOPFBEREICH (Fixiert) ---
    pdf.set_text_color(0, 0, 0)
    
    # 1. Logo
    if os.path.exists("logo.png"): pdf.image("logo.png", 160, 10, 20)
    elif os.path.exists("logo.jpg"): pdf.image("logo.jpg", 160, 10, 20)

    # 2. Adresse (Manuell positioniert)
    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_xy(10, 10); pdf.cell(0, 10, 'INTERWARK', 0, 0, 'L')
    
    pdf.set_font('Helvetica', '', 10)
    pdf.set_xy(10, 18); pdf.cell(0, 5, 'Bernhard Stegemann-Klammt', 0, 0, 'L')
    pdf.set_xy(10, 23); pdf.cell(0, 5, 'Hohe Str. 26', 0, 0, 'L')
    pdf.set_xy(10, 28); pdf.cell(0, 5, '26725 Emden', 0, 0, 'L')
    pdf.set_xy(10, 33); pdf.cell(0, 5, 'info@interwark.de', 0, 0, 'L')

    # Linie
    pdf.set_draw_color(0, 0, 0)
    pdf.line(10, 42, 200, 42)
    
    # --- INHALT ---
    pdf.set_y(55)
    
    # Kunde
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(0, 5, txt(f"Kunde: {daten.get('kunde_name')}"), ln=1)
    pdf.set_font("Helvetica", '', 12)
    pdf.multi_cell(0, 6, txt(f"{daten.get('adresse')}"))
    
    # Titel
    pdf.ln(10) 
    pdf.set_font("Helvetica", 'B', 20)
    rechnungs_nr = daten.get('rechnungs_nr', 'ENTWURF') 
    pdf.cell(0, 10, txt(f"Arbeitsbericht Nr. {rechnungs_nr}"), ln=1)
    
    # Datum
    pdf.set_font("Helvetica", '', 10)
    datum_heute = datetime.now().strftime('%d.%m.%Y')
    pdf.cell(0, 5, txt(f"Arbeitsbericht Datum: {datum_heute}"), ln=1)
    pdf.cell(0, 5, txt(f"Projekt/Betreff: {daten.get('problem_titel')}"), ln=1)
    pdf.ln(10)
    
    # Tabelle
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", 'B', 10)
    pdf.cell(10, 8, "#", 1, 0, 'C', 1)
    pdf.cell(90, 8, "Leistung / Artikel", 1, 0, 'L', 1)
    pdf.cell(20, 8, "Menge", 1, 0, 'C', 1)
    pdf.cell(30, 8, "Einzel", 1, 0, 'R', 1)
    pdf.cell(30, 8, "Gesamt", 1, 1, 'R', 1)
    
    # Positionen
    pdf.set_font("Helvetica", '', 10)
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
    
    # Summen
    pdf.ln(5)
    pdf.set_font("Helvetica", '', 11)
    netto = f"{daten.get('summe_netto', 0):.2f}".replace('.', ',')
    mwst = f"{daten.get('mwst_betrag', 0):.2f}".replace('.', ',')
    brutto = f"{daten.get('summe_brutto', 0):.2f}".replace('.', ',')
    
    pdf.cell(150, 6, "Netto Summe:", 0, 0, 'R'); pdf.cell(30, 6, f"{netto} EUR", 0, 1, 'R')
    pdf.cell(150, 6, "+ 19% MwSt:", 0, 0, 'R'); pdf.cell(30, 6, f"{mwst} EUR", 0, 1, 'R')
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(150, 10, "Gesamtsumme:", 0, 0, 'R'); pdf.cell(30, 10, f"{brutto} EUR", 0, 1, 'R')
    
    pdf.ln(10)
    pdf.set_font("Helvetica", '', 10)
    pdf.multi_cell(0, 5, txt("Dieser Arbeitsbericht dient als Leistungsnachweis."))
    
    timestamp = int(time.time())
    dateiname = f"Bericht_{rechnungs_nr}_{timestamp}.pdf"
    pdf.output(dateiname)
    return dateiname

# Secrets laden
api_key_default = st.secrets.get("openai_api_key", "")
email_sender_default = st.secrets.get("email_sender", "")
email_password_default = st.secrets.get("email_password", "")
smtp_server_default = st.secrets.get("smtp_server", "smtp.ionos.de")
smtp_port_default = st.secrets.get("smtp_port", 465)
google_json_raw = st.secrets.get("google_json", "")

# --- SEITENLEISTE ---
with st.sidebar:
    st.header("⚙️ System-Status")
    if api_key_default: st.success("✅ KI-System bereit")
    else: st.error("❌ KI-Key fehlt")
    api_key = api_key_default or st.text_input("OpenAI Key", type="password")
    
    google_creds = clean_json_string(google_json_raw)
    if google_creds: st.success("☁️ Cloud Speicher aktiv")
    else: st.error("❌ Google Key Fehler")
        
    blatt_name = st.text_input("Dateiname", value="Auftragsbuch")
    
    if email_sender_default: st.success("📧 E-Mail aktiv")
    else: st.info("E-Mail manuell:") 
    email_sender = email_sender_default or st.text_input("E-Mail")
    email_password = email_password_default or st.text_input("Passwort", type="password")
    smtp_server = smtp_server_default or st.text_input("SMTP Server", value="smtp.ionos.de")
    smtp_port = smtp_port_default or st.number_input("SMTP Port", value=465)
    email_receiver = st.text_input("Empfänger (Büro/DATEV)", value=email_sender)

client = None
if api_key: client = OpenAI(api_key=api_key)

# --- WEITERE FUNKTIONEN ---
def lade_preise_live():
    fallback_text = "PREISLISTE (Fallback): - Anfahrt: 22 EUR - Arbeitszeit: 77 EUR"
    if not google_creds: return fallback_text
    try:
        gc = gspread.service_account_from_dict(google_creds)
        sh = gc.open(blatt_name)
        try: ws = sh.worksheet("Preisliste")
        except: return fallback_text
        alle_daten = ws.get_all_values()
        if len(alle_daten) < 2: return fallback_text
        live_text = "AKTUELLE PREISLISTE (Live):\n"
        for zeile in alle_daten[1:]:
            if len(zeile) >= 2:
                artikel = zeile[0]
                preis = zeile[1].replace('€', '').replace('EUR', '').strip()
                if artikel and preis:
                    live_text += f"- {artikel}: {preis} EUR\n"
        return live_text
    except: return fallback_text

def audio_zu_text(dateipfad):
    audio_file = open(dateipfad, "rb")
    return client.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")

def text_zu_daten(rohtext, preisliste_text):
    system_befehl = f"""
    Du bist ein Buchhalter für Handwerker (Interwark).
    {preisliste_text}
    Aufgabe:
    1. Analysiere den Text. Suche passende Artikel aus der Preisliste.
    2. Wenn ein Artikel genannt wird, nutze EXAKT den Preis aus der Liste.
    3. Berechne Netto, 19% MwSt und Brutto.
    Gib JSON zurück:
    {{
      "kunde_name": "Name",
      "adresse": "Adresse",
      "problem_titel": "Betreff",
      "positionen": [ {{ "text": "Leistung", "menge": 1.0, "einzel_netto": 0.00, "gesamt_netto": 0.00 }} ],
      "summe_netto": 0.00, "mwst_betrag": 0.00, "summe_brutto": 0.00
    }}
    """
    response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_befehl}, {"role": "user", "content": rohtext}], response_format={"type": "json_object"})
    return json.loads(response.choices[0].message.content)

def hole_neue_rechnungsnummer():
    start_nummer = 2025001
    if not google_creds: return str(start_nummer)
    try:
        gc = gspread.service_account_from_dict(google_creds)
        sh = gc.open(blatt_name)
        worksheet = sh.get_worksheet(0)
        spalte_a = worksheet.col_values(1)
        if not spalte_a: return str(start_nummer)
        letzter_wert = spalte_a[-1]
        if letzter_wert.isdigit():
            neue_nummer = int(letzter_wert) + 1
            return str(neue_nummer)
        else: return str(start_nummer)
    except Exception as e:
        print(f"Fehler bei Nummerierung: {e}")
        return str(start_nummer)

def speichere_in_google_sheets(daten):
    try:
        if not google_creds: return False
        gc = gspread.service_account_from_dict(google_creds)
        sh = gc.open(blatt_name); worksheet = sh.get_worksheet(0)
        if not worksheet.get_all_values(): 
            worksheet.append_row(["Rechnungs-Nr", "Datum", "Kunde", "Arbeit", "Netto", "MwSt", "Brutto"])
        rechnungs_nr = daten.get('rechnungs_nr', '')
        neue_zeile = [
            rechnungs_nr,
            datetime.now().strftime("%d.%m.%Y"), 
            daten.get('kunde_name'), 
            daten.get('problem_titel'), 
            str(daten.get('summe_netto')).replace('.', ','), 
            str(daten.get('mwst_betrag')).replace('.', ','), 
            str(daten.get('summe_brutto')).replace('.', ',')
        ]
        worksheet.append_row(neue_zeile)
        return True
    except: return False

def sende_email_mit_pdf(pdf_pfad, daten):
    try:
        msg = MIMEMultipart()
        msg['From'] = email_sender
        msg['To'] = email_receiver
        msg['Subject'] = f"Bericht: {daten.get('kunde_name')}"
        msg.attach(MIMEText('Neuer Arbeitsbericht anbei.', 'plain'))
        with open(pdf_pfad, "rb") as f:
            p = MIMEBase("application", "pdf") 
            p.set_payload(f.read())
            encoders.encode_base64(p)
            filename = os.path.basename(pdf_pfad)
            p.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(p)
        if int(smtp_port) == 465: s = smtplib.SMTP_SSL(smtp_server, int(smtp_port))
        else: s = smtplib.SMTP(smtp_server, int(smtp_port)); s.starttls()
        s.login(email_sender, email_password); s.sendmail(email_sender, email_receiver, msg.as_string()); s.quit(); return True
    except Exception as e:
        print(f"Mail Fehler: {e}")
        return False

# --- APP START ---
# Wir ändern den Titel zurück auf den Original-Namen
st.title("✅ MeisterBot Final")
st.caption("Sprachnachricht hochladen -> PDF & DATEV-Daten erhalten")

uploaded_file = st.file_uploader("Sprachnachricht", type=["mp3", "wav", "m4a", "ogg", "opus"], label_visibility="collapsed")

if uploaded_file and api_key:
    preise_text = lade_preise_live()

    with st.spinner("⏳ Analysiere Audio & Berechne..."):
        with open(f"temp.{uploaded_file.name.split('.')[-1]}", "wb") as f: 
            f.write(uploaded_file.getbuffer())
        
        try:
            transkript = audio_zu_text(f.name)
            daten = text_zu_daten(transkript, preise_text)
            daten['rechnungs_nr'] = hole_neue_rechnungsnummer()

            st.markdown("---")
            c_info1, c_info2, c_info3 = st.columns(3)
            c_info1.metric("Kunde", daten.get('kunde_name', 'Unbekannt'))
            c_info2.metric("Nr.", daten.get('rechnungs_nr'))
            c_info3.metric("Brutto", f"{daten.get('summe_brutto'):.2f} €")
            
            pdf_datei = erstelle_bericht_pdf(daten)
            datev_csv_content = baue_datev_datei(daten)
            
            if speichere_in_google_sheets(daten): st.toast("✅ Gespeichert")
            
            # Downloads
            st.markdown("### 📥 Downloads")
            c_dl1, c_dl2 = st.columns(2)
            
            with open(pdf_datei, "rb") as f:
                c_dl1.download_button("📄 PDF Bericht", f, pdf_datei, "application/pdf")
            
            c_dl2.download_button("📊 DATEV CSV", datev_csv_content, f"DATEV_{daten.get('rechnungs_nr')}.csv", "text/csv")
                
        except Exception as e:
            st.error(f"Ein Fehler ist aufgetreten: {e}")
