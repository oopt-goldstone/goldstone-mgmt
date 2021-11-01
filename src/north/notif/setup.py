import setuptools

with open("requirements.txt", "r") as f:
    install_requires = f.read().split()

setuptools.setup(
    name="gsnotif",
    version="0.1.0",
    install_requires=install_requires,
    description="Goldstone Python sonic notif daemon",
    url="https://github.com/microsonic/goldstone-mgmt",
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gsnorthd-notif = gsnotif.main:main",
        ],
    },
    packages=setuptools.find_packages(),
    zip_safe=False,
)
