import streamlit as st
import json

st.set_page_config(page_title="🔧 Schlüssel-Reparatur", page_icon="🔧")

st.title("🔧 Der Schlüssel-Doktor")
st.write("Wir machen deine JSON-Datei fit für den Tresor.")

# 1. Großes Eingabefeld
st.info("1. Öffne deine heruntergeladene JSON-Datei auf dem PC (mit Editor/Notepad).")
st.info("2. Kopiere ALLES (von { bis }) und füge es hier ein:")

rohtext = st.text_area("Füge hier den Datei-Inhalt ein:", height=300)

if rohtext:
    st.markdown("---")
    st.subheader("Diagnose:")
    
    try:
        # Wir testen, ob es gültiges JSON ist
        daten = json.loads(rohtext)
        st.success("✅ Super! Die Datei ist gültig und lesbar.")
        
        st.subheader("Dein fertiger Text für die Secrets:")
        st.write("Kopiere den folgenden Block und ersetze damit ALLES in deinen Secrets:")
        
        # Wir bauen den perfekten TOML-Block
        toml_block = f"""openai_api_key = "sk-..."
email_sender = "info@interwark.de"
email_password = "..."
smtp_server = "smtp.ionos.de"
smtp_port = 465

google_json = \"\"\"
{json.dumps(daten, indent=2)}
\"\"\"
"""
        st.code(toml_block, language="toml")
        st.warning("⚠️ WICHTIG: Trage oben im Block noch deinen echten OpenAI-Key und dein Email-Passwort ein!")
        
    except json.JSONDecodeError as e:
        st.error(f"❌ Die Datei ist kaputt: {e}")
        st.write("Tipp: Lade die Datei am besten nochmal neu bei Google Cloud herunter. Irgendwo fehlt ein Komma, eine Klammer oder ein Gänsefüßchen.")
