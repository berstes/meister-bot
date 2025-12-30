import streamlit as st
import os
import json
import time
import smtplib
from datetime import datetime

# --- 1. SICHERHEITS-START ---
api_key = None
client = None
email_sender = None
email_receiver = None
smtp_server = "smtp.ionos.de"
smtp_port = 465
email_password = None
google_creds = None
blatt_name = "Auftragsbuch"

try:
    import pandas as pd
    import gspread
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders
    from openai import OpenAI
    from fpdf import FPDF
except ImportError as e:
    st.error(f"Fehler beim Laden von Modulen: {e}")
    st.stop()

# --- 2. KONFIGURATION ---
# Version hochgezählt
st.set_page_config(page_title="Auftrags- und Arbeitsberichte App Vers. 3.3.0", page_icon="📝")

# --- 3. HELFER ---
def clean_json_string(s):
    if not s: return ""
    try: return json.loads(s)
    except:
        try: return json.loads(s, strict=False)
        except: pass
    fixed = s.replace('\n', '\\n').replace('\r', '')
    try: return json.loads(fixed)
    except: return None

# --- 4. SEITENLEISTE ---
with st.sidebar:
    st.header("⚙️ Einstellungen")
    if st.button("🔄 App Reset / Neu laden"):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    
    modus = st.radio("Modus:", ("Chef-Dashboard", "Bericht & DATEV erstellen", "Auftrag annehmen"))
    st.markdown("---")
    
    api_key_default = st.secrets.get("openai_api_key", "")
    if api_key_default:
        api_key = api_key_default
        st.success("✅ KI aktiv")
    else:
        api_key = st.text_input("OpenAI Key", type="password")

    google_json_raw = st.secrets.get("google_json", "")
    google_creds = clean_json_string(google_json_raw)
    if google_creds: st.success("☁️ Cloud aktiv")
    
    blatt_name = st.text_input("Google Sheet Name", value="Auftragsbuch")
    
    email_sender = st.secrets.get("email_sender", "")
    email_password = st.secrets.get("email_password", "")
    smtp_server = st.secrets.get("smtp_server", "smtp.ionos.de")
    smtp_port = st.secrets.get("smtp_port", 465)
    
    if email_sender: 
        st.success("📧 Mail aktiv")
        email_receiver = st.text_input("Empfänger", value=email_sender)

# --- 5. CLIENT ---
if api_key:
    try:
        client = OpenAI(api_key=api_key)
    except Exception as e:
        st.error(f"Fehler: {e}")

# --- 6. LOGIK ---

def lade_statistik_daten():
    """Lädt Statistik extrem robust und fehlertolerant."""
    if not google_creds: return 0.0, 0, 0, None
    try:
        gc = gspread.service_account_from_dict(google_creds)
        sh = gc.open(blatt_name)
        
        ws_rechnungen = sh.get_worksheet(0)
        alle_werte = ws_rechnungen.get_all_values()
        
        if len(alle_werte) < 2:
            return 0.0, 0, 0, None
            
        raw_headers = alle_werte[0]
        headers_clean = [str(h).strip() for h in raw_headers]
        
        df = pd.DataFrame(alle_werte[1:], columns=headers_clean)
        
        col_datum = next((c for c in df.columns if "datum" in c.lower()), None)
        col_brutto = next((c for c in df.columns if "brutto" in c.lower()), None)
        
        if not col_datum or not col_brutto:
            return 0.0, 0, 0, None

        df['Datum_Clean'] = pd.to_datetime(df[col_datum], format='%d.%m.%Y', errors='coerce')
        df = df.dropna(subset=['Datum_Clean']) 

        def putze_geld(x):
            if not isinstance(x, str): return 0.0
            sauber = x.replace('€', '').replace('EUR', '').strip()
            sauber = sauber.replace('.', '').replace(',', '.')
            try: return float(sauber)
            except: return 0.0
            
        df['Brutto_Zahl'] = df[col_brutto].apply(putze_geld)
        
        heute = pd.Timestamp.now()
        df_monat = df[(df['Datum_Clean'].dt.month == heute.month) & (df['Datum_Clean'].dt.year == heute.year)]
        umsatz_monat = df_monat['Brutto_Zahl'].sum()
        
        anzahl_heute = len(df[df['Datum_Clean'].dt.date == heute.date()])
        
        aktuelle_kw = heute.isocalendar()[1]
        df['KW'] = df['Datum_Clean'].dt.isocalendar().week
        anzahl_woche = len(df[(df['KW'] == aktuelle_kw) & (df['Datum_Clean'].dt.year == heute.year)])
        
        df['Monat_Jahr'] = df['Datum_Clean'].dt.strftime('%Y-%m')
        df = df.sort_values('Datum_Clean')
        chart_data = df.groupby('Monat_Jahr')['Brutto_Zahl'].sum().tail(6)
        
        return umsatz_monat, anzahl_heute, anzahl_woche, chart_data

    except Exception as e:
        return 0.0, 0, 0, None

