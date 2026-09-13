"""Documented inference integrations; absent vendor APIs fail explicitly."""
import os

class IntegrationUnavailable(RuntimeError):
    pass

def wandb_client():
    key = os.getenv('WANDB_API_KEY')
    project = os.getenv('CADFORGE_WEAVE_PROJECT')
    if not key or not project:
        raise IntegrationUnavailable('W&B Inference requires WANDB_API_KEY and CADFORGE_WEAVE_PROJECT=team/project')
    from openai import OpenAI
    return OpenAI(base_url='https://api.inference.wandb.ai/v1',api_key=key,project=project,timeout=60,max_retries=1)

def wandb_chat(prompt: str, model: str):
    """Use public development prompts only; caller opts into Weave initialization."""
    response = wandb_client().chat.completions.create(model=model,messages=[{'role':'user','content':prompt}],max_tokens=800)
    return {'text': response.choices[0].message.content, 'usage':response.usage.model_dump() if response.usage else None}

def typesafe_client():
    raise IntegrationUnavailable('TypeSafe.ai public site is a stealth-lab waitlist with no published API contract found on 2026-09-12. Supply official API documentation/access before implementing a vendor adapter. Pydantic AI is a different product.')
