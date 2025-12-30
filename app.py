import streamlit as st
import os
import json
import time
import smtplib
import urllib.parse
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
st.set_page_config(page_title="Auftrags- und Arbeitsberichte App Vers. 3.9.1", page_icon="📝")

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
        for key in list(st.session_state.keys()):
            del st.session_state[key]
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
    if not google_creds: return 0.0, 0, 0, None
    try:
        gc = gspread.service_account_from_dict(google_creds)
        sh = gc.open(blatt_name)
        ws_rechnungen = sh.get_worksheet(0)
        alle_werte = ws_rechnungen.get_all_values()
        if len(alle_werte) < 2: return 0.0, 0, 0, None
        raw_headers = alle_werte[0]
        headers_clean = [str(h).strip() for h in raw_headers]
        df = pd.DataFrame(alle_werte[1:], columns=headers_clean)
        col_datum = next((c for c in df.columns if "datum" in c.lower()), None)
        col_brutto = next((c for c in df.columns if "brutto" in c.lower()), None)
        if not col_datum or not col_brutto: return 0.0, 0, 0, None
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
    except Exception as e: return 0.0, 0, 0, None

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
                if art_nr: txt += f"- Art. {art_nr}: {name} ({preis} EUR)\n"
                else: txt += f"- {name}: {preis} EUR\n"
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
    Format: {{'anrede': 'Herr/Frau', 'kunde_name': 'Name', 'adresse': 'Str, PLZ Ort', 'kundennummer': '1000', 'problem_titel': 'Betreff', 'positionen': [{{'text':'L', 'menge':1.0, 'einzel_netto':0.0}}], 'summe_netto':0.0, 'mwst_betrag':0.0, 'summe_brutto':0.0}}
    """
    res = client.chat.completions.create(model="gpt-4o", messages=[{"role":"system","content":sys},{"role":"user","content":txt}], response_format={"type":"json_object"})
    return json.loads(res.choices[0].message.content)

def text_zu_auftrag(txt, kunden_db):
    sys = f"Du bist Sekretär. KUNDEN: {kunden_db}. JSON: {{'kunde_name':'Name', 'anrede':'Herr/Frau', 'adresse':'Adr', 'kontakt':'Tel', 'problem':'Prob', 'termin':'Wann'}}"
    res = client.chat.completions.create(model="gpt-4o", messages=[{"role":"system","content":sys},{"role":"user","content":txt}], response_format={"type":"json_object"})
    return json.loads(res.choices[0].message.content)

def hole_nr():
    now = datetime.now()
    jahr = now.strftime("%Y")
    monat = now.strftime("%m")
    prefix = f"B-{jahr}-{monat}"
    start_nr = f"{prefix}-01"
    if not google_creds: return start_nr
    try:
        gc = gspread.service_account_from_dict(google_creds); sh = gc.open(blatt_name); ws = sh.get_worksheet(0)
        col = ws.col_values(1)
        if not col or len(col) < 2: return start_nr
        last_entry = col[-1]
        if last_entry.startswith(prefix):
            try:
                parts = last_entry.split('-')
                if len(parts) == 4:
                    nummer = int(parts[3])
                    neue_nummer = nummer + 1
                    return f"{prefix}-{neue_nummer:02d}"
            except: pass
        return start_nr
    except Exception as e: return start_nr

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
        self.set_y(-35)
        self.set_fill_color(248, 248, 248) 
        self.rect(0, 297-35, 210, 35, 'F') 
        c_head = (20, 80, 160) # Blau
        c_text = (50, 50, 50)  # Dunkelgrau
        def txt(t): return str(t).encode('latin-1', 'replace').decode('latin-1') if t else ""
        y_top = 297 - 30 
        
        # --- FUSSZEILE GRÖSSEN ---
        self.set_xy(10, y_top); self.set_text_color(*c_head); self.set_font('Helvetica', 'B', 7.5); self.cell(45, 3.5, txt("Firma"), 0, 2, 'L')
        self.set_text_color(*c_text); self.set_font('Helvetica', '', 6.5); self.multi_cell(45, 3.5, txt("Interwark\nEinzelunternehmen\nMobil: (0171) 1 42 87 38"), 0, 'L')
        
        self.set_xy(60, y_top); self.set_text_color(*c_head); self.set_font('Helvetica', 'B', 7.5); self.cell(45, 3.5, txt("KONTAKT"), 0, 2, 'L')
        self.set_xy(60, self.get_y()); self.set_text_color(*c_text); self.set_font('Helvetica', '', 6.5); self.multi_cell(45, 3.5, txt("Hohe Str. 28\n26725 Emden\nTel: (0 49 21) 99 71 30\ninfo@interwark.de"), 0, 'L')
        
        self.set_xy(110, y_top); self.set_text_color(*c_head); self.set_font('Helvetica', 'B', 7.5); self.cell(45, 3.5, txt("BANKVERBINDUNG"), 0, 2, 'L')
        self.set_xy(110, self.get_y()); self.set_text_color(*c_text); self.set_font('Helvetica', '', 6.5); self.multi_cell(45, 3.5, txt("Sparkasse Emden\nIBAN: DE92 2845 0000 0018\n0048 61\nBIC: BRLADE21EMD"), 0, 'L')
        
        self.set_xy(160, y_top); self.set_text_color(*c_head); self.set_font('Helvetica', 'B', 7.5); self.cell(45, 3.5, txt("STEUERNUMMER"), 0, 2, 'L')
        self.set_xy(160, self.get_y()); self.set_text_color(*c_text); self.set_font('Helvetica', '', 6.5); self.multi_cell(45, 3.5, txt("USt-IdNr.:\nDE226723406\nGerichtsstand: Emden"), 0, 'L')

def erstelle_bericht_pdf(daten):
    pdf = PDF(); pdf.add_page()
    def txt(t): return str(t).encode('latin-1', 'replace').decode('latin-1') if t else ""

    pdf.set_text_color(0, 0, 0)
    if os.path.exists("logo.png"): pdf.image("logo.png", 160, 10, 17)
    elif os.path.exists("logo.jpg"): pdf.image("logo.jpg", 160, 10, 17)

    pdf.set_font('Helvetica', 'B', 14); pdf.set_xy(10, 10); pdf.cell(0, 10, 'INTERWARK', 0, 0, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_xy(10, 18); pdf.cell(0, 5, 'Bernhard Stegemann-Klammt', 0, 0, 'L')
    pdf.set_xy(10, 23); pdf.cell(0, 5, 'Hohe Str. 28', 0, 0, 'L') 
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
        pdf.set_font("Helvetica", '', 9); pdf.cell(0, 5, txt(f"Kundennr.: {kd}"), ln=1); pdf.set_font("Helvetica", 'B', 12)
    pdf.set_font("Helvetica", '', 12); pdf.multi_cell(0, 6, txt(f"{daten.get('adresse')}"))
    
    pdf.ln(10); pdf.set_font("Helvetica", 'B', 15)
    rechnungs_nr = daten.get('rechnungs_nr', 'ENTWURF') 
    pdf.cell(0, 10, txt(f"Arbeitsbericht Nr. {rechnungs_nr}"), ln=1)
    
    pdf.set_font("Helvetica", '', 10)
    datum_heute = datetime.now().strftime('%d.%m.%Y')
    pdf.cell(0, 5, txt(f"Datum: {datum_heute}"), ln=1)
    pdf.cell(0, 5, txt(f"Betreff: {daten.get('problem_titel')}"), ln=1)
    pdf.ln(10)
    
    pdf.set_fill_color(240, 240, 240); pdf.set_font("Helvetica", 'B', 10)
    pdf.cell(10, 8, "#", 1, 0, 'C', 1); pdf.cell(90, 8, "Leistung / Artikel", 1, 0, 'L', 1)
    pdf.cell(20, 8, "Menge", 1, 0, 'C', 1); pdf.cell(30, 8, "Einzel", 1, 0, 'R', 1); pdf.cell(30, 8, "Gesamt", 1, 1, 'R', 1)
    
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
    
    ts = int(time.time()); dateiname = f"Bericht_{rechnungs_nr}_{ts}.pdf"
    pdf.output(dateiname); return dateiname

def speichere_rechnung(d):
    if not google_creds: return False
    try:
        gc = gspread.service_account_from_dict(google_creds); sh = gc.open(blatt_name); ws = sh.get_worksheet(0)
        if not ws.get_all_values(): ws.append_row(["Nr", "Datum", "Kunde", "Arbeit", "Netto", "MwSt", "Brutto", "KdNr"])
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

def berechne_summen(df_pos):
    summe_netto = 0.0; positions_liste = []
    for _, row in df_pos.iterrows():
        try:
            m = float(row['menge']); e = float(row['einzel_netto']); g = m * e; summe_netto += g
            positions_liste.append({"text": row['text'], "menge": m, "einzel_netto": e, "gesamt_netto": g})
        except: pass
    mwst = summe_netto * 0.19; brutto = summe_netto + mwst
    return positions_liste, summe_netto, mwst, brutto

# --- 7. HAUPTPROGRAMM ---
st.title("Auftrags- und Arbeitsberichte App 3.9.1")

if modus == "Chef-Dashboard":
    st.markdown("### 👋 Moin Chef! Hier ist der Überblick.")
    if api_key and google_creds:
        with st.spinner("Lade Zahlen..."):
            umsatz, anzahl_heute, anzahl_woche, chart_data = lade_statistik_daten()
            if isinstance(umsatz, str) and umsatz.startswith("Fehler"): st.error(umsatz)
            else:
                k1, k2, k3 = st.columns(3)
                if not isinstance(umsatz, (int, float)): umsatz = 0.0
                k1.metric("Umsatz (Monat)", f"{umsatz:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
                k2.metric("Aufträge (Heute)", str(anzahl_heute))
                k3.metric("Aufträge (Woche)", str(anzahl_woche))
                st.markdown("---")
                st.subheader("📈 Umsatzverlauf")
                if chart_data is not None and not chart_data.empty: st.bar_chart(chart_data)
                else: st.info("Noch nicht genug Daten für ein Diagramm.")
    else: st.warning("Bitte erst API Keys eintragen.")

elif modus == "Bericht & DATEV erstellen":
    st.caption("Modus: 🔵 Arbeitsbericht erstellen")
    if 'temp_data' not in st.session_state: st.session_state.temp_data = None
    if 'audio_processed' not in st.session_state: st.session_state.audio_processed = False

    f = st.file_uploader("Sprachnachricht", type=["mp3","wav","m4a","ogg","opus"], label_visibility="collapsed")

    # 1. SCHRITT: AUDIO VERARBEITEN
    if f and api_key and client and not st.session_state.audio_processed:
        dateiendung = f.name.split('.')[-1]
        temp_filename = f"temp_audio.{dateiendung}"
        with st.spinner("⏳ Analysiere Audio..."):
            with open(temp_filename, "wb") as file: file.write(f.getbuffer())
            try:
                txt = audio_zu_text(temp_filename)
                preise = lade_preise_live()
                kunden = lade_kunden_live() 
                dat = text_zu_daten(txt, preise, kunden)
                dat['rechnungs_nr'] = hole_nr()
                st.session_state.temp_data = dat; st.session_state.audio_processed = True; st.rerun()
            except Exception as e: st.error(f"Fehler: {e}")

    # 2. SCHRITT: VORSCHAU & EDITOR
    if st.session_state.temp_data:
        st.markdown("### 📝 Vorschau & Korrektur")
        dat = st.session_state.temp_data
        c1, c2 = st.columns(2)
        neuer_kunde = c1.text_input("Kunde", value=dat.get('kunde_name', ''))
        neue_nr = c2.text_input("Bericht Nr.", value=dat.get('rechnungs_nr', ''))
        neue_adresse = st.text_area("Adresse", value=dat.get('adresse', ''))
        neuer_titel = st.text_input("Betreff / Arbeit", value=dat.get('problem_titel', ''))

        st.markdown("#### Positionen bearbeiten")
        df_pos = pd.DataFrame(dat.get('positionen', []))
        if 'gesamt_netto' in df_pos.columns: df_pos = df_pos.drop(columns=['gesamt_netto']) 
        edited_df = st.data_editor(df_pos, num_rows="dynamic", use_container_width=True)

        # 3. SCHRITT: FERTIGSTELLEN
        if st.button("✅ Bericht jetzt erstellen", type="primary"):
            try:
                with st.spinner("Erstelle PDF..."):
                    pos_list, sum_net, sum_mwst, sum_brutto = berechne_summen(edited_df)
                    final_data = {'rechnungs_nr': neue_nr, 'kunde_name': neuer_kunde, 'adresse': neue_adresse, 'problem_titel': neuer_titel, 'positionen': pos_list, 'summe_netto': sum_net, 'mwst_betrag': sum_mwst, 'summe_brutto': sum_brutto, 'anrede': dat.get('anrede', ''), 'kundennummer': dat.get('kundennummer', '')}
                    pdf = erstelle_bericht_pdf(final_data)
                    csv = baue_datev_datei(final_data)
                    gespeichert = speichere_rechnung(final_data)
                    mail_gesendet = False
                    if email_sender: mail_gesendet = sende_mail(pdf, final_data)

                    st.success("Erledigt!")
                    if gespeichert: st.toast("Cloud gespeichert ✅")
                    if mail_gesendet: st.toast("Mail gesendet 📧")
                    
                    st.markdown("---")
                    st.markdown("### 📤 Versand & Download")
                    
                    # --- ÄNDERUNG: KLARE TRENNUNG PDF vs WHATSAPP ---
                    c_dl, c_wa = st.columns(2)
                    
                    with c_dl:
                        st.markdown("#### 1. Datei laden")
                        with open(pdf, "rb") as file: 
                            st.download_button("⬇️ PDF herunterladen", file, pdf, "application/pdf")
                            
                    with c_wa:
                        st.markdown("#### 2. WhatsApp senden")
                        wa_text = f"Moin {neuer_kunde}, anbei der Arbeitsbericht {neue_nr}."
                        wa_link = f"https://wa.me/?text={urllib.parse.quote(wa_text)}"
                        st.link_button("💬 WhatsApp öffnen", wa_link)
                    
                    st.info("⚠️ Hinweis: WhatsApp kann keine Dateien automatisch anhängen. Bitte das heruntergeladene PDF manuell in den Chat ziehen!")

                    # DATEV separat drunter
                    with open(pdf, "rb") as f_csv:
                        st.download_button("📊 DATEV (CSV) laden", csv, f"DATEV_{neue_nr}.csv", "text/csv")

            except Exception as e: st.error(f"Fehler beim Erstellen: {e}")

    if st.session_state.audio_processed:
        if st.button("❌ Abbrechen / Neu starten"):
            st.session_state.temp_data = None; st.session_state.audio_processed = False; st.rerun()

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
