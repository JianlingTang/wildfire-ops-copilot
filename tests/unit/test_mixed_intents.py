from app.services.mixed_intents import is_exposure_action_request


def test_detects_exposure_action_request() -> None:
    assert is_exposure_action_request(
        "What are main roads and assets within this ROI? Generate an alert for people to avoid this area."
    )


def test_does_not_treat_plain_exposure_lookup_as_mixed() -> None:
    assert not is_exposure_action_request("What roads and assets are within this ROI?")


def test_does_not_treat_plain_action_as_mixed() -> None:
    assert not is_exposure_action_request("Draft a public advisory for this alert.")
