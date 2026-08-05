# CHVN Paper Reviewer
### Multi-Agent Scientific Review System · 100% Offline · Q1 Standards

A fully local, offline scientific paper review system that analyzes PDF manuscripts using a multi-agent architecture. Rubrics based on **IEEE**, **Elsevier**, **MDPI**, **Emerald**, **SAGE**, and **Taylor & Francis** Q1 journal peer review standards.

---

## ✨ Features

- **11 specialized reviewer agents** + MetaReviewer editorial synthesis
- **3 review modes:**
  - 🚀 **Fast** (~4 min): 20K chars, major issues only, fast screening
  - ⚖️ **Balanced** (~6 min): 40K chars, complete review, recommended
  - 🔬 **Deep** (~10 min): 48K chars, exhaustive analysis, pre-submission
- **Conditional agents**: Statistics & Figures/Tables activate only if content detected
- **✍️ Modo Autor** (Author Mode):
  - Post-review mode to generate author-facing revision suggestions
  - Per-section instructions + LaTeX code snippets
  - Formatting adjusted to target publisher (IEEE, Elsevier, MDPI, etc.)
  - One-click copy to clipboard
- **6 publisher rubrics** + paper type support (article, short communication, review, conference, case study, etc.)
- **Configurable LLM** from the web UI — supports llama3.2, qwen3, mistral, gemma3, etc.
- **PDF report download** with editorial decision, scores, and synthesis
- **100% offline** — no data leaves your machine
- **macOS launcher** (Abrir Paper Reviewer.app) with one-click startup

---

## Installation

### Mac

**Automatic (recommended):**
1. Double-click **Abrir Paper Reviewer.app** in the project folder
   - Auto-starts the server in the background
   - Opens browser at http://localhost:8000
   - Creates venv and installs dependencies on first run

**Manual:**
```bash
# 1. Install Ollama
brew install ollama

# 2. Clone or extract the project
git clone https://github.com/chvn00/paper-reviewer.git
cd paper-reviewer

# 3. Create venv and install dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 4. Start Ollama
ollama serve

# 5. In another terminal, start the app
.venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000

# 6. Open browser
open http://localhost:8000
```

### Model Selection

By default, the app uses **llama3.2** (optimized for Mac Apple Silicon).

**To change models:**
1. Open the app → ⚙️ **Model Config**
2. Click **↻** to refresh available models
3. Select a model or type its name manually
4. Click **💾 Save**

Available models (via Ollama):
- `llama3.2` — 4B, fast, good quality (default)
- `qwen3:32b` — 32B, highest quality (slow, needs 32GB RAM)
- `qwen3:14b` — 14B, balanced (recommended if available)
- `mistral` — 7B, general purpose
- `gemma3:12b` — 12B, specialized

---

## Workflow

### 1️⃣ Upload & Select Settings
- Drop a PDF or click to browse
- Choose **Target Journal** (IEEE, Elsevier, MDPI, etc.)
- Choose **Paper Type** (Full Article, Review, Short Communication, etc.)
- Pick a **Review Mode** (Fast / Balanced / Deep)

### 2️⃣ Run Review
- Click **▶ Run Multi-Agent Review**
- Watch progress as 11 agents analyze the paper sequentially
- Agents display results live as they complete

### 3️⃣ View Results
- **Agent Reviews** tab: See each agent's feedback (strengths, weaknesses, major comments, recommendations)
- **Final Report** tab: Editorial decision, weighted score, synthesis, score table
- Download as PDF

### 4️⃣ (Optional) Modo Autor
- After review completes, **✍️ Modo Autor** tab activates
- Click **▶ Generar Sugerencias**
- System generates per-section revision guidance:
  - 💡 Instruction: What to change and how to write it
  - 📄 LaTeX code: Rewritten section in target publisher format
  - Click **Copiar** to copy LaTeX to clipboard
- Editorial badge shows target publisher + paper type

---

## Architecture

```
paper-reviewer/
├── frontend/
│   ├── index.html              # Dashboard UI (author mode included)
│   ├── styles.css              # Academic dark theme + Modo Autor styles
│   └── app.js                  # Frontend logic + author mode polling
├── backend/
│   ├── app.py                  # FastAPI server + endpoints
│   ├── report_generator.py     # PDF report generation
│   ├── llm/
│   │   └── phi3_client.py      # Abstract LLM client (Ollama, JSON mode)
│   └── agents/
│       ├── base_agent.py                    # Base class (deduplication, contradiction checks)
│       ├── parser_agent.py                  # PDF parsing → sections
│       ├── title_abstract_agent.py          # Title/Abstract/Keywords review
│       ├── structure_reviewer.py            # Manuscript structure & IMRaD
│       ├── methodology_reviewer.py          # Methods, reproducibility, equations
│       ├── statistics_reviewer.py           # Statistical tests, effect sizes (conditional)
│       ├── figures_tables_agent.py          # Figures/tables/equations (conditional)
│       ├── results_reviewer.py              # Results validity & empirical support
│       ├── discussion_conclusions_agent.py  # Discussion/conclusions interpretation
│       ├── writing_reviewer.py              # Scientific writing clarity
│       ├── references_reviewer.py           # References recency & quality
│       ├── ethics_limitations_reviewer.py   # Ethics/limitations/COPE standards
│       ├── author_mode_agent.py             # ✍️ Revision suggestions generator
│       └── meta_reviewer.py                 # Editorial synthesis + decision
├── uploads/                    # Temporary PDF storage (auto-deleted after review)
├── reports/                    # Generated PDF reports
├── .claude/
│   └── launch.json            # Dev server config
├── Abrir Paper Reviewer.app   # macOS app launcher
├── requirements.txt
└── README.md
```

