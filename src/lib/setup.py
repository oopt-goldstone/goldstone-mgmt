import setuptools

with open("requirements.txt") as f:
    install_requires = f.read().split()

setuptools.setup(
    name="goldstone_lib",
    version="0.1.0",
    install_requires=install_requires,
    description="Goldstone Python Library",
    url="https://github.com/microsonic/goldstone-mgmt",
    python_requires=">=3.7",
    packages=["goldstone.lib", "goldstone.lib.connector"],
    zip_safe=False,
)
