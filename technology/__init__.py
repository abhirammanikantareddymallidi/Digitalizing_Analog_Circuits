"""
Technology node package.

Provides:
  - PTM SPICE model file parser
  - Technology database (singleton, auto-discovers .pm files)
  - Technology constraint engine

Usage:
    from technology.tech_database import TechDatabase
    db = TechDatabase.get_instance()
    node = db.get_node("16nm")
    constraints = node.get_constraint_ranges("NMOS")
"""

from technology.tech_database import TechDatabase
from technology.tech_constraints import TechConstraintEngine

__all__ = ["TechDatabase", "TechConstraintEngine"]
