from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="nhentai-cli",
    version="1.0.0",
    author="Based on NClientV3",
    description="Python CLI for nhentai.net based on NClientV3 architecture",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.28.0",
        "Pillow>=9.0.0",
        "reportlab>=3.6.0",
        "beautifulsoup4>=4.12.0",
    ],
    entry_points={
        "console_scripts": [
            "nhentai=nhentai_cli.cli:main",
        ],
    },
)
