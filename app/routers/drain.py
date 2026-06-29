from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
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


@router.get("", response_class=HTMLResponse)
def drain_page(request: Request):
    return templates.TemplateResponse("drain.html", {
        "request": request, "clusters": None,
    })


@router.post("/parse", response_class=HTMLResponse)
def drain_parse(
    request: Request,
    log_text: str = Form(...),
    threshold: float = Form(0.5),
):
    lines = [l for l in log_text.split("\n") if l.strip()]
    if not lines:
        return templates.TemplateResponse("drain.html", {
            "request": request, "error": "No log lines provided",
        })
    clusters = drain_cluster(lines, similarity_threshold=threshold)
    return templates.TemplateResponse("drain.html", {
        "request": request, "clusters": clusters, "total_lines": len(lines),
        "threshold": threshold,
    })
