import json
from pathlib import Path


def load_multiple_sorries_as_json() -> dict:
    project_root = Path(__file__).resolve().parent.parent.parent
    sample_sorries_path = project_root / "doc" / "sample_sorry_list.json"
    with open(sample_sorries_path, "r") as f:
        return json.load(f)["sorries"]


def load_single_sorry_as_json() -> dict:
    return load_multiple_sorries_as_json()[0]


def test_add_sorry(client):
    sorry = load_single_sorry_as_json()
    response = client.post("/sorries/", json=sorry)
    assert response.status_code == 201


def test_add_multiple_sorries(client):
    sorries = load_multiple_sorries_as_json()
    response = client.post("/sorries/", json=sorries)
    assert response.status_code == 201
    assert len(response.json()) == len(sorries)