---

## Review Agents

| Agent | Scope | Conditional |
|---|---|---|
| TitleAbstractKeywordsReviewer | Title clarity, abstract IMRaD structure, keyword relevance | No |
| StructureReviewer | IMRaD flow, hypothesis clarity, section coherence | No |
| MethodologyReviewer | Research design, reproducibility, equation presentation | No |
| StatisticsReviewer | Statistical tests, effect sizes, CI reporting, p-hacking checks | ✅ If stats detected |
| FiguresTablesReviewer | Captions completeness, axes labels, self-containment, redundancy | ✅ If figs/tables detected |
| ResultsReviewer | Empirical support, baseline comparisons, claim substantiation | No |
| DiscussionConclusionsReviewer | Interpretation validity, limitations acknowledgment, future work | No |
| WritingReviewer | Clarity, flow, academic tone, jargon precision | No |
| ReferencesReviewer | Recency, relevance, completeness, self-citation bias | No |
| EthicsLimitationsReviewer | COPE standards, data availability, conflict of interest declarations | No |
| AuthorModeAgent | ✍️ Revision instructions + LaTeX suggestions per section (post-review) | No |
| MetaReviewer | Weighted synthesis, editorial decision, confidence assessment | Always last |

---

## Scoring & Decisions

Scale **0–5** per agent:

| Score | Label |
|---|---|
| 0 | Not evaluable / Skipped |
| 1 | Very weak |
| 2 | Weak |
| 3 | Acceptable |
| 4 | Good |
| 5 | Excellent |

**Editorial decisions (weighted average):**
- ≥ 4.5 → **Accept**
- ≥ 3.5 → **Minor Revision**
- ≥ 2.5 → **Major Revision**
- < 2.5 → **Reject**

---

## Supported Publishers & Paper Types

### Publishers (rubric selection)
- 🏢 **IEEE** — technical rigor, reproducibility, state-of-the-art baselines
- 🏢 **Elsevier/ScienceDirect** — originality, methodological soundness, clarity
- 🏢 **MDPI** — scientific soundness, data transparency, reproducibility
- 🏢 **Emerald** — theoretical AND practical implications (mandatory for both)
- 🏢 **SAGE** — methodological coherence, interpretive rigor, field relevance
- 🏢 **Taylor & Francis** — broad scope, originality, argument clarity

### Paper Types
- Full Article (default)
- Short Communication
- Letter (rapid communication)
- Review Article
- Conference Paper
- Case Study
- Conceptual Paper
- Technical Note

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | System health + Ollama status |
| GET | `/config` | Current LLM configuration |
| POST | `/config` | Update LLM configuration |
| GET | `/models` | List available Ollama models |
| POST | `/upload` | Upload PDF file |
| POST | `/review` | Start review pipeline |
| GET | `/status/{id}` | Poll review progress |
| GET | `/partial-results/{id}` | Get partial results (live streaming) |
| GET | `/results/{id}` | Get complete review results |
| GET | `/download-report/{id}` | Download PDF report |
| DELETE | `/session/{id}` | Clear session & cleanup |
| POST | `/author-mode/{id}` | ✍️ Start Author Mode suggestion generation |
| GET | `/author-mode/{id}` | ✍️ Poll Author Mode progress + results |
| GET | `/history` | Get all completed reviews |
| GET | `/history/{id}/download` | Download report from history |
| DELETE | `/history/{id}` | Delete history record |

---

## Performance

On Mac Mini M4 Pro with llama3.2:

| Mode | Time | Content Window | Use Case |
|---|---|---|---|
| Fast | ~4 min | 20K chars | Rapid screening, initial triage |
| Balanced | ~6 min | 40K chars | Standard peer review (recommended) |
| Deep | ~10 min | 48K chars | Exhaustive analysis, pre-submission |

*Times vary with model size and system load.*

---

## Technical Details

### JSON Mode
All agents expect JSON responses. The LLM client enforces `format: "json"` in Ollama to eliminate parse errors.

### Deduplication & Contradiction Checks
The base agent:
1. Removes near-duplicates within each list (>75% word overlap)
2. Removes strengths that contradict weaknesses (same topic, opposite judgment)
3. Normalizes all responses to consistent structure

### No Data Retention
- PDFs are deleted immediately after review (privacy)
- Sessions are cleared after download
- Reports remain in `reports/` folder on your machine only

---

## Disclaimer

This system is an **AI-assisted tool**. All outputs must be validated by qualified domain experts before acting on them. The system cannot replace human peer review and should not be used as the sole basis for editorial decisions.

Rubrics are based on publicly documented peer review criteria from Elsevier (2024 structured review pilot), IEEE Author Center, Emerald Publishing, SAGE, and literature on Q1 journal standards.

**Confidence scores** represent model certainty, not review quality. Always have a human expert review the feedback.

---

## Development

### Running Tests
```bash
# Smoke test: author mode with LLM
.venv/bin/python backend/agents/author_mode_agent.py

# Check imports
.venv/bin/python -c "from backend.app import app; print('OK')"
```

### Contributing
Pull requests welcome. Ensure:
- New agents inherit from `BaseReviewerAgent`
- All outputs are JSON
- Tests pass locally with ollama running
- Commit message is descriptive

---

**Repository:** https://github.com/chvn00/paper-reviewer
**Latest Release:** Aug 5, 2026 (v2 · Fable 5 review improvements)
