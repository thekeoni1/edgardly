"""
Step 1 tests: project scaffold
Pass criteria:
  - data/ and downloads/ directories exist
  - Flask app starts and serves HTTP 200 at /
  - Response contains expected page title
"""
import os
import sys
import time
import subprocess
import requests
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_data_dir_exists():
    assert os.path.isdir(os.path.join(BASE_DIR, "data")), "data/ directory missing"


def test_downloads_dir_exists():
    assert os.path.isdir(os.path.join(BASE_DIR, "downloads")), "downloads/ directory missing"


def test_app_py_exists():
    assert os.path.isfile(os.path.join(BASE_DIR, "app.py")), "app.py missing"


def test_index_html_exists():
    assert os.path.isfile(
        os.path.join(BASE_DIR, "templates", "index.html")
    ), "templates/index.html missing"


def test_style_css_exists():
    assert os.path.isfile(
        os.path.join(BASE_DIR, "static", "style.css")
    ), "static/style.css missing"


@pytest.mark.integration
@pytest.mark.timeout(15)
def test_homepage_returns_200():
    """Start the Flask server, hit it, confirm 200, then shut it down."""
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Wait for server to be ready
        for _ in range(10):
            time.sleep(1)
            try:
                r = requests.get("http://localhost:5000", timeout=2)
                assert r.status_code == 200
                assert "EDGAR" in r.text
                return
            except requests.ConnectionError:
                continue
        pytest.fail("Server did not become reachable within 10 seconds")
    finally:
        proc.terminate()
        proc.wait(timeout=5)
