from collections import Counter


def recovery_metrics(reports, states):
    count = len(reports)
    distribution = Counter()
    recoverable = set()
    for case, state in states.items():
        for event in state.get("trace_events", []):
            if event.get("type") == "failure_classified":
                distribution[event["diagnosis"]["failure_type"]] += 1
                if event["action"] != "stop":
                    recoverable.add(case)
    recovered = sum(r["case_id"] in recoverable and r["verdict"] == "resolved" for r in reports)
    return {
        "avg_coder_retries": sum(s.get("coder_retries", 0) for s in states.values()) / count if count else 0,
        "avg_replans": sum(s.get("replans", 0) for s in states.values()) / count if count else 0,
        "avg_step_count": sum(s.get("step_count", 0) for s in states.values()) / count if count else 0,
        "avg_elapsed_seconds": sum(s.get("elapsed_seconds", 0) for s in states.values()) / count if count else 0,
        "failure_type_distribution": dict(distribution),
        "recovery_success_rate": recovered / len(recoverable) if recoverable else None,
    }