def lade_kunden_live():
    if not google_creds: return "Keine Cloud."
    try:
        gc = gspread.service_account_from_dict(google_creds)
        sh = gc.open(blatt_name)
        try: ws = sh.worksheet("Kunden")
        except: return "Hinweis: Tabellenblatt 'Kunden' fehlt."
        alle_daten = ws.get_all_values()
        if len(alle_daten) < 2: return "Keine Kunden."
        kunden_text = "BEKANNTE KUNDEN:\n"
        for zeile in alle_daten[1:]:
            if len(zeile) >= 1:
                name = zeile[0]
                strasse = zeile[1] if len(zeile) > 1 else ""
                plz = zeile[2] if len(zeile) > 2 else ""
                ort = zeile[3] if len(zeile) > 3 else ""
                kd_nr = zeile[4] if len(zeile) > 4 else ""
                anrede = zeile[5] if len(zeile) > 5 else "" 
                kunden_text += f"- Name: {name} | Anrede: {anrede} | Adresse: {strasse}, {plz} {ort} | KdNr: {kd_nr}\n"
        return kunden_text
    except Exception as e: return f"Fehler DB: {e}"

def lade_preise_live():
    """Liest Preise + Artikelnummer (Spalte C)"""
    if not google_creds: return "Preise: Standard"
    try:
        gc = gspread.service_account_from_dict(google_creds)
        sh = gc.open(blatt_name); ws = sh.worksheet("Preisliste")
        alle = ws.get_all_values(); txt = "PREISLISTE:\n"
        for z in alle[1:]:
            if len(z) >= 2:
                name = z[0]
                preis = z[1]
                art_nr = z[2] if len(z) > 2 else "" 
                
                if art_nr:
                    txt += f"- Art. {art_nr}: {name} ({preis} EUR)\n"
                else:
                    txt += f"- {name}: {preis} EUR\n"
        return txt
    except: return "Preise: Standard"

def audio_zu_text(pfad):
    f = open(pfad, "rb")
    return client.audio.transcriptions.create(model="whisper-1", file=f, response_format="text")

def text_zu_daten(txt, preise, kunden_db):
    sys = f"""
    Du bist Buchhalter.
    PREISE (Format: Art.Nr: Name Preis):
    {preise}
    KUNDEN: {kunden_db}
    
    AUFGABE: JSON erstellen.
    - Wenn du einen Artikel aus der Preisliste erkennst, schreibe die Artikelnummer oder den exakten Namen in 'text'.
    
    Format: {{'anrede': 'Herr/Frau', 'kunde_name': 'Name', 'adresse': 'Str, PLZ Ort', 'kundennummer': '1000', 'problem_titel': 'Betreff', 'positionen': [{{'text':'L', 'menge':1.0, 'einzel_netto':0.0, 'gesamt_netto':0.0}}], 'summe_netto':0.0, 'mwst_betrag':0.0, 'summe_brutto':0.0}}
    """
    res = client.chat.completions.create(model="gpt-4o", messages=[{"role":"system","content":sys},{"role":"user","content":txt}], response_format={"type":"json_object"})
    return json.loads(res.choices[0].message.content)

