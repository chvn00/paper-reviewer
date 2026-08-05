"""
app.py — CHVN Paper Reviewer v3
--------------------------------
Fixes:
- Sequential agent execution (no more timeouts from parallel overload)
- Timer: tracks elapsed time per session
- Stop & Save: interrupt without losing completed agents
- /models endpoint for UI dropdown
- Balanced mode added
"""

import os
import uuid
import asyncio
import logging
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─── Access token auth (set ACCESS_TOKEN env var to enable) ──────────────────
_ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")

def _require_auth(request: Request):
    """Check Bearer token. Skipped if ACCESS_TOKEN not configured."""
    if not _ACCESS_TOKEN:
        return  # Auth disabled (local mode)
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if not token:
        token = request.headers.get("X-Access-Token", "")
    if token != _ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing access token.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("chvn_review.log")],
)
logger = logging.getLogger(__name__)

from backend.llm.phi3_client import update_config, get_config, check_ollama_health
from backend.agents.parser_agent import ParserAgent
from backend.agents.title_abstract_agent import TitleAbstractKeywordsReviewerAgent
from backend.agents.structure_reviewer import StructureReviewerAgent
from backend.agents.methodology_reviewer import MethodologyReviewerAgent
from backend.agents.statistics_reviewer import StatisticsReviewerAgent
from backend.agents.figures_tables_agent import FiguresTablesReviewerAgent
from backend.agents.results_reviewer import ResultsReviewerAgent
from backend.agents.discussion_conclusions_agent import DiscussionConclusionsReviewerAgent
from backend.agents.writing_reviewer import WritingReviewerAgent
from backend.agents.references_reviewer import ReferencesReviewerAgent
from backend.agents.ethics_limitations_reviewer import EthicsLimitationsReviewerAgent
from backend.agents.meta_reviewer import MetaReviewerAgent
from backend.report_generator import ReportGenerator
from backend.agents.author_mode_agent import generate_author_suggestion

BASE_DIR     = Path(__file__).parent.parent
UPLOAD_DIR   = BASE_DIR / "uploads"
REPORTS_DIR  = BASE_DIR / "reports"
FRONTEND_DIR = BASE_DIR / "frontend"
HISTORY_PATH = REPORTS_DIR / "history.json"

UPLOAD_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

MAX_FILE_MB = 20
sessions: dict    = {}
stop_flags: dict  = {}


def _load_history() -> list:
    try:
        if HISTORY_PATH.exists():
            return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[History] Could not read history: {e}")
    return []


def _save_history(records: list):
    HISTORY_PATH.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _add_history_record(session: dict):
    meta_review = session.get("meta_review", {})
    sections = session.get("parse_result", {}).get("sections", {})
    report_path = session.get("report_path", "")
    if not report_path:
        return
    records = _load_history()
    record = {
        "id": str(uuid.uuid4()),
        "session_id": session.get("session_id", ""),
        "title": sections.get("title", "").strip() or session.get("filename", ""),
        "filename": session.get("filename", ""),
        "mode": session.get("mode", "fast"),
        "model_used": session.get("model_used", ""),
        "final_weighted_score": meta_review.get("final_weighted_score", 0),
        "editorial_decision": meta_review.get("editorial_decision", "N/A"),
        "elapsed_sec": session.get("elapsed_sec", 0),
        "created_at": datetime.now().isoformat(),
        "report_path": report_path,
        "stopped_early": session.get("status") == "stopped",
    }
    records.insert(0, record)
    _save_history(records[:200])

