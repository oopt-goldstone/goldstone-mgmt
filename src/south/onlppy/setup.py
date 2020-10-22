import setuptools

setuptools.setup(
        name='gsonlp',
        version='0.1.0',
#        install_requires=['sysrepo'],
        description='Goldstone Python ONLP south daemon',
        url='https://github.com/microsonic/goldstone-mgmt',
        python_requires='>=3.7',
        entry_points={
            'console_scripts': [
                'gssouthd-onlp = gsonlp.main:main',
            ],
        },
        packages=setuptools.find_packages(),
        zip_safe = False,
)
