import setuptools

setuptools.setup(
        name='gscli',
        version='0.1.0',
        install_requires=['prompt_toolkit', 'tabulate', 'natsort'],
        description='Goldstone CLI',
        url='https://github.com/microsonic/goldstone-mgmt',
        python_requires='>=3.7',
        entry_points={
            'console_scripts': [
                'gscli = gscli.main:main',
            ],
        },
        packages=setuptools.find_packages(),
        zip_safe = False,
)
