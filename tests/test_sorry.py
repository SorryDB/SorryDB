import json
from dataclasses import asdict

from sorrydb.database.sorry import Sorry, SorryJSONEncoder, sorry_object_hook
from tests.mock_sorries import sorry_with_defaults


def test_sorry_asdict_from_dict():
    original_sorry = sorry_with_defaults()

    sorry_dict = asdict(original_sorry)

    reconstructed_sorry = Sorry.from_dict(sorry_dict)

    assert asdict(original_sorry) == asdict(reconstructed_sorry)


def test_sorry_json_serialization_with_custom_encoder(tmp_path):
    original_sorry = sorry_with_defaults()  # test sorry object

    tmp_file_path = tmp_path / "sorry_test.json"

    # Write the Sorry object directly to JSON using the custom encoder
    with open(tmp_file_path, "w") as tmp_file:
        json.dump(original_sorry, tmp_file, cls=SorryJSONEncoder)

    # Read the JSON file back
    with open(tmp_file_path, "r") as file:
        # Convert JSON directly to a Sorry object using the custom object hook
        reconstructed_sorry = json.load(file, object_hook=sorry_object_hook)

    assert original_sorry == reconstructed_sorry
