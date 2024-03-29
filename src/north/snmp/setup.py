import setuptools

with open("requirements.txt", "r") as f:
    install_requires = f.read().split()

setuptools.setup(
    name="gssnmp",
    version="0.1.0",
    install_requires=install_requires,
    description="Goldstone SNMP AgentX",
    url="https://github.com/microsonic/goldstone-mgmt",
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gsnorthd-snmp = gs_ax_impl.main:main",
        ],
    },
    package_dir={"gs_ax_impl": "src/gs_ax_impl", "ax_interface": "src/ax_interface"},
    packages=setuptools.find_packages("src"),
    zip_safe=False,
)
