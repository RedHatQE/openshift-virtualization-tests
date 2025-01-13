#! /usr/bin/python
# -*- coding: utf-8 -*-

from setuptools import find_packages, setup

setup(
    name="cnv-utilities",
    version="1.0",
    packages=find_packages(include=["utilities"]),
    include_package_data=True,
    package_data={"": ["utilities/manifests/*"]},
    install_requires=[
        "kubernetes",
        "openshift",
        "xmltodict",
        "netaddr",
        "paramiko",
        "pytest",
        "jira",
        "openshift-python-wrapper",
    ],
    python_requires=">=3.6",
)
