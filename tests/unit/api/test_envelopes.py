import json

from fastapi.exceptions import RequestValidationError

from talk_to_me_server.api.envelopes import envelope
from talk_to_me_server.api.errors import validation_error_response


def test_envelope_status_matches_reason_code() -> None:
    response = envelope(403, "Remote management denied")

    assert response.status_code == 403
    assert json.loads(response.body) == {
        "version": 1,
        "reasonCode": 403,
        "reasonText": "Remote management denied",
    }


def test_envelope_appends_payload_after_required_keys() -> None:
    response = envelope(200, "OK", jobId="job-1")

    assert list(json.loads(response.body)) == ["version", "reasonCode", "reasonText", "jobId"]


def test_validation_error_is_400_with_structured_errors() -> None:
    error = RequestValidationError(
        [
            {
                "type": "missing",
                "loc": ("body", "values"),
                "msg": "Field required",
                "input": {},
            }
        ]
    )

    response = validation_error_response(error)
    body = json.loads(response.body)

    assert response.status_code == body["reasonCode"] == 400
    assert body["validationErrors"] == [
        {"location": ["body", "values"], "message": "Field required", "type": "missing"}
    ]


def test_text_shape_limit_validation_is_413() -> None:
    error = RequestValidationError(
        [
            {
                "type": "text_limit_exceeded",
                "loc": ("body", "values"),
                "msg": "values contains more than 255 items",
                "input": [],
            }
        ]
    )

    response = validation_error_response(error)

    assert response.status_code == json.loads(response.body)["reasonCode"] == 413
