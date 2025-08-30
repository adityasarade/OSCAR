"""
OSCAR Setup Script - Simplified package installation
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

# Read requirements
requirements_path = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_path.exists():
    with open(requirements_path, 'r', encoding='utf-8') as f:
        requirements = [
            line.strip() for line in f 
            if line.strip() and not line.startswith("#")
        ]

setup(
    name="oscar-agent",
    version="0.2.0",  # Updated version after cleanup
    description="OSCAR - Operating System's Complete Agentic Rex",
    long_description=long_description,
    long_description_content_type="text/markdown",
    
    # Author info
    author="OSCAR Team",
    author_email="oscar@example.com",
    url="https://github.com/oscar-team/oscar",
    
    # Package configuration
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    package_data={
        "oscar.config": ["*.yaml", "*.yml"],
    },
    
    # Dependencies
    install_requires=requirements,
    python_requires=">=3.8",
    
    # CLI entry point
    entry_points={
        "console_scripts": [
            "oscar=oscar.cli.main:main",
        ],
    },
    
    # Optional dependencies
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "black>=23.0.0",
            "isort>=5.12.0",
        ],
        "browser": [
            "playwright>=1.40.0",
        ],
    },
    
    # Classification
    classifiers=[
        "Development Status :: 4 - Beta",  # Updated from Alpha
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Topic :: System :: Systems Administration",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Environment :: Console",
    ],
    
    keywords="ai agent automation llm voice-assistant system-administration agentic",
    
    # Project URLs
    project_urls={
        "Bug Reports": "https://github.com/adityasarade/OSCAR",
        "Source": "https://github.com/adityasarade/OSCAR",
        "Documentation": "https://github.com/adityasarade/OSCAR",
    },
)