def text_zu_auftrag(txt, kunden_db):
    sys = f"Du bist Sekretär. KUNDEN: {kunden_db}. JSON: {{'kunde_name':'Name', 'anrede':'Herr/Frau', 'adresse':'Adr', 'kontakt':'Tel', 'problem':'Prob', 'termin':'Wann'}}"
    res = client.chat.completions.create(model="gpt-4o", messages=[{"role":"system","content":sys},{"role":"user","content":txt}], response_format={"type":"json_object"})
    return json.loads(res.choices[0].message.content)

def hole_nr():
    # --- ÄNDERUNG: Neues Nummerierungsformat B-YYYY-MM-01 ---
    now = datetime.now()
    jahr = now.strftime("%Y")
    monat = now.strftime("%m")
    prefix = f"B-{jahr}-{monat}"  # z.B. B-2026-01
    
    start_nr = f"{prefix}-01"

    if not google_creds: 
        return start_nr
        
    try:
        gc = gspread.service_account_from_dict(google_creds)
        sh = gc.open(blatt_name)
        ws = sh.get_worksheet(0)
        col = ws.col_values(1) # Spalte A (Nr)
        
        if not col or len(col) < 2:
            return start_nr
            
        last_entry = col[-1] # Letzter Eintrag, z.B. "B-2026-01-05" oder altes Format "2025001"
        
        # Wir prüfen, ob der letzte Eintrag das neue Format hat und vom selben Monat ist
        if last_entry.startswith(prefix):
            try:
                # Format splitten: B-2026-01-05 -> ["B", "2026", "01", "05"]
                parts = last_entry.split('-')
                if len(parts) == 4:
                    nummer = int(parts[3])
                    neue_nummer = nummer + 1
                    # Formatierung: führende Null wenn < 10 (01, 02...)
                    return f"{prefix}-{neue_nummer:02d}"
            except:
                pass # Falls Parsing fehlschlägt, Fallback nutzen
        
        # Falls neuer Monat oder altes Format -> Reset auf 01
        return start_nr

    except Exception as e:
        return start_nr

def baue_datev_datei(daten):
    umsatz = f"{daten.get('summe_brutto', 0):.2f}".replace('.', ',')
    datum = datetime.now().strftime("%d%m")
    rechnungs_nr = daten.get('rechnungs_nr', datetime.now().strftime("%y%m%d%H%M"))
    raw_text = f"{daten.get('kunde_name')} {daten.get('problem_titel')}"
    buchungstext = raw_text.replace(";", " ")[:60]
    gegenkonto = daten.get('kundennummer')
    if not gegenkonto or str(gegenkonto) == "None": gegenkonto = "1410"
    header = "Umsatz (ohne Soll/Haben-Kz);Soll/Haben-Kennzeichen;WKZ;Konto;Gegenkonto (ohne BU-Schlüssel);Belegdatum;Belegfeld 1;Buchungstext"
    line = f"{umsatz};S;EUR;8400;{gegenkonto};{datum};{rechnungs_nr};{buchungstext}"
    return f"{header}\n{line}"

class PDF(FPDF):
    def header(self): pass
    def footer(self):
        self.set_y(-20)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 4, 'Interwark | Vorlage für DATEV', 0, 1, 'L')

