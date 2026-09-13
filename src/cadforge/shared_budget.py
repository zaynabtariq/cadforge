"""Durable cross-process counters for trusted evaluation workers.

A worker with arbitrary filesystem write access can tamper with this ledger;
use an external resource broker for adversarial isolation.
"""
from pathlib import Path
import os
import sqlite3
from contextlib import contextmanager
from .execution_budget import ExecutionBudget,BudgetExceeded


class SharedExecutionBudget(ExecutionBudget):
    def __init__(self,path,limits=None):
        self.path=Path(path).resolve()
        if limits is not None:
            ExecutionBudget(limits)  # Validate before creating anything.
            self.path.parent.mkdir(parents=True,exist_ok=True)
            descriptor=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            os.close(descriptor)
            try:
                with self._connection() as db:
                    db.execute('CREATE TABLE counters (name TEXT PRIMARY KEY, allowance INTEGER NOT NULL CHECK(allowance>=0), used INTEGER NOT NULL CHECK(used>=0 AND used<=allowance), denied INTEGER NOT NULL CHECK(denied>=0))')
                    db.executemany('INSERT INTO counters VALUES (?,?,0,0)',list(limits.items()))
                    db.execute('PRAGMA user_version=1')
            except Exception:
                self.path.unlink(missing_ok=True);raise
        # mode=rw ensures attaching a missing ledger cannot create fresh limits.
        with self._connection() as db:
            if db.execute('PRAGMA user_version').fetchone()[0]!=1:raise ValueError('Unsupported budget ledger')
            rows=db.execute('SELECT name,allowance,used,denied FROM counters').fetchall()
        if not rows:raise ValueError('Empty budget ledger')
        self.limits={r[0]:r[1] for r in rows}

    @contextmanager
    def _connection(self):
        db=sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=10)
        try:
            with db:yield db
        finally:db.close()

    def charge(self,kind,amount=1):
        if type(amount) is not int or amount<=0:raise ValueError('Charge must be a positive integer')
        denied=False
        with self._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT allowance,used FROM counters WHERE name=?',(kind,)).fetchone()
            if row is None:raise ValueError('Unconfigured budget category: '+kind)
            allowance,used=row
            if amount>allowance-used:
                db.execute('UPDATE counters SET denied=denied+1 WHERE name=?',(kind,));denied=True
            else:db.execute('UPDATE counters SET used=used+? WHERE name=?',(amount,kind))
        if denied:raise BudgetExceeded(kind)

    def snapshot(self):
        with self._connection() as db:rows=db.execute('SELECT name,allowance,used,denied FROM counters').fetchall()
        return {key:{row[0]:row[index] for row in rows} for index,key in enumerate(('limits','used','denied'),1)}
