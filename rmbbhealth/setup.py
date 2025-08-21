from setuptools import setup, find_packages

setup(
    name="rmbbhealth",
    version="1.0.0",
    description="RMBB Health Integration Package",
    packages=find_packages(),
    install_requires=[
        "flask",
        "requests", 
        "python-dotenv"
    ],
    python_requires=">=3.8",
)