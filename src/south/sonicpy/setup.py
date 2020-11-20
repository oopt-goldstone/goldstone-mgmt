import setuptools

setuptools.setup(
        name='gssonic',
        version='0.1.0',
        install_requires=['sysrepo','libyang', 'kubernetes_asyncio'],
        description='Goldstone Python sonic south daemon',
        url='https://github.com/microsonic/goldstone-mgmt',
        python_requires='>=3.7',
        entry_points={
            'console_scripts': [
                'gssouthd-sonic = gssonic.main:main',
            ],
        },
        packages=setuptools.find_packages(),
        zip_safe = False,
)
