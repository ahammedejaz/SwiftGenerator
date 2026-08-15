"""FIN application-message envelope construction.

Rules this module holds itself to:

* Blocks are only emitted when the value is genuinely available. A block whose content is
  allocated by an external messaging interface or by the network is never invented.
* Every emitted value carries a :class:`FieldOrigin` so a consumer can see who is
  accountable for it.
* Block 5 (trailer) is emitted only when the client profile explicitly configures trailer
  fields. MAC, CHK, PDE, PDM, DLM and authentication trailers are interface or network
  generated; the platform refuses to produce them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.profiles.loader import ClientProfile, FinEnvelopeProfile
from app.studio.models import (
    EnvelopeField,
    EnvelopeOverride,
    FieldOrigin,
    IssueSeverity,
    ValidationIssue,
    ValidationLayer,
)

ADDRESS_PATTERN = re.compile(r"^[A-Z0-9]{12}$")
MUR_PATTERN = re.compile(r"^[A-Z0-9._/-]{1,16}$")

#: Trailer tags the platform will never generate, whatever a profile asks for.
FORBIDDEN_TRAILER_TAGS = frozenset({"MAC", "CHK", "PDE", "PDM", "DLM", "TNG", "SYS"})


class FinEnvelopeUnavailable(Exception):
    """Raised when a complete FIN message cannot be produced without inventing a value."""

    def __init__(self, issues: list[ValidationIssue]) -> None:
        super().__init__("; ".join(issue.message for issue in issues))
        self.issues = issues


@dataclass(frozen=True)
class FinMessage:
    text: str
    fields: list[EnvelopeField]
    warnings: list[ValidationIssue]


def _issue(rule_id: str, message: str, suggestion: str, field: str) -> ValidationIssue:
    return ValidationIssue(
        rule_id=rule_id,
        severity=IssueSeverity.ERROR,
        layer=ValidationLayer.FIN_ENVELOPE,
        field=field,
        message=message,
        suggestion=suggestion,
    )


def _resolve(
    profile: ClientProfile, override: EnvelopeOverride | None
) -> tuple[FinEnvelopeProfile | None, dict[str, tuple[str | None, FieldOrigin]]]:
    """Merge profile configuration with per-request overrides, tracking value origin."""
    configured = profile.fin_envelope
    override = override or EnvelopeOverride()

    def pick(
        request_value: str | None, profile_value: str | None
    ) -> tuple[str | None, FieldOrigin]:
        if request_value:
            return request_value, FieldOrigin.USER_ENTERED
        if profile_value:
            return profile_value, FieldOrigin.PROFILE_CONFIGURED
        return None, FieldOrigin.INTERFACE_GENERATED

    resolved = {
        "sender": pick(
            override.sender, configured.sender_logical_terminal if configured else None
        ),
        "receiver": pick(override.receiver, configured.receiver_address if configured else None),
        "sessionNumber": pick(
            override.session_number, configured.session_number if configured else None
        ),
        "sequenceNumber": pick(
            override.sequence_number, configured.sequence_number if configured else None
        ),
        "priority": pick(override.priority, configured.priority if configured else None),
        "messageUserReference": (
            (override.message_user_reference, FieldOrigin.USER_ENTERED)
            if override.message_user_reference
            else (None, FieldOrigin.USER_ENTERED)
        ),
    }
    return configured, resolved


def envelope_availability(profile: ClientProfile) -> list[ValidationIssue]:
    """Report what stops this profile from producing a complete FIN message, if anything."""
    configured = profile.fin_envelope
    if configured is None:
        return [
            _issue(
                "FIN_ENVELOPE_NOT_CONFIGURED",
                f"Profile {profile.profile_id} has no configured FIN interface values.",
                "Add a finEnvelope block to the client profile, or use Block 4 output.",
                "finEnvelope",
            )
        ]
    issues: list[ValidationIssue] = []
    if not configured.session_number:
        issues.append(
            _issue(
                "FIN_SESSION_NUMBER_NOT_SUPPLIED",
                "The session number is allocated by the messaging interface and is not configured.",
                "Configure finEnvelope.sessionNumber, or supply envelope.sessionNumber "
                "on the request.",
                "sessionNumber",
            )
        )
    if not configured.sequence_number:
        issues.append(
            _issue(
                "FIN_SEQUENCE_NUMBER_NOT_SUPPLIED",
                "The sequence number is allocated by the messaging interface and is not "
                "configured.",
                "Configure finEnvelope.sequenceNumber, or supply envelope.sequenceNumber "
                "on the request.",
                "sequenceNumber",
            )
        )
    return issues


def build_fin_message(
    *,
    message_type: str,
    block_4: str,
    profile: ClientProfile,
    override: EnvelopeOverride | None = None,
) -> FinMessage:
    """Assemble `{1:}{2:}[{3:}]{4:...-}[{5:}]`.

    :raises FinEnvelopeUnavailable: when a required value is neither supplied on the
        request nor configured on the profile. The envelope is never completed by
        guessing.
    """
    configured, resolved = _resolve(profile, override)
    issues: list[ValidationIssue] = []

    sender, sender_origin = resolved["sender"]
    receiver, receiver_origin = resolved["receiver"]
    session, session_origin = resolved["sessionNumber"]
    sequence, sequence_origin = resolved["sequenceNumber"]
    priority, priority_origin = resolved["priority"]
    mur, mur_origin = resolved["messageUserReference"]

    if not sender:
        issues.append(
            _issue(
                "FIN_SENDER_NOT_SUPPLIED",
                "A 12-character sender logical terminal is required for Block 1.",
                "Configure finEnvelope.senderLogicalTerminal on the client profile.",
                "sender",
            )
        )
    elif not ADDRESS_PATTERN.fullmatch(sender):
        issues.append(
            _issue(
                "FIN_SENDER_INVALID",
                f"Sender logical terminal '{sender}' must be 12 uppercase alphanumerics.",
                "Use an 8-character BIC, a 1-character logical terminal and a 3-character branch.",
                "sender",
            )
        )
    if not receiver:
        issues.append(
            _issue(
                "FIN_RECEIVER_NOT_SUPPLIED",
                "A 12-character receiver address is required for Block 2.",
                "Configure finEnvelope.receiverAddress on the client profile.",
                "receiver",
            )
        )
    elif not ADDRESS_PATTERN.fullmatch(receiver):
        issues.append(
            _issue(
                "FIN_RECEIVER_INVALID",
                f"Receiver address '{receiver}' must be 12 uppercase alphanumerics.",
                "Use an 8-character BIC, a 1-character logical terminal and a 3-character branch.",
                "receiver",
            )
        )
    if not session:
        issues.append(
            _issue(
                "FIN_SESSION_NUMBER_NOT_SUPPLIED",
                "Block 1 requires a session number, which the messaging interface allocates.",
                "Configure finEnvelope.sessionNumber or send envelope.sessionNumber; "
                "the platform will not invent one.",
                "sessionNumber",
            )
        )
    if not sequence:
        issues.append(
            _issue(
                "FIN_SEQUENCE_NUMBER_NOT_SUPPLIED",
                "Block 1 requires a sequence number, which the messaging interface allocates.",
                "Configure finEnvelope.sequenceNumber or send envelope.sequenceNumber; "
                "the platform will not invent one.",
                "sequenceNumber",
            )
        )
    if mur and not MUR_PATTERN.fullmatch(mur):
        issues.append(
            _issue(
                "FIN_MUR_INVALID",
                f"Message user reference '{mur}' must be 1-16 characters from A-Z 0-9 . _ / -.",
                "Shorten the reference or remove unsupported characters.",
                "messageUserReference",
            )
        )
    digits = message_type[2:] if message_type.upper().startswith("MT") else message_type
    if not re.fullmatch(r"\d{3}", digits):
        issues.append(
            _issue(
                "FIN_MESSAGE_TYPE_INVALID",
                f"'{message_type}' is not a three-digit FIN message type.",
                "Use a message type such as MT541.",
                "messageType",
            )
        )
    if issues:
        raise FinEnvelopeUnavailable(issues)

    assert configured is not None  # guaranteed: sender/receiver resolution would have failed
    application_id = configured.application_id
    service_id = configured.service_id
    effective_priority = priority or "N"

    block_1 = f"{{1:{application_id}{service_id}{sender}{session}{sequence}}}"
    block_2 = f"{{2:I{digits}{receiver}{effective_priority}}}"

    warnings: list[ValidationIssue] = []
    block_3 = ""
    if mur and configured.include_message_user_reference:
        block_3 = f"{{3:{{108:{mur}}}}}"
    elif mur and not configured.include_message_user_reference:
        warnings.append(
            ValidationIssue(
                rule_id="FIN_MUR_SUPPRESSED_BY_PROFILE",
                severity=IssueSeverity.WARNING,
                layer=ValidationLayer.FIN_ENVELOPE,
                field="messageUserReference",
                message="The profile does not include a user header, so the message user "
                "reference was not written to Block 3.",
                suggestion="Set finEnvelope.includeMessageUserReference to true to emit "
                "Block 3 field 108.",
            )
        )

    block_5 = ""
    rejected_trailers = sorted(
        tag for tag in configured.trailer_fields if tag.upper() in FORBIDDEN_TRAILER_TAGS
    )
    if rejected_trailers:
        warnings.append(
            ValidationIssue(
                rule_id="FIN_TRAILER_NOT_GENERATED",
                severity=IssueSeverity.WARNING,
                layer=ValidationLayer.FIN_ENVELOPE,
                field="trailerFields",
                message="Trailer values "
                + ", ".join(rejected_trailers)
                + " are generated by the messaging interface or the network and were not "
                "written to Block 5.",
                suggestion="Let the receiving interface add authentication and checksum "
                "trailers.",
            )
        )
    emitted_trailers = {
        tag.upper(): value
        for tag, value in configured.trailer_fields.items()
        if tag.upper() not in FORBIDDEN_TRAILER_TAGS
    }
    if emitted_trailers:
        inner = "".join(f"{{{tag}:{value}}}" for tag, value in sorted(emitted_trailers.items()))
        block_5 = f"{{5:{inner}}}"

    text = f"{block_1}\n{block_2}\n"
    if block_3:
        text += f"{block_3}\n"
    text += block_4
    if block_5:
        text += f"\n{block_5}"

    fields = [
        EnvelopeField(
            block="1",
            name="Application identifier",
            value=application_id,
            origin=FieldOrigin.PROFILE_CONFIGURED,
            explanation="FIN application identifier configured on the client profile.",
        ),
        EnvelopeField(
            block="1",
            name="Service identifier",
            value=service_id,
            origin=FieldOrigin.PROFILE_CONFIGURED,
            explanation="FIN service identifier configured on the client profile.",
        ),
        EnvelopeField(
            block="1",
            name="Sender logical terminal",
            value=sender,
            origin=sender_origin,
            explanation="Sending institution address and logical terminal.",
        ),
        EnvelopeField(
            block="1",
            name="Session number",
            value=session,
            origin=session_origin,
            explanation="Configured test-interface session number. A live Swift interface "
            "allocates this value; the platform does not generate it.",
        ),
        EnvelopeField(
            block="1",
            name="Sequence number",
            value=sequence,
            origin=sequence_origin,
            explanation="Configured test-interface sequence number. A live Swift interface "
            "allocates this value; the platform does not generate it.",
        ),
        EnvelopeField(
            block="2",
            name="Input/output identifier",
            value="I",
            origin=FieldOrigin.APPLICATION_GENERATED,
            explanation="Input message sent by the configured sender.",
        ),
        EnvelopeField(
            block="2",
            name="Message type",
            value=digits,
            origin=FieldOrigin.APPLICATION_GENERATED,
            explanation="Derived from the selected message type.",
        ),
        EnvelopeField(
            block="2",
            name="Receiver address",
            value=receiver,
            origin=receiver_origin,
            explanation="Receiving institution address and logical terminal.",
        ),
        EnvelopeField(
            block="2",
            name="Priority",
            value=effective_priority,
            origin=priority_origin if priority else FieldOrigin.PROFILE_CONFIGURED,
            explanation="Message priority: N for normal, U for urgent.",
        ),
        EnvelopeField(
            block="3",
            name="Message user reference (108)",
            value=mur if block_3 else None,
            origin=mur_origin if block_3 else FieldOrigin.USER_ENTERED,
            explanation=(
                "User header reference supplied with the request."
                if block_3
                else "No message user reference was supplied, so Block 3 was not emitted."
            ),
        ),
        EnvelopeField(
            block="4",
            name="Text block",
            value="present",
            origin=FieldOrigin.APPLICATION_GENERATED,
            explanation="Composed deterministically from the configured message specification.",
        ),
        EnvelopeField(
            block="5",
            name="Trailer",
            value=block_5 or None,
            origin=FieldOrigin.NETWORK_GENERATED,
            explanation=(
                "Only profile-configured trailer values are written."
                if block_5
                else "No trailer was emitted. MAC, CHK and authentication trailers are added "
                "by the messaging interface and the network, and are never fabricated here."
            ),
        ),
    ]
    return FinMessage(text=text, fields=fields, warnings=warnings)
