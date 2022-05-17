import setuptools

with open("requirements.txt", "r") as f:
    install_requires = f.read().split()

setuptools.setup(
    name="goldstone_system_telemetry",
    version="0.1.0",
    install_requires=install_requires,
    description="Streaming telemetry server",
    url="https://github.com/oopt-goldstone/goldstone-mgmt",
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gssystemd-telemetry = goldstone.system.telemetry.main:main",
        ],
    },
    packages=["goldstone.system.telemetry"],
    zip_safe=False,
)
