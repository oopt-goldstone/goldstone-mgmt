import setuptools

with open("requirements.txt", "r") as f:
    install_requires = f.read().split()

setuptools.setup(
    name="goldstone_south_onlp",
    version="0.1.0",
    install_requires=install_requires,
    description="Goldstone Python ONLP south daemon",
    url="https://github.com/microsonic/goldstone-mgmt",
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gssouthd-onlp = goldstone.south.onlp.main:main",
        ],
    },
    packages=["goldstone.south.onlp"],
    zip_safe=False,
)
