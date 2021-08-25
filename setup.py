#!/usr/bin/env python

from pbr.packaging import parse_requirements
from setuptools import setup, find_packages

setup(
    name='bumblebee',
    version='0.1',
    description=('Virtual Desktop service'),
    author='ARDC',
    author_email='coreservices@ardc.edu.au',
    url='https://github.com/NeCTAR-RC/bumblebee',
    license='Apache License 2.0',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=parse_requirements(),
    classifiers=(
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ),
)
