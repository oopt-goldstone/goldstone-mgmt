import setuptools

with open("requirements.txt", "r") as f:
    install_requires = f.read().split()

setuptools.setup(
    name="gsopenconfig",
    version="0.1.0",
    install_requires=install_requires,
    description="Goldstone OpenConfig translator",
    url="https://github.com/microsonic/goldstone-mgmt",
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gsxlated-openconfig = gsopenconfig.main:main",
        ],
    },
    packages=setuptools.find_packages(),
    zip_safe=False,
)
