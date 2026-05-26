from setuptools import setup, find_packages

setup(
    name="srchigh",
    version="2.0.0",
    description="eCourts India — High Court Judgments Scraper",
    python_requires=">=3.9",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "requests>=2.31.0",
        "Pillow>=10.0.0",
        "pytesseract>=0.3.10",
        "parsel>=1.10.0",
        "cssselect>=1.3.0",
    ],
    entry_points={
        "console_scripts": [
            "srchigh = srchigh.main:run_cli",
        ],
    },
)
