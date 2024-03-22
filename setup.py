#! /usr/bin/python
# -*- coding: utf-8 -*-

from setuptools import find_packages, setup


setup(
    name="openshift-virtualization-tests",
    version="1.0",
    packages=find_packages(include=["operator_utilities"]),
    include_package_data=True,
    install_requires=[
        "kubernetes",
        "openshift",
        "xmltodict",
        "python-bugzilla",
        "netaddr",
        "paramiko",
        "pytest",
        "jira",
        "openshift-python-wrapper",
    ],
    python_requires=">=3.8",
)
