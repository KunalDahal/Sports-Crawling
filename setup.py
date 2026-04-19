from setuptools import setup

setup(
    name="spcrawler",
    version="1.0.0",
    description="Sports piracy stream detection crawler",
    packages=[
        "spcrawler",
        "spcrawler.client",
        "spcrawler.instance",
        "spcrawler.utils",
    ],
    package_dir={"spcrawler": "src"},
    python_requires=">=3.11",
    install_requires=[
        "crawl4ai>=0.4.0",
        "ddgs>=6.0.0",
        "pymongo>=4.6.0",
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
    ],
)