def erstelle_bericht_pdf(daten):
    pdf = PDF(); pdf.add_page()
    def txt(t): return str(t).encode('latin-1', 'replace').decode('latin-1') if t else ""

    pdf.set_text_color(0, 0, 0)
    if os.path.exists("logo.png"): pdf.image("logo.png", 160, 10, 20)
    elif os.path.exists("logo.jpg"): pdf.image("logo.jpg", 160, 10, 20)

    pdf.set_font('Helvetica', 'B', 16); pdf.set_xy(10, 10); pdf.cell(0, 10, 'INTERWARK', 0, 0, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_xy(10, 18); pdf.cell(0, 5, 'Bernhard Stegemann-Klammt', 0, 0, 'L')
    pdf.set_xy(10, 23); pdf.cell(0, 5, 'Hohe Str. 26', 0, 0, 'L')
    pdf.set_xy(10, 28); pdf.cell(0, 5, '26725 Emden', 0, 0, 'L')
    pdf.set_xy(10, 33); pdf.cell(0, 5, 'info@interwark.de', 0, 0, 'L')
    pdf.set_draw_color(0, 0, 0); pdf.line(10, 42, 200, 42)
    
    pdf.set_y(55)
    pdf.set_font("Helvetica", 'B', 12)
    anrede = daten.get('anrede', '')
    if anrede and anrede != "None": pdf.cell(0, 5, txt(anrede), ln=1)
    pdf.cell(0, 5, txt(daten.get('kunde_name')), ln=1)
    
    kd = daten.get('kundennummer', '')
    if kd: 
        pdf.set_font("Helvetica", '', 9)
        pdf.cell(0, 5, txt(f"Kundennr.: {kd}"), ln=1)
        pdf.set_font("Helvetica", 'B', 12)
        
    pdf.set_font("Helvetica", '', 12); pdf.multi_cell(0, 6, txt(f"{daten.get('adresse')}"))
    
    # --- ÄNDERUNG: Schriftgröße von 20 auf 18 verkleinert ---
    pdf.ln(10); pdf.set_font("Helvetica", 'B', 18)
    rechnungs_nr = daten.get('rechnungs_nr', 'ENTWURF') 
    pdf.cell(0, 10, txt(f"Arbeitsbericht Nr. {rechnungs_nr}"), ln=1)
    
    pdf.set_font("Helvetica", '', 10)
    datum_heute = datetime.now().strftime('%d.%m.%Y')
    pdf.cell(0, 5, txt(f"Datum: {datum_heute}"), ln=1)
    pdf.cell(0, 5, txt(f"Betreff: {daten.get('problem_titel')}"), ln=1)
    pdf.ln(10)
    
    pdf.set_fill_color(240, 240, 240); pdf.set_font("Helvetica", 'B', 10)
    pdf.cell(10, 8, "#", 1, 0, 'C', 1); pdf.cell(90, 8, "Leistung / Artikel", 1, 0, 'L', 1)
    pdf.cell(20, 8, "Menge", 1, 0, 'C', 1); pdf.cell(30, 8, "Einzel", 1, 0, 'R', 1)
    pdf.cell(30, 8, "Gesamt", 1, 1, 'R', 1)
    
    pdf.set_font("Helvetica", '', 10); i = 1
    for pos in daten.get('positionen', []):
        text = txt(pos.get('text', '')); menge = str(pos.get('menge', ''))
        einzel = f"{pos.get('einzel_netto', 0):.2f}".replace('.', ','); gesamt = f"{pos.get('gesamt_netto', 0):.2f}".replace('.', ',')
        pdf.cell(10, 8, str(i), 1, 0, 'C'); pdf.cell(90, 8, text, 1, 0, 'L'); pdf.cell(20, 8, menge, 1, 0, 'C')
        pdf.cell(30, 8, einzel, 1, 0, 'R'); pdf.cell(30, 8, gesamt, 1, 1, 'R'); i += 1
    
    pdf.ln(5); pdf.set_font("Helvetica", '', 11)
    netto = f"{daten.get('summe_netto', 0):.2f}".replace('.', ',')
    mwst = f"{daten.get('mwst_betrag', 0):.2f}".replace('.', ',')
    brutto = f"{daten.get('summe_brutto', 0):.2f}".replace('.', ',')
    pdf.cell(150, 6, "Netto Summe:", 0, 0, 'R'); pdf.cell(30, 6, f"{netto} EUR", 0, 1, 'R')
    pdf.cell(150, 6, "+ 19% MwSt:", 0, 0, 'R'); pdf.cell(30, 6, f"{mwst} EUR", 0, 1, 'R')
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(150, 10, "Gesamtsumme:", 0, 0, 'R'); pdf.cell(30, 10, f"{brutto} EUR", 0, 1, 'R')
    
    pdf.ln(15); pdf.set_font("Helvetica", 'I', 9)
    hinweis = "Hinweis: Dieses Dokument dient als Leistungsnachweis und Buchungsvorlage.\nKeine Rechnung im Sinne des §14 UStG."
    pdf.multi_cell(0, 5, txt(hinweis))
    
    pdf.ln(5); pdf.set_font("Helvetica", '', 8)
    bank_info = "Bank: Sparkasse Emden | IBAN: DE00 0000 0000 0000 0000 00"
    pdf.cell(0, 5, txt(bank_info), 0, 1, 'C')
    
    ts = int(time.time()); dateiname = f"Bericht_{rechnungs_nr}_{ts}.pdf"
    pdf.output(dateiname); return dateiname

def speichere_rechnung(d):
    if not google_creds: return False
    try:
        gc = gspread.service_account_from_dict(google_creds); sh = gc.open(blatt_name); ws = sh.get_worksheet(0)
        if not ws.get_all_values(): 
            ws.append_row(["Nr", "Datum", "Kunde", "Arbeit", "Netto", "MwSt", "Brutto", "KdNr"])
        ws.append_row([d.get('rechnungs_nr'), datetime.now().strftime("%d.%m.%Y"), d.get('kunde_name'), d.get('problem_titel'), str(d.get('summe_netto')).replace('.',','), str(d.get('mwst_betrag')).replace('.',','), str(d.get('summe_brutto')).replace('.',','), d.get('kundennummer', '')])
        return True
    except: return False

def speichere_auftrag(d):
    if not google_creds: return False
    try:
        gc = gspread.service_account_from_dict(google_creds); sh = gc.open(blatt_name)
        try: ws = sh.worksheet("Offene Aufträge")
        except: ws = sh.add_worksheet("Offene Aufträge", 100, 10)
        if not ws.get_all_values(): ws.append_row(["Datum", "Kunde", "Adresse", "Kontakt", "Problem", "Termin"])
        ws.append_row([datetime.now().strftime("%d.%m.%Y"), d.get('kunde_name'), d.get('adresse'), d.get('kontakt'), d.get('problem'), d.get('termin')])
        return True
    except: return False

def sende_mail(pfad, d):
    try:
        msg = MIMEMultipart(); msg['From']=email_sender; msg['To']=email_receiver; msg['Subject']=f"Bericht: {d.get('kunde_name')}"
        with open(pfad, "rb") as f:
            p = MIMEBase("application", "pdf"); p.set_payload(f.read()); encoders.encode_base64(p)
            p.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(pfad)}"')
            msg.attach(p)
        s = smtplib.SMTP_SSL(smtp_server, int(smtp_port)) if int(smtp_port)==465 else smtplib.SMTP(smtp_server, int(smtp_port))
        if int(smtp_port)!=465: s.starttls()
        s.login(email_sender, email_password); s.sendmail(email_sender, email_receiver, msg.as_string()); s.quit(); return True
    except: return False

