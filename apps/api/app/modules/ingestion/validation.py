"""Pure catalog-aware rules; callers resolve existence and applicability first."""

from datetime import datetime, timedelta

from app.modules.facilities.schemas import FieldError, ObservationCreate, ResourceDefinition


def validate_observation(
    observation: ObservationCreate,
    resource: ResourceDefinition,
    now: datetime,
) -> list[FieldError]:
    """Return field errors without HTTP, persistence, or implicit clock access.

    Payload shape is validated by ObservationCreate. The backend must resolve
    the facility and applicable resource before calling this function.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware server timestamp.")
    if observation.resource_id != resource.resource_id:
        return [FieldError(field="resource_id", message="Resource definition does not match.")]

    errors: list[FieldError] = []
    if observation.unit != resource.unit:
        errors.append(FieldError(
            field="unit",
            message=f"Expected {resource.unit.value} for resource {resource.resource_id}.",
        ))
    if not resource.allows_fractional and not observation.available_quantity.is_integer():
        errors.append(FieldError(
            field="available_quantity",
            message=f"Use a whole number for resource {resource.resource_id}.",
        ))
    if observation.observed_at > now + timedelta(minutes=5):
        errors.append(FieldError(
            field="observed_at",
            message="Observation time must not be more than five minutes ahead of server time.",
        ))
    return errors
