# 💼 JobHunt.AI — Local-First Job Application Tracker & AI Resume Tailor

A private, local-first application tracker and AI-powered resume tailor built with **Streamlit** and **SQLite**. Works out of the box with local LLMs (**LM Studio**, **Ollama**) or external AI providers (**Google Gemini**, **OpenAI**, **Claude**).

---

## ✨ Key Features

- **💼 Application Tracker**: Search, filter, and track applications across interview stages. Includes inline status updates, follow-up scheduling, and deletion.
- **🎯 Add Job & Tailor**: Ingest job descriptions via URL or pasted text, perform weighted semantic gap analysis (core vs. preferred skills), and generate tailored resumes in Markdown and clean 2-page Microsoft Word (`.docx`).
- **📝 Master Resume Manager**: Centralized visual profile manager that synchronizes your skills, work history, and side projects to markdown and JSON. Features an expand/collapse toggle.
- **📊 Conversion Dashboard**: True lifetime funnel analytics (Leads → Prepared → Submitted → Interviewed) and match-score conversion benchmarks.
- **🔒 Security & Privacy by Design**:
  - API keys are stored strictly in a local, git-ignored `.env` file with `0600` permissions.
  - Server binds to localhost (`127.0.0.1`), keeping your data on your machine.
  - Supports 100% offline local inference via LM Studio and Ollama.

---

## 🛠️ Tech Stack & Requirements

- **Frontend & App Framework**: [Streamlit](https://streamlit.io/)
- **Database**: SQLite (auto-initialized on first run)
- **Document Generation**: `python-docx`
- **Supported AI Models**:
  - **Local (Default)**: LM Studio (`http://127.0.0.1:1234/v1`), Ollama (`http://127.0.0.1:11434/v1`)
  - **Cloud APIs**: Google Gemini API (`gemini-3.8-flash`), OpenAI (`gpt-5.4`), OpenRouter / Anthropic Claude

---

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/layclough/job-tracker-oss.git
cd job-tracker-oss
```

### 2. Set Up a Virtual Environment & Install Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Launch the Application
```bash
streamlit run app.py
```
Open `http://localhost:8501` in your browser.

---

## ⚙️ Configuring Your AI Model

Click the **Settings** button in the sidebar to configure your preferred AI provider:

1. **Local LM Studio (Default)**:
   - Run LM Studio locally and start the local server on `http://127.0.0.1:1234/v1`.
   - Recommended model: `google/gemma-4-31b` or `qwen2.5-14b-instruct`.
2. **Local Ollama**:
   - Run Ollama locally on `http://127.0.0.1:11434/v1`.
   - Recommended model: `gemma4:31b` or `qwen3:32b`.
3. **Google Gemini API**:
   - Select **Google Gemini API**, enter your API key, and test connectivity.
   - Recommended model: `gemini-3.8-flash`.
4. **OpenAI API**:
   - Select **OpenAI API**, enter your API key, and test connectivity.
   - Recommended model: `gpt-5.4`.

---

## 📁 Project Structure

```text
job-tracker-oss/
├── app.py                      # Main Streamlit router & database initialization
├── assets/                     # Custom UI styling (global_styles.css)
├── views/                      # Application views
│   ├── master.py               # Master resume profile editor
│   ├── tailor.py               # Job description ingest & resume tailor
│   ├── tracker.py              # Application tracker & status management
│   └── dashboard.py            # Funnel conversion analytics
├── src/                        # Core logic
│   ├── llm_config.py           # Provider settings, key masking & connections
│   ├── extractor.py            # JD extraction & weighted semantic gap scoring
│   ├── generator.py            # Dynamic resume generation & DOCX export
│   └── adapters/               # URL web scraping adapters
├── 00_Data/
│   └── templates/              # Starter resume and profile templates
└── requirements.txt            # Python dependencies
```

---

## 📄 License

MIT License. Feel free to use, modify, and build upon this project for your own job hunt.
