#!/bin/bash
cd /Users/cesarvalencia/Downloads/Paper_Reviewer_mac
lsof -ti :8000 | xargs kill -9 2>/dev/null
python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 &
sleep 2
open http://localhost:8000
