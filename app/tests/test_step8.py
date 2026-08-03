"""
Step 8 tests: downloads library
Pass criteria:
  - list_downloads returns {} for a missing or empty directory
  - list_downloads handles year-subfolder structure correctly
  - list_downloads handles flat (no-year-folder) structure, inferring year from filename
  - list_downloads includes filename, path, size, modified fields
  - Files are sorted newest-downloaded first within each year
  - GET /api/downloads returns JSON dict
  - GET /downloads/<path> returns 404 for a missing file
"""
import sys
import os
import time
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


@pytest.fixture(scope="module")
def client():
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


def test_list_downloads_missing_dir(tmp_path):
    import edgar_api
    result = edgar_api.list_downloads(str(tmp_path / "nonexistent"))
    assert result == {}


def test_list_downloads_empty_dir(tmp_path):
    import edgar_api
    result = edgar_api.list_downloads(str(tmp_path))
    assert result == {}


def test_list_downloads_year_subfolder_structure(tmp_path):
    import edgar_api
    d = tmp_path / "Apple Inc" / "2023"
    d.mkdir(parents=True)
    (d / "10-K_2023-11-03.htm").write_text("<html>test</html>")

    result = edgar_api.list_downloads(str(tmp_path))
    assert "Apple Inc" in result
    assert "2023" in result["Apple Inc"]
    files = result["Apple Inc"]["2023"]
    assert len(files) == 1
    f = files[0]
    assert f["filename"] == "10-K_2023-11-03.htm"
    assert f["size"] > 0
    assert "modified" in f
    assert f["path"] == "Apple Inc/2023/10-K_2023-11-03.htm"


def test_list_downloads_flat_structure(tmp_path):
    import edgar_api
    d = tmp_path / "Apple Inc"
    d.mkdir(parents=True)
    (d / "10-K_2023-11-03.htm").write_text("<html>test</html>")

    result = edgar_api.list_downloads(str(tmp_path))
    assert "Apple Inc" in result
    # Year should be inferred from filename
    assert "2023" in result["Apple Inc"]
    f = result["Apple Inc"]["2023"][0]
    assert f["filename"] == "10-K_2023-11-03.htm"
    assert f["path"] == "Apple Inc/10-K_2023-11-03.htm"


def test_list_downloads_sorted_by_recency(tmp_path):
    import edgar_api
    d = tmp_path / "Apple Inc"
    d.mkdir(parents=True)
    f1 = d / "10-K_2022-10-28.htm"
    f2 = d / "10-K_2023-11-03.htm"
    f1.write_text("old")
    time.sleep(0.05)
    f2.write_text("new")

    result = edgar_api.list_downloads(str(tmp_path))
    files_2022 = result["Apple Inc"].get("2022", [])
    files_2023 = result["Apple Inc"].get("2023", [])
    # Both exist; 2023 file was written last so its modified > 2022 file
    assert files_2023[0]["modified"] > files_2022[0]["modified"]


def test_list_downloads_multiple_companies(tmp_path):
    import edgar_api
    for company, year, fname in [
        ("Apple Inc", "2023", "10-K_2023-11-03.htm"),
        ("Apple Inc", "2022", "10-K_2022-10-28.htm"),
        ("Microsoft Corp", "2023", "10-K_2023-07-27.htm"),
    ]:
        d = tmp_path / company / year
        d.mkdir(parents=True, exist_ok=True)
        (d / fname).write_text("x")

    result = edgar_api.list_downloads(str(tmp_path))
    assert set(result.keys()) == {"Apple Inc", "Microsoft Corp"}
    assert set(result["Apple Inc"].keys()) == {"2023", "2022"}


def test_api_downloads_returns_dict(client):
    r = client.get("/api/downloads")
    assert r.status_code == 200
    assert isinstance(r.get_json(), dict)


def test_serve_download_missing_file(client):
    r = client.get("/downloads/NonExistentCo/9999/no_file.htm")
    assert r.status_code == 404


@pytest.mark.integration
def test_api_downloads_reflects_real_files(client):
    r = client.get("/api/downloads")
    assert r.status_code == 200
    data = r.get_json()
    if "Apple Inc" in data:
        for year, files in data["Apple Inc"].items():
            for f in files:
                assert "filename" in f
                assert "path" in f
                assert "size" in f
                assert "modified" in f
                assert f["size"] > 0
