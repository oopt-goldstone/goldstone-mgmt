import setuptools

setuptools.setup(
    name="gssystem",
    version="0.1.0",
    install_requires=["pyroute2", "tabulate"],
    description="Goldstone Python system south daemon",
    url="https://github.com/microsonic/goldstone-mgmt",
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gssouthd-system = gssystem.main:main",
        ],
    },
    packages=setuptools.find_packages(),
    zip_safe=False,
)
