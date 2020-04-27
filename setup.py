import setuptools
import os
import io


def read(*parts):
    filename = os.path.join(os.path.abspath(os.path.dirname(__file__)), *parts)

    with io.open(filename, encoding='utf-8', mode='rt') as fp:
        return fp.read()


setuptools.setup(
    name="async-cache",
    version="0.0.5",
    author="Rajat Singh",
    author_email="iamsinghrajat@gmail.com",
    description=read("README.rst"),
    long_description_content_type="text/markdown",
    url="https://github.com/iamsinghrajat/async-cache",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.3',
    keywords=['asyncio', 'lru', 'cache', 'async', 'async-cache', 'lru-cache'],
)
