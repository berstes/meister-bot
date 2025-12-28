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
st.set_page_config(page_title="MeisterBot", page_icon="📝")

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
    st.header("⚙️ System-Status")
    if api_key_default: st.success("✅ KI-System bereit")
    else: st.error("❌ KI-Key fehlt")
    api_key = api_key_default or st.text_input("OpenAI Key", type="password")
    
    google_creds = clean_json_string(google_json_raw)
    if google_creds: st.success("☁️ Cloud Speicher aktiv")
    else: st.error("❌ Google Key Fehler")
        
    blatt_name = st.text_input("Dateiname", value="Auftragsbuch")
    
    if email_sender_default: st.success("📧 E-Mail aktiv")
    else: st.info("E-Mail manuell:"); 
    email_sender = email_sender_default or st.text_input("E-Mail")
    email_password = email_password_default or st.text_input("Passwort", type="password")
    smtp_server = smtp_server_default or st.text_input("SMTP Server", value="smtp.ionos.de")
    smtp_port = smtp_port_default or st.number_input("SMTP Port", value=465)
    email_receiver = st.text_input("Empfänger (Büro/DATEV)", value=email_sender)

client = None
if api_key: client = OpenAI(api_key=api_key)

# --- 2. LIVE-PREISE ---

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
        # Spalte A = Name, Spalte B = Preis (ab Zeile 2)
        for zeile in alle_daten[1:]:
            if len(zeile) >= 2:
                artikel = zeile[0]
                preis = zeile[1].replace('€', '').replace('EUR', '').strip()
                if artikel and preis:
                    live_text += f"- {artikel}: {preis} EUR\n"
        return live_text
    except: return fallback_text

# --- 3. KI ---

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

# --- 4. PDF ---

class PDF(FPDF):
    def header(self):
        if os.path.exists("logo.png"): self.image("logo.png", 160, 8, 20)
        elif os.path.exists("logo.jpg"): self.image("logo.jpg", 160, 8, 20)
        self.set_font('Arial', 'B', 15)
        self.cell(80, 10, 'INTERWARK', 0, 1, 'L')
        self.set_font('Arial', '', 10)
        self.cell(80, 5, 'Bernhard Stegemann-Klammt', 0, 1, 'L')
        self.set_draw_color(200,200,200); self.line(10, 35, 200, 35); self.ln(20)
    def footer(self):
        self.set_y(-30); self.set_font('Arial', 'I', 8); self.set_text_color(128)
        self.cell(0, 4, 'Interwark | Vorlage für DATEV', 0, 1, 'L')

def erstelle_bericht_pdf(daten):
    pdf = PDF()
    pdf.add_page()
    
    # Hilfsfunktion für Sonderzeichen
    def txt(t): return str(t).encode('latin-1', 'replace').decode('latin-1') if t else ""
    
    # 1. Empfänger
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 5, txt(f"Kunde: {daten.get('kunde_name')}"), 0, 1)
    pdf.set_font("Arial", '', 12)
    pdf.multi_cell(0, 6, txt(f"{daten.get('adresse')}"))
    
    # 2. Titel & Datum & Betreff (NEU)
    pdf.ln(15) 
    
    # Zeile 1: Die Nummer
    pdf.set_font("Arial", 'B', 20)
    rechnungs_nr = daten.get('rechnungs_nr', 'ENTWURF') 
    pdf.cell(0, 10, txt(f"Arbeitsbericht Nr. {rechnungs_nr}"), 0, 1)
    
    # Zeile 2: Das Datum
    pdf.set_font("Arial", '', 10)
    datum_heute = datetime.now().strftime('%d.%m.%Y')
    pdf.cell(0, 5, txt(f"Arbeitsbericht Datum: {datum_heute}"), 0, 1)
    
    # Zeile 3: Projekt/Betreff
    pdf.cell(0, 5, txt(f"Projekt/Betreff: {daten.get('problem_titel')}"), 0, 1)
    
    pdf.ln(10) # Abstand zur Tabelle
    
    # 4. Tabelle Header
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(10, 8, "#", 1, 0, 'C', 1)
    pdf.cell(90, 8, "Leistung / Artikel", 1, 0, 'L', 1)
    pdf.cell(20, 8, "Menge", 1, 0, 'C', 1)
    pdf.cell(30, 8, "Einzel", 1, 0, 'R', 1)
    pdf.cell(30, 8, "Gesamt", 1, 1, 'R', 1)
    
    # 5. Positionen
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
    
    # 6. Summenblock
    netto = f"{daten.get('summe_netto', 0):.2f}".replace('.', ',')
    mwst = f"{daten.get('mwst_betrag', 0):.2f}".replace('.', ',')
    brutto = f"{daten.get('summe_brutto', 0):.2f}".replace('.', ',')
    
    pdf.ln(5)
    pdf.set_font("Arial", '', 11)
    pdf.cell(150, 6, "Netto Summe:", 0, 0, 'R')
    pdf.cell(30, 6, f"{netto} EUR", 0, 1, 'R')
    
    pdf.cell(150, 6, "+ 19% MwSt:", 0, 0, 'R')
    pdf.cell(30, 6, f"{mwst} EUR", 0, 1, 'R')
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(150, 10, "Gesamtsumme:", 0, 0, 'R')
    pdf.cell(30, 10, f"{brutto} EUR", 0, 1, 'R')
    
    # 7. Abschluss-Text
    pdf.ln(15)
    pdf.set_font("Arial", '', 10)
    pdf.multi_cell(0, 5, txt("Dieser Arbeitsbericht dient als Leistungsnachweis."))
    
    dateiname = f"Arbeitsbericht_{rechnungs_nr}.pdf"
    pdf.output(dateiname)
    return dateiname


