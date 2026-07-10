"""Entry point. Initializes DB, seeds demo data if empty, serves the app.

    python run.py            # http://127.0.0.1:8000
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.api:app", host="127.0.0.1", port=8000, reload=False)
