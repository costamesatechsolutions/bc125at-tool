from setuptools import setup, find_packages

setup(
    name="bc125at",
    version="0.1.0",
    description="BC125AT Scanner Programming Tool for macOS (Apple Silicon native)",
    author="James Lovberg",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "pyusb>=1.2.0",
    ],
    entry_points={
        "console_scripts": [
            "bc125at=bc125at.cli:main",
        ],
    },
    classifiers=[
        "Operating System :: MacOS",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Topic :: Communications :: Ham Radio",
    ],
)