# --- 5. SPEICHERN & SENDEN (FIX FÜR IPHONE) ---

def speichere_in_google_sheets(daten):
    try:
        if not google_creds: return False
        gc = gspread.service_account_from_dict(google_creds)
        sh = gc.open(blatt_name); worksheet = sh.get_worksheet(0)
        
        # Header anpassen: Rechnungs-Nr kommt nach vorne
        if not worksheet.get_all_values(): 
            worksheet.append_row(["Rechnungs-Nr", "Datum", "Kunde", "Arbeit", "Netto", "MwSt", "Brutto"])
        
        # Hier nutzen wir die Nummer, die wir vorher generiert und in 'daten' gespeichert haben
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
            # HIER IST DER FIX FÜR APPLE MAIL: "application/pdf"
            p = MIMEBase("application", "pdf") 
            p.set_payload(f.read())
            encoders.encode_base64(p)
            # Dateiname in Anführungszeichen setzen!
            filename = os.path.basename(pdf_pfad)
            p.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(p)

        if int(smtp_port) == 465: s = smtplib.SMTP_SSL(smtp_server, int(smtp_port))
        else: s = smtplib.SMTP(smtp_server, int(smtp_port)); s.starttls()
        s.login(email_sender, email_password); s.sendmail(email_sender, email_receiver, msg.as_string()); s.quit(); return True
    except Exception as e:
        print(f"Mail Fehler: {e}")
        return False

def hole_neue_rechnungsnummer():
    # Standard-Startnummer für das neue Jahr (Jahr + 3 Ziffern)
    start_nummer = 2025001
    
    if not google_creds: 
        return str(start_nummer) # Fallback ohne Cloud
    
    try:
        gc = gspread.service_account_from_dict(google_creds)
        sh = gc.open(blatt_name)
        worksheet = sh.get_worksheet(0)
        
        # Wir nehmen an, die Nummer steht in Spalte A (Index 1)
        spalte_a = worksheet.col_values(1)
        
        if not spalte_a:
            return str(start_nummer)
            
        letzter_wert = spalte_a[-1]
        
        # Prüfen, ob der letzte Wert eine Zahl ist (Header "Rechnungs-Nr" überspringen)
        if letzter_wert.isdigit():
            neue_nummer = int(letzter_wert) + 1
            return str(neue_nummer)
        else:
            # Falls da "Datum" oder Text steht, fangen wir neu an
            return str(start_nummer)
    except Exception as e:
        print(f"Fehler bei Nummerierung: {e}")
        return str(start_nummer)


# --- APP START ---
st.title("📝 MeisterBot")
st.caption("Sprachnachricht hochladen -> PDF & DATEV-Daten erhalten")

uploaded_file = st.file_uploader("Sprachnachricht", type=["mp3", "wav", "m4a", "ogg", "opus"], label_visibility="collapsed")

if uploaded_file and api_key:
    preise_text = lade_preise_live()

    with st.spinner("⏳ Analysiere Audio & Berechne..."):
        # Temporäre Datei speichern
        with open(f"temp.{uploaded_file.name.split('.')[-1]}", "wb") as f: 
            f.write(uploaded_file.getbuffer())
        
        try:
            # 1. KI-Analyse
            transkript = audio_zu_text(f.name)
            daten = text_zu_daten(transkript, preise_text)
            
            # 2. Nummer holen (WICHTIG: Damit 'ENTWURF' weggeht)
            daten['rechnungs_nr'] = hole_neue_rechnungsnummer()

            st.markdown("---")
            
            # 3. Anzeige
            c_info1, c_info2, c_info3 = st.columns(3)
            c_info1.metric("Kunde", daten.get('kunde_name', 'Unbekannt'))
            c_info2.metric("Nr.", daten.get('rechnungs_nr'))
            c_info3.metric("Brutto", f"{daten.get('summe_brutto'):.2f} €")
            
            # 4. PDF & CSV erstellen
            pdf_datei = erstelle_bericht_pdf(daten)
            datev_csv_content = erstelle_datev_csv(daten)
            
            # 5. Speichern
            if speichere_in_google_sheets(daten): st.toast("✅ In Google Sheets gespeichert")
            else: st.toast("⚠️ Fehler beim Speichern (Google)")
                
            if email_sender: 
                if sende_email_mit_pdf(pdf_datei, daten): st.toast("📧 E-Mail versendet")
            
            # 6. DOWNLOADS (Hier war der Fehler!)
            st.markdown("### 📥 Downloads")
            
            # HIER definieren wir die Spalten c_dl1 und c_dl2:
            c_dl1, c_dl2 = st.columns(2)
            
            # Button 1: PDF
            with open(pdf_datei, "rb") as f:
                c_dl1.download_button(
                    label="📄 Arbeitsbericht PDF",
                    data=f,
                    file_name=f"Arbeitsbericht_{daten.get('rechnungs_nr')}.pdf",
                    mime="application/pdf",
                )
            
            # Button 2: DATEV
            c_dl2.download_button(
                label="📊 DATEV Export (CSV)",
                data=datev_csv_content,
                file_name=f"DATEV_Buchung_{daten.get('rechnungs_nr')}.csv",
                mime="text/csv",
            )
                
        except Exception as e:
            st.error(f"Ein Fehler ist aufgetreten: {e}")









