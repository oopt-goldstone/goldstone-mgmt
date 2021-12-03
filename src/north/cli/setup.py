import setuptools

with open("requirements.txt") as f:
    install_requires = f.read().split()

setuptools.setup(
    name="goldstone_north_cli",
    version="0.1.0",
    install_requires=install_requires,
    description="Goldstone CLI",
    url="https://github.com/microsonic/goldstone-mgmt",
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gscli = goldstone.north.cli.main:main",
        ],
    },
    packages=["goldstone.north.cli"],
    zip_safe=False,
)
