"""Typed clients for the upstreams. These fetch and shape; they never compute statistics.

The split matters: a client that quietly averages something is a client whose output you
cannot check against the API's own documentation. Statistics live in ``analysis/``.
"""
