import json
import time
import logging
from datetime import datetime
from difflib import SequenceMatcher
from fastapi import APIRouter, Depends, Query, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AgentGroundTruth, AgentGroundTruthRun, AIProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent/api/ground-truth", tags=["agent_ground_truth"])


def _gt_to_dict(g):
    return {
        "id": g.id,
        "name": g.name,
        "category": g.category,
        "question": g.question,
        "expected_answer": g.expected_answer,
        "expected_tools": json.loads(g.expected_tools) if g.expected_tools else [],
        "tags": g.tags or "",
        "difficulty": g.difficulty,
        "is_active": bool(g.is_active),
        "created_at": g.created_at.strftime("%Y-%m-%d %H:%M:%S") if g.created_at else None,
        "updated_at": g.updated_at.strftime("%Y-%m-%d %H:%M:%S") if g.updated_at else None,
    }


def _run_to_dict(r, test_name: str = ""):
    actual_tools_raw = []
    try:
        actual_tools_raw = json.loads(r.actual_tools) if r.actual_tools else []
    except (json.JSONDecodeError, TypeError):
        actual_tools_raw = []

    actual_tools_norm = []
    for item in actual_tools_raw:
        if isinstance(item, str):
            actual_tools_norm.append({"name": item, "is_success": True})
        elif isinstance(item, dict):
            actual_tools_norm.append({
                "name": item.get("name", ""),
                "is_success": bool(item.get("is_success", True)),
                "latency_ms": item.get("latency_ms", 0),
            })

    return {
        "id": r.id,
        "test_id": r.test_id,
        "test_name": test_name,
        "session_id": r.session_id,
        "provider_id": r.provider_id,
        "model_name": r.model_name,
        "actual_answer": (r.actual_answer or "")[:500],
        "actual_tools": actual_tools_norm,
        "answer_score": r.answer_score,
        "tool_score": r.tool_score,
        "total_score": r.total_score,
        "latency_ms": r.latency_ms,
        "error": r.error or "",
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
    }


