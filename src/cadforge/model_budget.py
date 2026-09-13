"""Charge each provider request, including retries, before model execution."""
from .execution_budget import _current
from contextlib import asynccontextmanager


def budgeted_model(model):
    budget=_current.get()
    if budget is None:return model
    from pydantic_ai.models.wrapper import WrapperModel
    class CountedModel(WrapperModel):
        async def request(self,messages,model_settings,model_request_parameters):
            budget.charge('model_requests')
            return await self.wrapped.request(messages,model_settings,model_request_parameters)
        @asynccontextmanager
        async def request_stream(self,messages,model_settings,model_request_parameters,run_context=None):
            budget.charge('model_requests')
            async with self.wrapped.request_stream(messages,model_settings,model_request_parameters,run_context) as response:
                yield response
    return CountedModel(model)
