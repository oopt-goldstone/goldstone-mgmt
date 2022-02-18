import setuptools

with open("requirements.txt", "r") as f:
    install_requires = f.read().split()

setuptools.setup(
    name="goldstone_north_gnmi",
    version="0.1.0",
    install_requires=install_requires,
    description="Goldstone gNMI server",
    url="https://github.com/oopt-goldstone/goldstone-mgmt",
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gsnorthd-gnmi = goldstone.north.gnmi.main:main",
        ],
    },
    packages=[
        "goldstone.north.gnmi",
        "goldstone.north.gnmi.repo",
        "goldstone.north.gnmi.proto",
    ],
    zip_safe=False,
)
