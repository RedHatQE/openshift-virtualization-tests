"""Conftest for pytest marker analyzer tests.

This file prevents pytest from discovering the project's top-level
conftest.py which requires an OpenShift cluster connection.
"""
