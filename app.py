# --- NEUE PDF FUNKTION (PROFI-DESIGN) ---
class PDF(FPDF):
    def header(self):
        # Briefkopf (Logo/Name links)
        self.set_font('Arial', 'B', 15)
        self.cell(80, 10, 'INTERWARK', 0, 1, 'L')
        self.set_font('Arial', '', 10)
        self.cell(80, 5, 'Bernhard Stegemann-Klammt', 0, 1, 'L')
        self.cell(80, 5, 'Hohe Str. 28, 26725 Emden', 0, 1, 'L')
        
        # Linie unter dem Kopf
        self.set_draw_color(200, 200, 200) # Grau
        self.line(10, 35, 200, 35)
        self.ln(20) # Abstand zum Text

    def footer(self):
        # Fußzeile (Grau & Klein)
        self.set_y(-30) # 3 cm von unten
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128) # Grau
        
        # Spalte 1: Adresse & Kontakt
        self.cell(60, 5, 'Interwark', 0, 0, 'L')
        self.cell(60, 5, 'Bankverbindung:', 0, 0, 'L')
        self.cell(0, 5, 'Steuernummer:', 0, 1, 'L') # Zeilenumbruch
        
        # Spalte 2: Daten
        self.cell(60, 5, 'Tel: +49 4921 997130', 0, 0, 'L')
        self.cell(60, 5, 'Sparkasse Emden', 0, 0, 'L')
        self.cell(0, 5, '58/143/02484', 0, 1, 'L')
        
        # Spalte 3: IBAN etc
        self.cell(60, 5, '', 0, 0, 'L')
        self.cell(60, 5, 'IBAN: DE92 2845 0000 0018 0048 61', 0, 0, 'L')
        self.cell(0, 5, 'USt-IdNr.: DE226723406', 0, 1, 'L')

def erstelle_pdf(daten):
    pdf = PDF() # Hier rufen wir unsere neue Klasse auf
    pdf.add_page()
    
    # Hilfsfunktion für Umlaute
    def txt(t): return str(t).encode('latin-1', 'replace').decode('latin-1')
    
    # --- EMPFÄNGERFELD ---
    pdf.set_text_color(0) # Wieder Schwarz
    pdf.set_font("Arial", '', 10)
    pdf.ln(5)
    # Kleines Absenderfeld über der Adresse (für Fensterbriefumschläge)
    pdf.set_font("Arial", 'U', 8)
    pdf.cell(0, 5, txt("Interwark - Hohe Str. 28 - 26725 Emden"), 0, 1)
    
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 5, txt(daten.get('kunde_name', 'Kunde')), 0, 1)
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 5, txt(daten.get('adresse', '')), 0, 1)
    
    # --- DATUM & TITEL ---
    pdf.ln(20)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt(f"Auftrag / Rapport"), 0, 1)
    
    # --- INHALT ---
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 11)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 8, txt("Problembeschreibung / Meldung:"), 0, 1, fill=True)
    
    pdf.set_font("Arial", '', 11)
    pdf.multi_cell(0, 6, txt(daten.get('problem_detail', '')))
    
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(40, 8, txt("Dringlichkeit:"), 0, 0)
    pdf.set_font("Arial", '', 11)
    pdf.cell(0, 8, txt(daten.get('dringlichkeit', '-')), 0, 1)

    # --- UNTERSCHRIFTEN ---
    pdf.ln(30)
    pdf.line(10, pdf.get_y(), 90, pdf.get_y())
    pdf.line(110, pdf.get_y(), 190, pdf.get_y())
    
    pdf.set_font("Arial", '', 8)
    pdf.cell(90, 5, "Datum, Unterschrift Monteur", 0, 0, 'C')
    pdf.cell(10, 5, "", 0, 0)
    pdf.cell(90, 5, "Datum, Unterschrift Kunde", 0, 1, 'C')

    dateiname = "auftrag.pdf"
    pdf.output(dateiname)
    return dateiname