@router.get("/tests")
def list_tests(
    category: str = "",
    is_active: bool = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(AgentGroundTruth)
    if category:
        q = q.filter(AgentGroundTruth.category == category)
    if is_active is not None:
        q = q.filter(AgentGroundTruth.is_active == is_active)
    elif not include_inactive:
        q = q.filter(AgentGroundTruth.is_active == True)
    items = q.order_by(AgentGroundTruth.created_at.desc()).all()
    return JSONResponse({"items": [_gt_to_dict(g) for g in items], "total": len(items)})


@router.post("/tests")
def create_test(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        gt = AgentGroundTruth(
            name=payload.get("name", "").strip(),
            category=payload.get("category", "qa"),
            question=payload.get("question", ""),
            expected_answer=payload.get("expected_answer", ""),
            expected_tools=json.dumps(payload.get("expected_tools", []), ensure_ascii=False),
            tags=payload.get("tags", ""),
            difficulty=payload.get("difficulty", "medium"),
            is_active=bool(payload.get("is_active", True)),
        )
        if not gt.name:
            return JSONResponse({"ok": False, "error": "名称不能为空"}, status_code=400)
        if not gt.question:
            return JSONResponse({"ok": False, "error": "问题不能为空"}, status_code=400)
        db.add(gt)
        db.commit()
        db.refresh(gt)
        return JSONResponse({"ok": True, "id": gt.id, "item": _gt_to_dict(gt)})
    except Exception as e:
        logger.exception("create_test failed")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.put("/tests/{test_id}")
def update_test(test_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        gt = db.query(AgentGroundTruth).filter(AgentGroundTruth.id == test_id).first()
        if not gt:
            return JSONResponse({"error": "not found"}, status_code=404)
        if "name" in payload:
            gt.name = payload["name"]
        if "category" in payload:
            gt.category = payload["category"]
        if "question" in payload:
            gt.question = payload["question"]
        if "expected_answer" in payload:
            gt.expected_answer = payload["expected_answer"]
        if "expected_tools" in payload:
            gt.expected_tools = json.dumps(payload["expected_tools"], ensure_ascii=False)
        if "tags" in payload:
            gt.tags = payload["tags"]
        if "difficulty" in payload:
            gt.difficulty = payload["difficulty"]
        if "is_active" in payload:
            gt.is_active = bool(payload["is_active"])
        gt.updated_at = datetime.now()
        db.commit()
        db.refresh(gt)
        return JSONResponse({"ok": True, "item": _gt_to_dict(gt)})
    except Exception as e:
        logger.exception("update_test failed")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.delete("/tests/{test_id}")
def delete_test(test_id: int, hard: bool = Query(False), db: Session = Depends(get_db)):
    """软删除：默认将 is_active 置为 False，保留历史 run 记录。hard=True 时物理删除。"""
    try:
        gt = db.query(AgentGroundTruth).filter(AgentGroundTruth.id == test_id).first()
        if not gt:
            return JSONResponse({"error": "not found"}, status_code=404)
        if hard:
            db.query(AgentGroundTruthRun).filter(AgentGroundTruthRun.test_id == test_id).delete()
            db.query(AgentGroundTruth).filter(AgentGroundTruth.id == test_id).delete()
        else:
            gt.is_active = False
            gt.updated_at = datetime.now()
        db.commit()
        return JSONResponse({"ok": True, "hard": hard})
    except Exception as e:
        logger.exception("delete_test failed")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/tests/{test_id}/run")
def run_single_test(
    test_id: int,
    provider_id: int = Query(0),
    max_rounds: int = Query(3, ge=1, le=5),
    db: Session = Depends(get_db),
):
    """执行 GroundTruth 用例：真实 Agent 循环（LLM → 工具执行 → 回填 → 再调 LLM）。

    与生产 Agent 的差异：
    - 不创建 chat_session / chat_message / ToolInvocation（避免污染生产数据）
    - 不走 PendingAction 确认闭环（离线评测场景，工具直接执行）
    - 限制 max_rounds 防止无限循环
    """
    try:
        gt = db.query(AgentGroundTruth).filter(AgentGroundTruth.id == test_id).first()
        if not gt:
            return JSONResponse({"error": "not found"}, status_code=404)

        provider = None
        if provider_id:
            provider = db.query(AIProvider).filter(
                AIProvider.id == provider_id, AIProvider.is_enabled == True
            ).first()
        if not provider:
            provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
        if not provider:
            return JSONResponse({"error": "未配置启用的 AI Provider"}, status_code=400)

        from app.services.agent_service import call_llm, get_mcp_manifest
        from app.services.mcp_registry import call_mcp_tool

        mcp_tools = get_mcp_manifest()
        openai_tools = [{
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        } for t in mcp_tools]

        system_prompt = (
            "你是 AIOps 运维助手。请根据用户问题选择合适的工具调用并给出回答。"
            "工具调用后请基于工具返回的真实结果作答，不要编造数据。"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": gt.question},
        ]

        start = time.time()
        executed_tools = []
        final_answer = ""
        error_text = ""

        for round_idx in range(max_rounds):
            response = call_llm(provider, messages, openai_tools if openai_tools else None)
            if "error" in response:
                error_text = response["error"]
                break

            choice = response.get("choices", [{}])[0]
            resp_msg = choice.get("message", {})
            content = resp_msg.get("content", "") or ""
            tool_calls_raw = resp_msg.get("tool_calls") or []

            if not tool_calls_raw:
                final_answer = content
                break

            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {
                        "id": tc.get("id", f"call_{i}"),
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"].get("arguments", "{}"),
                        },
                    } for i, tc in enumerate(tool_calls_raw)
                ],
            })

            for i, tc in enumerate(tool_calls_raw):
                tool_name = tc["function"]["name"]
                try:
                    arguments = json.loads(tc["function"].get("arguments", "{}"))
                except (json.JSONDecodeError, KeyError):
                    arguments = {}

                t_start = time.time()
                try:
                    tool_result = call_mcp_tool(
                        tool_name, arguments, db=db, user_id=None, allow_internal=False
                    )
                    is_success = tool_result.get("status") == "success"
                except Exception as e:
                    tool_result = {"status": "error", "message": f"工具执行异常: {e}"}
                    is_success = False
                t_latency = int((time.time() - t_start) * 1000)

                executed_tools.append({
                    "name": tool_name,
                    "is_success": is_success,
                    "latency_ms": t_latency,
                })

                try:
                    tool_content = json.dumps(tool_result, ensure_ascii=False)[:4000]
                except Exception:
                    tool_content = str(tool_result)[:4000]

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", f"call_{i}"),
                    "content": tool_content,
                })

            final_answer = content

        if not final_answer and error_text:
            return JSONResponse({"ok": False, "message": error_text}, status_code=200)

        latency = int((time.time() - start) * 1000)
        expected_tools = json.loads(gt.expected_tools) if gt.expected_tools else []
        tool_score = _calc_tool_score(executed_tools, expected_tools)
        answer_score = _calc_answer_similarity(final_answer, gt.expected_answer)
        total_score = round(answer_score * 0.6 + tool_score * 0.4, 3)

        run = AgentGroundTruthRun(
            test_id=test_id,
            provider_id=provider.id,
            model_name=provider.default_model or "",
            actual_answer=final_answer,
            actual_tools=json.dumps(executed_tools, ensure_ascii=False),
            answer_score=answer_score,
            tool_score=tool_score,
            total_score=total_score,
            latency_ms=latency,
            error=error_text,
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        test_name = gt.name or ""
        return JSONResponse({"ok": True, "run": _run_to_dict(run, test_name)})
    except Exception as e:
        logger.exception("run_single_test failed")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.get("/runs")
def list_runs(
    test_id: int = Query(0),
    category: str = Query(""),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(AgentGroundTruthRun).join(
        AgentGroundTruth, AgentGroundTruth.id == AgentGroundTruthRun.test_id
    )
    if test_id:
        q = q.filter(AgentGroundTruthRun.test_id == test_id)
    if category:
        q = q.filter(AgentGroundTruth.category == category)
    items = q.order_by(AgentGroundTruthRun.created_at.desc()).limit(limit).all()

    test_ids = {r.test_id for r in items}
    test_name_map = {}
    if test_ids:
        for g in db.query(AgentGroundTruth).filter(AgentGroundTruth.id.in_(test_ids)).all():
            test_name_map[g.id] = g.name

    return JSONResponse({
        "items": [_run_to_dict(r, test_name_map.get(r.test_id, "")) for r in items],
        "total": len(items),
    })


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total_tests = db.query(AgentGroundTruth).count()
    active_tests = db.query(AgentGroundTruth).filter(AgentGroundTruth.is_active == True).count()
    total_runs = db.query(AgentGroundTruthRun).count()
    avg_score_rows = db.query(AgentGroundTruthRun.total_score).filter(
        AgentGroundTruthRun.total_score > 0
    ).all()
    avg = round(sum(s[0] for s in avg_score_rows) / len(avg_score_rows), 3) if avg_score_rows else 0
    by_category = {}
    for cat_row in db.query(AgentGroundTruth.category).distinct().all():
        c = cat_row[0]
        by_category[c] = db.query(AgentGroundTruth).filter(AgentGroundTruth.category == c).count()
    by_difficulty = {}
    for d_row in db.query(AgentGroundTruth.difficulty).distinct().all():
        d = d_row[0]
        by_difficulty[d] = db.query(AgentGroundTruth).filter(AgentGroundTruth.difficulty == d).count()
    return JSONResponse({
        "total_tests": total_tests,
        "active_tests": active_tests,
        "total_runs": total_runs,
        "avg_total_score": avg,
        "by_category": by_category,
        "by_difficulty": by_difficulty,
    })


@router.get("/providers")
def list_providers(db: Session = Depends(get_db)):
    """列出可用的 AI Provider（供前端执行用例时选择）"""
    items = db.query(AIProvider).order_by(AIProvider.id.asc()).all()
    return JSONResponse({
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "provider_type": p.provider_type,
                "default_model": p.default_model or "",
                "is_enabled": bool(p.is_enabled),
            }
            for p in items
        ]
    })


