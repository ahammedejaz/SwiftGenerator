import pytest

from app.agents.errors import AiServiceError
from app.agents.preprocessing import resolve_placeholder, sanitize_user_text


def test_sensitive_values_are_replaced_with_request_local_placeholders() -> None:
    identifiers = iter(["AAAA0001", "AAAA0002", "AAAA0003"])
    result = sanitize_user_text(
        "Receive ISIN XS0000000001 into safekeeping account SYNTHSAFE01 "
        "with sender reference CLIENTREF01 against payment.",
        6000,
        id_factory=lambda: next(identifiers),
    )
    assert "XS0000000001" not in result.text
    assert "SYNTHSAFE01" not in result.text
    assert "CLIENTREF01" not in result.text
    assert len(result.placeholders) == 3
    issued = next(iter(result.placeholders.values()))
    assert resolve_placeholder(issued.token, issued.placeholder_id, result.placeholders) == issued


def test_unknown_or_modified_placeholder_is_rejected() -> None:
    result = sanitize_user_text(
        "Receive ISIN XS0000000001 against payment.",
        6000,
        id_factory=lambda: "AAAA0001",
    )
    with pytest.raises(AiServiceError) as caught:
        resolve_placeholder("[[SMS_ISIN_BBBB0002]]", "BBBB0002", result.placeholders)
    assert caught.value.code == "AI_UNSAFE_RESPONSE"


def test_placeholder_map_can_be_disposed() -> None:
    result = sanitize_user_text(
        "Receive ISIN XS0000000001 against payment.",
        6000,
        id_factory=lambda: "AAAA0001",
    )
    assert result.placeholders
    result.clear()
    assert result.placeholders == {}


def test_oversized_and_unicode_control_inputs_are_rejected_without_truncation() -> None:
    with pytest.raises(AiServiceError) as oversized:
        sanitize_user_text("x" * 11, 10)
    assert oversized.value.code == "AI_INPUT_TOO_LARGE"
    with pytest.raises(AiServiceError) as control:
        sanitize_user_text("receive\u202e deliver", 6000)
    assert control.value.code == "AI_UNSAFE_RESPONSE"


@pytest.mark.parametrize(
    "raw",
    [
        "{2:MT541}{4:\n:20C::SEME//TEST\n-}",
        "{1:F01SYNTH}{2:I541SYNTH}{4:\n:16R:GENL\n-}",
    ],
)
def test_raw_mt_content_is_kept_out_of_the_model_boundary(raw: str) -> None:
    with pytest.raises(AiServiceError) as caught:
        sanitize_user_text(raw, 6000)
    assert caught.value.code == "AI_RAW_CONTENT_NOT_ACCEPTED"
