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
        item_capacities: list[int] = []
        blocking_resources: list[CapacityResourceKind] = []
        unavailable_blocking_resources: list[CapacityResourceKind] = []

        for need in request.needs:
            available_amount = snapshot.available_for(need.resource_kind)
            item_capacity = available_amount // need.amount
            item_capacities.append(item_capacity)
            if item_capacity >= request.requested_items:
                continue

            blocking_resources.append(need.resource_kind)
            if available_amount == 0:
                unavailable_blocking_resources.append(need.resource_kind)

        max_by_capacity = min(item_capacities)
        max_admissible_items = min(request.requested_items, max_by_capacity)

        if max_admissible_items == request.requested_items:
            return CapacityDecision(
                status=CapacityDecisionStatus.ALLOW,
                work_class=request.work_class,
                max_admissible_items=max_admissible_items,
                blocking_resources=(),
                reason="capacity_available",
            )

        if max_admissible_items > 0:
            return CapacityDecision(
                status=CapacityDecisionStatus.THROTTLE,
                work_class=request.work_class,
                max_admissible_items=max_admissible_items,
                blocking_resources=tuple(blocking_resources),
                reason="capacity_partially_available",
            )

        if unavailable_blocking_resources:
            return CapacityDecision(
                status=CapacityDecisionStatus.REJECT,
                work_class=request.work_class,
                max_admissible_items=0,
                blocking_resources=tuple(blocking_resources),
                reason="capacity_unavailable",
            )

        return CapacityDecision(
            status=CapacityDecisionStatus.THROTTLE,
            work_class=request.work_class,
            max_admissible_items=0,
            blocking_resources=tuple(blocking_resources),
            reason="capacity_temporarily_insufficient",
        )
