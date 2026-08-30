ACTOR_FOR_NODE = {
    "ingest": "intake",
    "classify": "sorter",
    "retry_classify": "sorter",
    "review_classify": "sorter_reviewer",
    "extract": None,  # specialist by doc type
    "retry_extract": None,
    "judge_verify": "judge",
    "arbiter": "arbiter",
    "boss_escalation": "boss",
    "human_review": "human",
    "compile_report": "reporter",
    "catalog_write": "archivist",
    "archive": "archivist",
}
