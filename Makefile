.PHONY: help setup db backend-setup backend frontend-setup frontend dev test

VENV := backend/.venv
PY   := $(abspath $(VENV))/bin

help:
	@echo "make setup     install backend and frontend dependencies, create env files, migrate"
	@echo "make db        create the local Postgres role and databases (once)"
	@echo "make backend   run the API on :8000 (jobs inline, no Redis needed)"
	@echo "make frontend  run Next.js on :3000"
	@echo "make dev       run backend and frontend together (Ctrl+C stops both)"
	@echo "make test      run backend tests and frontend typecheck"

setup: backend-setup frontend-setup

db:
	bash backend/scripts/setup_local_db.sh

backend-setup:
	test -d $(VENV) || python3 -m venv $(VENV)
	$(PY)/pip install -r backend/requirements.txt
	test -f backend/.env || { cp backend/.env.example backend/.env; echo "Created backend/.env: set DATABASE_URL and GEMINI_API_KEY"; }
	cd backend && $(PY)/alembic upgrade head

frontend-setup:
	test -f frontend/.env.local || cp frontend/.env.example frontend/.env.local
	cd frontend && npm install

backend:
	cd backend && TASKS_EAGER=true $(PY)/uvicorn app.api.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

dev:
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) --no-print-directory backend & \
	$(MAKE) --no-print-directory frontend & \
	wait

test:
	cd backend && $(PY)/pytest
	cd frontend && npx tsc --noEmit
