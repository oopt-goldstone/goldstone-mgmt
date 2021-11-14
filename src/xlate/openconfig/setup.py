import setuptools

with open("requirements.txt", "r") as f:
    install_requires = f.read().split()

setuptools.setup(
    name="goldstone_xlate_openconfig",
    version="0.1.0",
    install_requires=install_requires,
    description="Goldstone OpenConfig translator",
    url="https://github.com/oopt-goldstone/goldstone-mgmt",
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gsxlated-openconfig = goldstone.xlate.openconfig.main:main",
        ],
    },
    packages=["goldstone.xlate.openconfig"],
    zip_safe=False,
)
