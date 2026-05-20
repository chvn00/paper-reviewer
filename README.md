# Multi-Agent Paper Review System
### Powered by Phi-3 Mini · 100% Offline · Q1 Journal Standards

A fully local, offline scientific paper review system that analyzes PDF manuscripts using a multi-agent architecture. Rubrics based on **Elsevier**, **IEEE**, **Emerald**, and **ScienceDirect** Q1 journal peer review standards.

---

## Features

- **11 specialized reviewer agents** + MetaReviewer
- **Two review modes**: Fast (parallel, ~15-25 min) / Deep (chunked, ~40-80 min)
- **Conditional agents**: Statistics and Equations agents only activate if content is detected
- **Configurable LLM** from the web UI — switch between phi3:mini, llama3.2, mistral
- **PDF report** download with editorial decision
- **100% offline** — no data leaves your machine

---

## Installation (Windows — Dell)

### 1. Install Python 3.10+
Download from https://python.org — check "Add to PATH" during install.

### 2. Install Ollama
Download from https://ollama.com and install.

### 3. Download Phi-3 Mini
```bash
ollama pull phi3:mini
```

### 4. Clone / Extract the project
Place all files in a folder, e.g. `C:\paper-review\`

### 5. Run the installer
```bash
install_windows.bat
```

### 6. Start the application
```bash
run_app.bat
```

### 7. Open browser
```
http://localhost:8000
```

---

## Tomorrow — Mac with Llama 3.2

1. Install Ollama for Mac: https://ollama.com
2. Pull the model: `ollama pull llama3.2`
3. Open the app → ⚙️ Model Config
4. Change **Model Name** to `llama3.2`
5. Click **Save Configuration**

No other changes needed — the client is model-agnostic.

---

## Architecture

```
paper-review/
├── frontend/
│   ├── index.html          # Dashboard UI
│   ├── styles.css          # Academic dark theme
│   └── app.js              # Frontend logic
├── backend/
│   ├── app.py              # FastAPI server
│   ├── report_generator.py # PDF report generation
│   ├── llm/
│   │   └── phi3_client.py  # Abstract LLM client (Ollama)
│   └── agents/
│       ├── base_agent.py                    # Base class
│       ├── parser_agent.py                  # PDF parsing
│       ├── title_abstract_agent.py          # Title/Abstract/Keywords
│       ├── structure_reviewer.py            # Manuscript structure
│       ├── methodology_reviewer.py          # Methodology + equations
│       ├── statistics_reviewer.py           # Stats (conditional)
│       ├── figures_tables_agent.py          # Figures/tables (conditional)
│       ├── results_reviewer.py              # Results validity
│       ├── discussion_conclusions_agent.py  # Discussion/conclusions
│       ├── writing_reviewer.py              # Scientific writing
│       ├── references_reviewer.py           # References quality
│       ├── ethics_limitations_reviewer.py   # Ethics/limitations
│       └── meta_reviewer.py                 # Editorial synthesis
├── uploads/                # Temporary PDF storage
├── reports/                # Generated PDF reports
├── install_windows.bat
├── run_app.bat
└── README.md
```

---

## Review Agents

| Agent | Scope | Conditional |
|---|---|---|
| TitleAbstractKeywordsReviewer | Title clarity, abstract IMRaD, keywords | No |
| StructureReviewer | IMRaD flow, hypothesis, coherence | No |
| MethodologyReviewer | Design, reproducibility, equations | No |
| StatisticsReviewer | Tests, effect sizes, CI reporting | ✅ If stats detected |
| FiguresTablesReviewer | Captions, axes, redundancy | ✅ If figs/tables detected |
| ResultsReviewer | Empirical support, baselines, claims | No |
| DiscussionConclusionsReviewer | Interpretation, limitations, future work | No |
| WritingReviewer | Clarity, flow, academic tone | No |
| ReferencesReviewer | Recency, relevance, completeness | No |
| EthicsLimitationsReviewer | COPE standards, data availability | No |
| MetaReviewer | Weighted synthesis, editorial decision | Always last |

---

## Scoring

Scale **0–5** per agent:

| Score | Label |
|---|---|
| 0 | Not evaluable / Skipped |
| 1 | Very weak |
| 2 | Weak |
| 3 | Acceptable |
| 4 | Good |
| 5 | Excellent |

**Editorial decisions:**
- ≥ 4.5 → Accept
- ≥ 3.5 → Minor Revision
- ≥ 2.5 → Major Revision
- < 2.5 → Reject

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | System health + Ollama status |
| GET | `/config` | Current LLM config |
| POST | `/config` | Update LLM config |
| POST | `/upload` | Upload PDF |
| POST | `/review` | Start review |
| GET | `/status/{id}` | Poll progress |
| GET | `/results/{id}` | Get full results |
| GET | `/download-report/{id}` | Download PDF report |
| DELETE | `/session/{id}` | Clear session |

---

## Disclaimer

This system is an AI-assisted tool. All outputs must be validated by qualified domain experts. The system cannot replace human peer review and should not be used as the sole basis for editorial decisions.

Rubrics are based on publicly documented peer review criteria from Elsevier (2024 structured review pilot), IEEE Author Center, Emerald Publishing, and literature on Q1 journal standards.
