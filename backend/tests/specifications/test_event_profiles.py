from app.event_profiles.registry import event_profile_registry
from app.specifications.models import CapabilityState, VerificationStatus


def test_only_source_bounded_dvop_profile_is_enabled() -> None:
    profile = event_profile_registry.profile
    assert profile.event_code == "DVOP"
    assert profile.capability is CapabilityState.PARTIAL
    assert profile.source.verification_status is VerificationStatus.EXTERNAL_VALIDATION_REQUIRED
    assert len(profile.catalogue_only_events) == 8
    assert all(
        item.capability is CapabilityState.CATALOGUE_ONLY for item in profile.catalogue_only_events
    )
