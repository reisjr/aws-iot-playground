from ddd_alerts_processor_lambda import lambda_function
from tests import *
import json


def load_lambda_event(name):
    data = None
    
    with open(name) as json_file:
        data = json.load(json_file)

    return data


def test_get_thing_name():
    event = load_lambda_event("tests/sample_payload_msgsent.json")
    thing_name = lambda_function.get_thing_name(event)

    assert thing_name == "dev-IZWB"