# --- 7. HAUPTPROGRAMM ---
# Version Update
st.title("Auftrags- und Arbeitsberichte App 3.3.0")

if modus == "Chef-Dashboard":
    st.markdown("### 👋 Moin Chef! Hier ist der Überblick.")
    
    if api_key and google_creds:
        with st.spinner("Lade Zahlen..."):
            
            umsatz, anzahl_heute, anzahl_woche, chart_data = lade_statistik_daten()
            
            if isinstance(umsatz, str) and umsatz.startswith("Fehler"):
                st.error(umsatz)
            else:
                k1, k2, k3 = st.columns(3)
                if not isinstance(umsatz, (int, float)): umsatz = 0.0
                
                k1.metric("Umsatz (Monat)", f"{umsatz:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
                k2.metric("Aufträge (Heute)", str(anzahl_heute))
                k3.metric("Aufträge (Woche)", str(anzahl_woche))
                
                st.markdown("---")
                st.subheader("📈 Umsatzverlauf")
                if chart_data is not None and not chart_data.empty:
                    st.bar_chart(chart_data)
                else:
                    st.info("Noch nicht genug Daten für ein Diagramm.")
    else:
        st.warning("Bitte erst API Keys eintragen.")

elif modus == "Bericht & DATEV erstellen":
    st.caption("Modus: 🔵 Arbeitsbericht erstellen")
    f = st.file_uploader("Sprachnachricht", type=["mp3","wav","m4a","ogg","opus"], label_visibility="collapsed")

    if f and api_key and client:
        dateiendung = f.name.split('.')[-1]
        temp_filename = f"temp_audio.{dateiendung}"
        
        with st.spinner("⏳ Erstelle Bericht..."):
            with open(temp_filename, "wb") as file: file.write(f.getbuffer())
            try:
                txt = audio_zu_text(temp_filename)
                preise = lade_preise_live()
                kunden = lade_kunden_live() 
                dat = text_zu_daten(txt, preise, kunden)
                dat['rechnungs_nr'] = hole_nr()
                
                st.markdown("---")
                c1, c2, c3 = st.columns(3)
                c1.metric("Kunde", dat.get('kunde_name')); c2.metric("Nr.", dat.get('rechnungs_nr')); c3.metric("Brutto", f"{dat.get('summe_brutto'):.2f} €")
                
                if dat.get('kundennummer'):
                    st.success(f"✅ Stammkunde: {dat.get('anrede')} {dat.get('kunde_name')}")
                
                pdf = erstelle_bericht_pdf(dat)
                csv = baue_datev_datei(dat)
                
                if speichere_rechnung(dat): st.toast("✅ Gespeichert")
                
                st.markdown("### 📥 Downloads")
                c_a, c_b = st.columns(2)
                with open(pdf, "rb") as file: c_a.download_button("📄 PDF Bericht", file, pdf, "application/pdf")
                c_b.download_button("📊 DATEV", csv, f"DATEV_{dat.get('rechnungs_nr')}.csv", "text/csv")
                
                if email_sender: 
                    if sende_mail(pdf, dat): st.toast("📧 Mail raus")
            except Exception as e: st.error(f"Fehler: {e}")

else: 
    st.caption("Modus: 🟠 Neuen Auftrag anlegen")
    f = st.file_uploader("Sprachnachricht", type=["mp3","wav","m4a","ogg","opus"], label_visibility="collapsed")

    if f and api_key and client:
        dateiendung = f.name.split('.')[-1]
        temp_filename = f"temp_audio.{dateiendung}"
        with st.spinner("⏳ Erfasse Auftrag..."):
            with open(temp_filename, "wb") as file: file.write(f.getbuffer())
            try:
                txt = audio_zu_text(temp_filename)
                kunden = lade_kunden_live()
                auf = text_zu_auftrag(txt, kunden)
                st.success(f"Auftrag von {auf.get('kunde_name')}")
                st.json(auf)
                if speichere_auftrag(auf): st.toast("✅ Auftrag notiert"); st.info("In 'Offene Aufträge' gespeichert.")
            except Exception as e: st.error(f"Fehler: {e}")
