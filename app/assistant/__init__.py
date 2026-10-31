"""FreeData.td assistant: answers questions about Chad's market prices and weather.

Design: ONE base engine (engine.py) and several "lenses" (markets.py, weather.py). A lens knows
the vocabulary of one domain (products, places, units) and how to read its data. The engine
routes a question to a lens and never invents a figure: every number in an answer comes from a
row of the database and is given with its date and source. No language model is needed to
answer, so answers are free, instant and testable; a model can later be added only to
understand unusual phrasing.
"""
from app.assistant.engine import Answer, Assistant

__all__ = ["Answer", "Assistant"]
