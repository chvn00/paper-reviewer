.PHONY: init test check demo health dashboard serve backup

PYTHON ?= python3

init:
	$(PYTHON) app.py inicializar

test:
	$(PYTHON) -m unittest discover -v

check:
	$(PYTHON) -m compileall -q app.py manzanares_agent tests
	$(PYTHON) -m unittest discover -v

demo:
	$(PYTHON) app.py demo --reset

health:
	$(PYTHON) app.py salud

dashboard:
	$(PYTHON) app.py tablero

serve:
	$(PYTHON) app.py servir

backup:
	$(PYTHON) app.py backup
