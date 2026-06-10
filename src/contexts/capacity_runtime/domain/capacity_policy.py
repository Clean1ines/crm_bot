from src.contexts.capacity_runtime.domain.capacity_decision import (
    CapacityDecision,
    CapacityDecisionStatus,
    CapacityRequest,
    CapacityResourceKind,
    CapacitySnapshot,
)


class CapacityAdmissionPolicy:
    def decide(
        self,
        *,
        request: CapacityRequest,
        snapshot: CapacitySnapshot,
    ) -> CapacityDecision:
        blocking_resources: list[CapacityResourceKind] = []
        unavailable_blocking_resources: list[CapacityResourceKind] = []

        for need in request.needs:
            available_amount = snapshot.available_for(need.resource_kind)
            if need.amount <= available_amount:
                continue

            blocking_resources.append(need.resource_kind)
            if available_amount == 0:
                unavailable_blocking_resources.append(need.resource_kind)

        if not blocking_resources:
            return CapacityDecision(
                status=CapacityDecisionStatus.ALLOW,
                work_class=request.work_class,
                blocking_resources=(),
                reason="capacity_available",
            )

        if unavailable_blocking_resources:
            return CapacityDecision(
                status=CapacityDecisionStatus.REJECT,
                work_class=request.work_class,
                blocking_resources=tuple(blocking_resources),
                reason="capacity_unavailable",
            )

        return CapacityDecision(
            status=CapacityDecisionStatus.THROTTLE,
            work_class=request.work_class,
            blocking_resources=tuple(blocking_resources),
            reason="capacity_temporarily_insufficient",
        )
