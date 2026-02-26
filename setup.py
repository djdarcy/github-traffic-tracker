from setuptools import setup, find_packages

setup(
    name="github-traffic-tracker",
    version="0.1.0",
    description="Zero-server GitHub traffic analytics — daily collection via Actions, gist-backed storage, client-side dashboard",
    author="Dustin",
    author_email="6962246+djdarcy@users.noreply.github.com",
    url="https://github.com/djdarcy/github-traffic-tracker",
    packages=find_packages(),
    install_requires=[],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
)
