from setuptools import setup, find_packages

setup(
    name="bc125at",
    version="0.1.0",
    description="BC125AT Scanner Programming Tool for macOS (tested on Apple Silicon)",
    author="Costa Mesa Tech Solutions",
    author_email="support@costamesatechsolutions.com",
    url="https://github.com/costamesatechsolutions/bc125at-tool",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "pyusb>=1.2.0",
    ],
    extras_require={
        "gui": ["flask>=2.0"],
    },
    entry_points={
        "console_scripts": [
            "bc125at=bc125at.cli:main",
        ],
    },
    license="AGPL-3.0",
    classifiers=[
        "Operating System :: MacOS",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Topic :: Communications :: Ham Radio",
    ],
)