def _calc_tool_score(executed_tools: list, expected_tools: list) -> float:
    """工具评分：期望工具被真实执行且成功才算命中。

    executed_tools: [{"name": "x", "is_success": True}, ...]
    expected_tools: ["x", "y"]
    """
    if not expected_tools:
        return 1.0
    if not executed_tools:
        return 0.0
    successful_names = {t.get("name") for t in executed_tools if t.get("is_success")}
    called_names = {t.get("name") for t in executed_tools}
    hits = sum(1 for t in expected_tools if t in successful_names)
    partial = sum(1 for t in expected_tools if t in called_names and t not in successful_names)
    score = (hits + partial * 0.3) / len(expected_tools)
    return round(min(score, 1.0), 3)


def _calc_answer_similarity(actual: str, expected: str) -> float:
    """答案相似度评分：字符级 2-gram Jaccard + SequenceMatcher 综合判定（中文友好）。

    旧实现用空格分词，对中文句子几乎全为 0（中文无空格）。
    """
    if not expected:
        return 1.0
    if not actual:
        return 0.0
    a = actual.strip().lower()
    e = expected.strip().lower()
    if not e:
        return 1.0
    if a == e:
        return 1.0
    if e in a or a in e:
        return 0.9

    def char_ngrams(s: str, n: int = 2) -> set:
        s = s.replace(" ", "").replace("\n", "")
        if len(s) < n:
            return {s} if s else set()
        return {s[i:i + n] for i in range(len(s) - n + 1)}

    a_grams = char_ngrams(a, 2)
    e_grams = char_ngrams(e, 2)
    if not e_grams:
        return 1.0
    intersection = a_grams & e_grams
    jaccard = len(intersection) / len(e_grams)

    seq_ratio = SequenceMatcher(None, a, e).ratio()

    score = 0.5 * jaccard + 0.5 * seq_ratio
    return round(min(score, 1.0), 3)
