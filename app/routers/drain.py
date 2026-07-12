from fastapi import APIRouter, Body, Request
from app.template_utils import get_templates

router = APIRouter(prefix="/drain", tags=["drain"])
templates = get_templates()


def drain_tokenize(line: str):
    return line.strip().split()


def drain_cluster(logs: list[str], similarity_threshold: float = 0.5) -> list[dict]:
    clusters = []
    for log in logs:
        tokens = drain_tokenize(log)
        best_match = None
        best_score = 0
        for c in clusters:
            template_tokens = c["template_tokens"]
            if len(tokens) != len(template_tokens):
                continue
            matches = sum(1 for i in range(len(tokens)) if tokens[i] == template_tokens[i])
            score = matches / len(tokens)
            if score > best_score:
                best_score = score
                best_match = c
        if best_match and best_score >= similarity_threshold:
            best_match["count"] += 1
            best_match["logs"].append(log)
            # Merge template: replace differing tokens with <*>
            tt = best_match["template_tokens"]
            for i in range(len(tokens)):
                if tt[i] != tokens[i]:
                    tt[i] = "<*>"
        else:
            clusters.append({
                "template": log,
                "template_tokens": tokens[:],
                "count": 1,
                "logs": [log],
            })
    return [
        {"template": c["template"], "count": c["count"], "logs": c["logs"]}
        for c in sorted(clusters, key=lambda x: -x["count"])
    ]


@router.get("/status")
def status():
    return {"module": "drain", "status": "ok"}


@router.post("/cluster")
def cluster_logs(logs: list[str] = Body(...), similarity_threshold: float = 0.5):
    return {"clusters": drain_cluster(logs, similarity_threshold)}


