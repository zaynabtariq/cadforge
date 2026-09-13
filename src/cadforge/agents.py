"""Specialist planning workers; LLM reviews are advisory, never validators."""
from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class SpecialistJob:
    id: str
    discipline: str
    lens: str
    request: str


DISCIPLINES = ("frame_geometry", "camera_packaging", "board_packaging", "fasteners",
               "assembly", "cable_routing", "thermal", "ergonomics", "manufacturing",
               "tolerances", "structural", "editability")
LENSES = ("requirements", "failure_modes", "parameterization", "clearances", "interfaces",
          "test_design", "repair_strategy", "unfamiliar_variants", "evidence_limits")


def build_specialist_jobs(request: str) -> list[SpecialistJob]:
    """108 unique discipline/lens jobs, not a claim of 108 concurrent processes."""
    return [SpecialistJob(f"{discipline}.{lens}", discipline, lens, request)
            for discipline in DISCIPLINES for lens in LENSES]


def deterministic_worker(job: SpecialistJob) -> dict:
    """Offline smoke-test worker. Explicitly not an autonomous LLM agent."""
    return {"execution_kind": "deterministic_checklist", "model_tokens": 0,
            "recommendation": f"Review {job.discipline} for {job.lens}; require measured evidence.",
            "relevant_parameters": [], "risks": ["Checklist alone does not validate geometry."]}


def make_llm_worker(model: str = "openai:gpt-4.1-mini-2025-04-14"):
    """Create a synchronous typed Pydantic AI worker for run_specialists.

    Model can be overridden with CADFORGE_MODEL. Each invocation has at most
    two model requests and 400 output tokens per request. Successful responses
    include provider-reported input/output tokens and request counts. Failed
    runs preserve consumed usage on the exception for the scheduler audit.
    """
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent
    from pydantic_ai.usage import RunUsage, UsageLimits

    class Review(BaseModel):
        recommendation: str = Field(max_length=1200)
        relevant_parameters: list[str] = Field(max_length=12)
        risks: list[str] = Field(max_length=8)

    selected_model = os.environ.get("CADFORGE_MODEL", model)

    def worker(job: SpecialistJob) -> dict:
        # One agent per job: no shared conversation state or hidden-case access.
        from .model_budget import budgeted_model
        agent = Agent(budgeted_model(selected_model), output_type=Review, retries=1,
                      instructions=("You are a CAD engineering specialist. Give a concise, actionable "
                                    "parameterized recommendation for your assigned discipline and review lens. "
                                    "Identify assumptions and unsupported engineering claims. No assertions "
                                    "of successful testing; you have no CAD execution tools."),
                      model_settings={"max_tokens": 400, "temperature": 0})
        usage = RunUsage()
        try:
            result = agent.run_sync(f"Discipline: {job.discipline}\nLens: {job.lens}\n"
                                    f"Design request: {job.request}", usage=usage,
                                    usage_limits=UsageLimits(request_limit=2))
        except Exception as error:
            error.cadforge_usage = {"input_tokens": usage.input_tokens,
                                   "output_tokens": usage.output_tokens,
                                   "model_tokens": usage.total_tokens,
                                   "model_requests": usage.requests}
            raise
        return {**result.output.model_dump(), "execution_kind": "pydantic_ai_llm",
                "model": selected_model, "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens, "model_tokens": usage.total_tokens,
                "model_requests": usage.requests}

    return worker


def main():
    """Run development-only specialist reviews: python -m cadforge.agents."""
    import argparse
    import json
    from pathlib import Path
    from .scheduler import run_specialists

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", default="Design editable glasses housing a camera and Raspberry Pi Zero 2 W.")
    parser.add_argument("--output", default="artifacts/specialist_reviews.json")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--llm", action="store_true")
    args = parser.parse_args()
    worker = make_llm_worker() if args.llm else deterministic_worker
    records = run_specialists(build_specialist_jobs(args.request), worker, args.workers)
    usage = [r.get("output", r.get("usage", {})) for r in records]
    report = {"scope": "development/demo advisory reviews, shared by all benchmark arms",
              "excluded_from_case_inference_budget": True,
              "execution_kind": "pydantic_ai_llm" if args.llm else "deterministic_checklist",
              "jobs": len(records), "completed": sum(r["status"] == "completed" for r in records),
              "input_tokens": sum(u.get("input_tokens", 0) for u in usage),
              "output_tokens": sum(u.get("output_tokens", 0) for u in usage),
              "model_requests": sum(u.get("model_requests", 0) for u in usage),
              "records": records}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "records"}))


if __name__ == "__main__":
    main()
