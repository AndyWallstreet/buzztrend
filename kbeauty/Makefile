# make is not installed on this Windows machine — these targets document intent.
# Actual entry point: python cli.py <command>  (see PLAN.md)
PY = python

backfill:
	$(PY) cli.py backfill

refresh:
	$(PY) cli.py refresh

weekly:
	$(PY) cli.py weekly --week $(WEEK)

monthly:
	$(PY) cli.py monthly --month $(MONTH)

report:
	$(PY) cli.py report

import-notes:
	$(PY) cli.py import-notes --file $(FILE)

publish:
	$(PY) cli.py publish --file $(FILE)

test:
	$(PY) cli.py test
