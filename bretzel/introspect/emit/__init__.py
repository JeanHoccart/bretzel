"""Projections of :mod:`bretzel.introspect.model` — and nothing more.

An emitter is **dumb**: it formats already-built dataclasses, it computes
nothing. That is what guarantees that the text and the JSON cannot
diverge — they read the same data.
"""
