import setuptools

with open("requirements.txt", "r") as f:
    install_requires = f.read().split()

setuptools.setup(
    name="gsgearbox",
    version="0.1.0",
    install_requires=install_requires,
    description="Goldstone Python Gearbox south daemon",
    url="https://github.com/microsonic/goldstone-mgmt",
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gssouthd-gearbox = gsgearbox.main:main",
        ],
    },
    packages=setuptools.find_packages(),
    zip_safe=False,
)
