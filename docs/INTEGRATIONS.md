# Integrations and execution status

This system runs its editable geometry backend locally. Remote inference and tracing are optional. No hidden benchmark cases or detailed hidden results are displayed in the notebook or sent to observability services.

| Integration | Implemented behavior | Verification and remaining access |
| --- | --- | --- |
| marimo | Reactive natural-language form, four dimension sliders, SVG preview, measured geometry checks, and JSON/STEP/STL/Python downloads | marimo 0.24.2 strict check and HTML export passed; programmatic submitted-form smoke test generated all five export formats without error |
| CadQuery | Parametric Python and JSON specifications, named STEP assembly, STL mesh and SVG exports | Local geometry backend; exported Python regenerates designs with CADForge installed |
| Pydantic AI | Typed optional planning and 108 bounded specialist review jobs with model usage records | Separate library from TypeSafe.ai; provider execution results live in run artifacts, not inferred from adapter availability |
| W&B Weave | `enable_weave()` initializes opt-in development tracing; `trace_development()` decorates development operations | Requires `WANDB_API_KEY` and `CADFORGE_WEAVE_PROJECT`; hosted tracing has not been verified without configuration |
| W&B Serverless Inference | `wandb_client()` and `wandb_chat(prompt, model)` use the OpenAI-compatible endpoint | Implemented adapter, unconfigured/unverified live; requires API key, team/project, and an available model |
| TypeSafe.ai | Explicit unavailable-adapter error with reason | Blocked: no public API contract/access found on the official site as checked 2026-09-12; Pydantic AI does not fulfill this vendor integration |

## Design studio

From the repository root:

```sh
PYTHONPATH=src .venv/bin/marimo edit notebooks/design_studio.py
```

For app mode, replace `edit` with `run`. The notebook uses the bounded offline request parser, so no API key or remote request is needed. Changing text or sliders does not invoke CAD until **Build design** is selected. Sliders explicitly override wall, clearance, lens width and lens height; other dimensions come from the request/default specification. Each submitted build writes a new directory under `artifacts/studio/`, preserving prior artifacts. The SVG is a static projection; edit dimensions and resubmit to inspect a new shape. STEP and Python/JSON preserve editable design intent; STL is a mesh export.

The UI reports the validator's actual limitations alongside its checks. A geometry pass does not certify assembled electronics, optical alignment, thermal behavior, structural performance, or wearability. The studio does not load the hidden benchmark. Form batching follows the [marimo form API](https://docs.marimo.io/api/inputs/form/); file downloads use the [download API](https://docs.marimo.io/api/outputs/download/).

## W&B Weave and serverless inference

Configure `WANDB_API_KEY` in the process environment and set `CADFORGE_WEAVE_PROJECT` to the authorized `team/project`. Do not store either credential in the repository. Initialization is explicit:

```python
from cadforge.telemetry import enable_weave, trace_development

status = enable_weave()

@trace_development
def review_public_design(request):
    return {"request": request, "review": "development-only"}
```

The inference adapter uses `https://api.inference.wandb.ai/v1`, with the project passed to the client. Select a model from the currently available account catalog:

```python
from cadforge.providers import wandb_chat

result = wandb_chat("Review this public development CAD brief...", model="YOUR_AVAILABLE_MODEL")
```

Inference and tracing are separate capabilities. Merely constructing the inference client does not establish a successful hosted Weave trace. Both require an authorized configured account before live verification. Consult [W&B Serverless Inference](https://docs.wandb.ai/inference/) and [Weave tracing](https://docs.wandb.ai/weave/guides/tracking/tracing/).

## TypeSafe.ai

The [official TypeSafe.ai site](https://typesafe.ai/) describes a stealth AI lab and offers a waitlist. No public integration contract was found in that inspection. `typesafe_client()` therefore raises `IntegrationUnavailable`; it does not fabricate endpoints or silently substitute another vendor. A real adapter requires official documentation, credentials, a supported model/API contract, and a live integration test. The optional [Pydantic AI typed agent framework](https://pydantic.dev/docs/ai/core-concepts/agent/) remains an independently named implementation dependency.
