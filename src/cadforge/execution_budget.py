"""Pre-execution counters shared by nested work in one evaluation context."""
from contextlib import contextmanager
from contextvars import ContextVar
import threading

_current=ContextVar('cadforge_execution_budget',default=None)


class BudgetExceeded(ValueError):
    def __init__(self,kind,trials=None):
        super().__init__(f'Evaluation budget exhausted: {kind}')
        self.kind=kind;self.trials=list(trials or [])


class ExecutionBudget:
    def __init__(self,limits):
        if not limits or any(not isinstance(k,str) or type(v) is not int or v<0 for k,v in limits.items()):
            raise ValueError('Budget limits must be named nonnegative integers')
        self.limits=dict(limits);self.used={k:0 for k in limits};self.denied={k:0 for k in limits}
        self._lock=threading.Lock()

    def charge(self,kind,amount=1):
        if type(amount) is not int or amount<=0:raise ValueError('Charge must be a positive integer')
        with self._lock:
            if kind not in self.limits:raise ValueError('Unconfigured budget category: '+kind)
            if self.used[kind]+amount>self.limits[kind]:
                self.denied[kind]+=1
                raise BudgetExceeded(kind)
            self.used[kind]+=amount

    def snapshot(self):
        with self._lock:return {'limits':dict(self.limits),'used':dict(self.used),'denied':dict(self.denied)}

    @contextmanager
    def activate(self):
        if _current.get() is not None:raise ValueError('Nested work must inherit its existing budget')
        token=_current.set(self)
        try:yield self
        finally:_current.reset(token)


def charge(kind,amount=1):
    budget=_current.get()
    if budget is not None:budget.charge(kind,amount)
