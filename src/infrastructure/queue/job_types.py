"""Known legacy execution_queue task types.

The current knowledge upload -> source ingestion -> workflow command drain
vertical is not driven by this old execution_queue.
"""

TASK_NOTIFY_MANAGER = "notify_manager"
TASK_UPDATE_METRICS = "update_metrics"
TASK_AGGREGATE_METRICS = "aggregate_metrics"

KNOWN_TASK_TYPES = {
    TASK_NOTIFY_MANAGER,
    TASK_UPDATE_METRICS,
    TASK_AGGREGATE_METRICS,
}
