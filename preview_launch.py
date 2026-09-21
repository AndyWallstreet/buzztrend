# -*- coding: utf-8 -*-
"""Claude 미리보기용 실행기 — 배정된 포트(PORT 환경변수)로 Streamlit 을 띄운다. (여러 채팅이 같은 포트를 두고 충돌하지 않게)"""
import os
import sys
from pathlib import Path

from streamlit.web import cli

sys.argv = ["streamlit", "run", str(Path(__file__).resolve().parent / "streamlit_app.py"),
            "--server.port", os.environ.get("PORT", "8602"), "--server.headless", "true",
            "--browser.gatherUsageStats", "false"]
cli.main()
