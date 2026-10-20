"""Use-cases. Each public function runs in its own transaction and returns a read model.

Lock order, wherever more than one row is locked: member, then item, then loan.
Keeping one order means two concurrent transactions can never deadlock on PostgreSQL.
"""
