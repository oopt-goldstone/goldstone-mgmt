import setuptools

with open("requirements.txt", "r") as f:
    install_requires = f.read().split()

setuptools.setup(
    name="goldstone_south_sonic",
    version="0.1.0",
    install_requires=install_requires,
    description="Goldstone Python sonic south daemon",
    url="https://github.com/microsonic/goldstone-mgmt",
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gssouthd-sonic = goldstone.south.sonic.main:main",
        ],
    },
    packages=["goldstone.south.sonic"],
    zip_safe=False,
)
