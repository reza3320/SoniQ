"""Compatibility shim — older launchers import ``main`` from here.

The original repo layout exposed the entry point as ``soniq.main``
(``run.py`` does ``from soniq.main import main``). Current code keeps
the real entry point in ``soniq.__main__``; this module bridges the two
so both old and new launchers work after an in-place update.
"""

from soniq.__main__ import main

__all__ = ["main"]
