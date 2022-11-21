import setuptools

with open("requirements.txt", "r") as f:
    install_requires = f.read().split()

setuptools.setup(
    name="goldstone_south_ocnos",
    version="0.1.0",
    install_requires=install_requires,
    description="Goldstone Python OcNOS south daemon",
    url="https://github.com/oopt-goldstone/goldstone-mgmt",
    python_requires=">=3.7",
    entry_points={
        "console_scripts": ["gssouthd-ocnos = goldstone.south.ocnos.main:main"]
    },
    packages=["goldstone.south.ocnos", "data"],
    include_package_data=True,
    package_data={"data": ["feature-list.yang"]},
    zip_safe=False,
)