app = FastAPI(title="CHVN Paper Reviewer", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


class ReviewRequest(BaseModel):
    session_id: str
    mode:       str = "fast"
    publisher:  Optional[str] = None
    paper_type: Optional[str] = None

class ConfigUpdate(BaseModel):
    model: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None


@app.get("/")
async def root():
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        return {"status": "CHVN Paper Reviewer v4"}
    return FileResponse(
        str(index),
        headers={
            "Cache-Control": "no-store, no-cache, no-transform, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/health")
async def health():
    groq_status = await check_ollama_health()
    return {"api": "running", "groq": groq_status, "config": get_config()}


@app.get("/models")
async def list_models(_: None = Depends(_require_auth)):
    from backend.llm.phi3_client import OLLAMA_MODELS
    cfg = get_config()
    return {"models": OLLAMA_MODELS, "current": cfg["model"]}


@app.get("/config")
async def get_model_config(_: None = Depends(_require_auth)):
    return get_config()


@app.post("/config")
async def update_model_config(config: ConfigUpdate, _: None = Depends(_require_auth)):
    new = {k: v for k, v in config.dict().items() if v is not None}
    update_config(new)
    return {"status": "updated", "config": get_config()}


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...), _: None = Depends(_require_auth)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_MB:
        raise HTTPException(413, f"File too large ({size_mb:.1f} MB). Max: {MAX_FILE_MB} MB.")

    session_id = str(uuid.uuid4())
    pdf_path   = UPLOAD_DIR / f"{session_id}.pdf"
    pdf_path.write_bytes(content)

    logger.info(f"[/upload] {session_id} — {file.filename} ({size_mb:.2f} MB)")

    parser       = ParserAgent()
    parse_result = parser.run(str(pdf_path))

    if not parse_result["success"]:
        pdf_path.unlink(missing_ok=True)
        raise HTTPException(422, parse_result["error"])

    sessions[session_id] = {
        "session_id":    session_id,
        "filename":      file.filename,
        "pdf_path":      str(pdf_path),
        "parse_result":  parse_result,
        "status":        "parsed",
        "progress":      0,
        "current_agent": "",
        "agent_results": [],
        "meta_review":   {},
        "report_path":   "",
        "elapsed_sec":   0,
        "start_time":    None,
        "created_at":    datetime.now().isoformat(),
    }
    stop_flags[session_id] = asyncio.Event()

    meta = parse_result["metadata"]
    sections = parse_result.get("sections", {})
    return {
        "session_id":      session_id,
        "filename":        file.filename,
        "size_mb":         round(size_mb, 2),
        "word_count":      meta.get("word_count", 0),
        "sections_found":  meta.get("sections_found", []),
        "has_statistics":  meta.get("has_statistics", False),
        "has_equations":   meta.get("has_equations", False),
        "has_figures":     meta.get("has_figures", False),
        "has_tables":      meta.get("has_tables", False),
        "figure_count":    meta.get("figure_count", 0),
        "table_count":     meta.get("table_count", 0),
        "equation_count":  meta.get("equation_count", 0),
        "format_detected": meta.get("format_detected", "Generic"),
        "detected_title":   sections.get("title", ""),
        "detected_abstract": sections.get("abstract", ""),
        "detected_keywords": sections.get("keywords", ""),
        "warnings":        parse_result.get("warnings", []),
    }


@app.post("/review")
async def start_review(req: ReviewRequest, bg: BackgroundTasks, _: None = Depends(_require_auth)):
    sid = req.session_id
    if sid not in sessions:
        raise HTTPException(404, "Session not found.")
    if sessions[sid]["status"] == "reviewing":
        raise HTTPException(409, "Review already in progress.")

    sessions[sid].update({
        "status":        "reviewing",
        "progress":      0,
        "mode":          req.mode,
        "publisher":     req.publisher or "",
        "paper_type":    req.paper_type or "",
        "model_used":    get_config()["model"],
        "agent_results": [],
        "start_time":    time.time(),
        "elapsed_sec":   0,
    })
    stop_flags[sid] = asyncio.Event()
    bg.add_task(run_pipeline, sid, req.mode, req.publisher or "", req.paper_type or "")
    return {"status": "started", "session_id": sid, "mode": req.mode}


@app.post("/stop/{session_id}")
async def stop_review(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found.")
    if session_id in stop_flags:
        stop_flags[session_id].set()
        sessions[session_id]["status"] = "stopping"
    return {"status": "stopping", "message": "Completed agents saved."}


@app.get("/status/{session_id}")
async def get_status(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found.")
    s = sessions[session_id]
    # Update elapsed time
    if s.get("start_time") and s["status"] == "reviewing":
        s["elapsed_sec"] = int(time.time() - s["start_time"])
    return {
        "session_id":    session_id,
        "status":        s["status"],
        "progress":      s["progress"],
        "current_agent": s.get("current_agent", ""),
        "agents_done":   len(s.get("agent_results", [])),
        "elapsed_sec":   s.get("elapsed_sec", 0),
        "error":         s.get("error", ""),
    }


@app.get("/results/{session_id}")
async def get_results(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found.")
    s = sessions[session_id]
    if s["status"] not in ("completed", "error", "stopped"):
        raise HTTPException(202, "Review still in progress.")
    return {
        "session_id":    session_id,
        "filename":      s["filename"],
        "mode":          s.get("mode", "fast"),
        "model_used":    s.get("model_used", "phi3:mini"),
        "metadata":      s["parse_result"]["metadata"],
        "warnings":      s["parse_result"].get("warnings", []),
        "agent_results": s["agent_results"],
        "meta_review":   s["meta_review"],
        "report_ready":  bool(s.get("report_path")),
        "stopped_early": s["status"] == "stopped",
        "elapsed_sec":   s.get("elapsed_sec", 0),
    }


@app.get("/history")
async def get_history():
    records = []
    for record in _load_history():
        public = {k: v for k, v in record.items() if k != "report_path"}
        public["report_ready"] = bool(record.get("report_path") and Path(record["report_path"]).exists())
        records.append(public)
    return {"history": records}


@app.get("/history/{record_id}/download")
async def download_history_report(record_id: str):
    for record in _load_history():
        if record.get("id") == record_id:
            path = record.get("report_path", "")
            if not path or not Path(path).exists():
                raise HTTPException(404, "Report file not found.")
            fname = record.get("filename", "paper").replace(".pdf", "")
            mode = record.get("mode", "review")
            return FileResponse(
                path=path,
                media_type="application/pdf",
                filename=f"CHVN_Review_{fname}_{mode}_{record_id[:8]}.pdf",
            )
    raise HTTPException(404, "History record not found.")


@app.delete("/history/{record_id}")
async def delete_history_record(record_id: str):
    records = _load_history()
    new_records = [r for r in records if r.get("id") != record_id]
    if len(new_records) == len(records):
        raise HTTPException(404, "History record not found.")
    _save_history(new_records)
    return {"ok": True}


@app.get("/partial-results/{session_id}")
async def get_partial_results(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found.")
    s = sessions[session_id]
    if s.get("start_time") and s["status"] in ("reviewing", "stopping"):
        s["elapsed_sec"] = int(time.time() - s["start_time"])
    return {
        "session_id": session_id,
        "status": s["status"],
        "progress": s.get("progress", 0),
        "current_agent": s.get("current_agent", ""),
        "agent_results": s.get("agent_results", []),
        "meta_review": s.get("meta_review", {}),
        "elapsed_sec": s.get("elapsed_sec", 0),
    }


@app.get("/partial-results/")
async def get_partial_results_query(session_id: str):
    return await get_partial_results(session_id)


@app.get("/download-report/{session_id}")
async def download_report(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found.")
    path = sessions[session_id].get("report_path", "")
    if not path or not Path(path).exists():
        raise HTTPException(404, "Report not generated yet.")
    fname = sessions[session_id]['filename'].replace('.pdf', '')
    return FileResponse(
        path=path, media_type="application/pdf",
        filename=f"CHVN_Review_{fname}_{session_id[:8]}.pdf"
    )


# ─── Modo Autor ──────────────────────────────────────────────────────────────

@app.post("/author-mode/{session_id}")
async def start_author_mode(session_id: str, bg: BackgroundTasks, _: None = Depends(_require_auth)):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found.")
    s = sessions[session_id]
    if s["status"] not in ("completed", "stopped"):
        raise HTTPException(409, "Review must be completed before entering Author Mode.")
    if not s.get("agent_results"):
        raise HTTPException(409, "No review results available.")

    s["author_mode_status"]   = "running"
    s["author_mode_progress"] = 0
    s["author_mode_current"]  = ""
    s["author_mode_results"]  = []

    bg.add_task(_run_author_mode, session_id)
    return {"status": "started", "session_id": session_id}


@app.get("/author-mode/{session_id}")
async def get_author_mode(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found.")
    s = sessions[session_id]
    return {
        "status":     s.get("author_mode_status", "idle"),
        "progress":   s.get("author_mode_progress", 0),
        "current":    s.get("author_mode_current", ""),
        "results":    s.get("author_mode_results", []),
        "error":      s.get("author_mode_error", ""),
        "publisher":  s.get("publisher", ""),
        "paper_type": s.get("paper_type", ""),
    }


async def _run_author_mode(session_id: str):
    s        = sessions[session_id]
    sections = s["parse_result"]["sections"]
    agents   = [r for r in s["agent_results"] if r.get("agent_name") != "MetaReviewer"]
    total    = max(len(agents), 1)

    try:
        results = []
        for i, agent_result in enumerate(agents):
            s["author_mode_current"]  = agent_result.get("agent_name", "")
            s["author_mode_progress"] = int((i / total) * 95)

            suggestion = await generate_author_suggestion(
                agent_result, sections,
                publisher=s.get("publisher", ""),
                paper_type=s.get("paper_type", ""),
            )
            results.append(suggestion)
            s["author_mode_results"] = list(results)

            logger.info(f"[AuthorMode] {session_id} — {suggestion['agent_name']} done ({i+1}/{total})")

        s["author_mode_status"]   = "completed"
        s["author_mode_progress"] = 100
        s["author_mode_current"]  = ""
    except Exception as e:
        logger.error(f"[AuthorMode] {session_id} ERROR: {e}", exc_info=True)
        s["author_mode_status"] = "error"
        s["author_mode_error"]  = str(e)


@app.delete("/session/{session_id}")
async def clear_session(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found.")
    if session_id in stop_flags:
        stop_flags[session_id].set()
    s = sessions.pop(session_id)
    stop_flags.pop(session_id, None)
    for key in ["pdf_path"]:
        p = s.get(key, "")
        if p:
            Path(p).unlink(missing_ok=True)
    return {"status": "cleared"}


# ─── Pipeline — SEQUENTIAL to avoid timeouts ─────────────────────────────────

async def run_pipeline(sid: str, mode: str, publisher: str = "", paper_type: str = ""):
    s          = sessions[sid]
    sections   = s["parse_result"]["sections"]
    metadata   = s["parse_result"]["metadata"]
    stop_event = stop_flags.get(sid, asyncio.Event())

    logger.info(f"[Pipeline] {sid} — mode={mode} publisher={publisher or 'general'} type={paper_type or 'full'} — SEQUENTIAL")

    agents = [
        TitleAbstractKeywordsReviewerAgent(),
        StructureReviewerAgent(),
        MethodologyReviewerAgent(),
        StatisticsReviewerAgent(),
        FiguresTablesReviewerAgent(),
        ResultsReviewerAgent(),
        DiscussionConclusionsReviewerAgent(),
        WritingReviewerAgent(),
        ReferencesReviewerAgent(),
        EthicsLimitationsReviewerAgent(),
    ]

    total          = len(agents)
    agent_results  = []

    try:
        # ── Run agents SEQUENTIALLY ────────────────────────────────────────
        for i, agent in enumerate(agents):
            if stop_event.is_set():
                logger.info(f"[Pipeline] Stop requested at agent {i}")
                agent_results.append(
                    agent._empty_result("Stopped by user before execution.")
                )
                continue

            s["current_agent"] = agent.agent_name
            s["progress"]      = 5 + int((i / total) * 82)

            result = await agent.run(sections, mode, publisher=publisher, paper_type=paper_type)
            agent_results.append(result)

            # Save immediately after each agent
            s["agent_results"] = list(agent_results)
            s["elapsed_sec"]   = int(time.time() - s["start_time"])

            logger.info(
                f"[Pipeline] {agent.agent_name} done "
                f"({i+1}/{total}) score={result.get('score',0)} "
                f"elapsed={s['elapsed_sec']}s"
            )

        # ── MetaReviewer ───────────────────────────────────────────────────
        s["current_agent"] = "MetaReviewer"
        s["progress"]      = 90
        meta        = MetaReviewerAgent()
        meta_result = await meta.synthesize(agent_results, sections, mode, publisher=publisher, paper_type=paper_type)
        s["meta_review"]  = meta_result
        s["progress"]     = 95

        # ── Generate PDF ───────────────────────────────────────────────────
        s["current_agent"] = "Generating Report..."
        report_path = REPORTS_DIR / f"report_{sid}_{mode}_{int(time.time())}.pdf"
        gen = ReportGenerator(str(report_path))

        elapsed = int(time.time() - s["start_time"])
        s["elapsed_sec"] = elapsed

        gen.generate({
            "metadata":      metadata,
            "mode":          mode,
            "model_used":    s.get("model_used", "phi3:mini"),
            "warnings":      s["parse_result"].get("warnings", []),
            "agent_results": agent_results + [meta_result],
            "meta_review":   meta_result,
            "stopped_early": stop_event.is_set(),
            "elapsed_sec":   elapsed,
        }, s["filename"])

        s["report_path"]   = str(report_path)
        s["current_agent"] = ""
        s["progress"]      = 100
        s["status"]        = "stopped" if stop_event.is_set() else "completed"
        _add_history_record(s)

        # Delete uploaded PDF immediately after review (privacy — paper not stored on server)
        pdf_path = s.get("pdf_path", "")
        if pdf_path:
            Path(pdf_path).unlink(missing_ok=True)
            logger.info(f"[Pipeline] PDF deleted after review (privacy): {pdf_path}")

        logger.info(f"[Pipeline] {sid} DONE — {elapsed}s — status={s['status']}")

    except Exception as e:
        logger.error(f"[Pipeline] {sid} ERROR: {e}", exc_info=True)
        s["status"]  = "error"
        s["error"]   = str(e)
        s["progress"] = max(int(s.get("progress", 0) or 0), 1)
        s["current_agent"] = "Error"


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.app:app", host="0.0.0.0", port=port, reload=False)
