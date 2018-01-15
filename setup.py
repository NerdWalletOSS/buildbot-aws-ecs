from setuptools import setup, find_packages

install_requires = [
    'six>=1.10.0',
    'buildbot>=0.9.15',
]

with open('VERSION') as version_fd:
    version = version_fd.read().strip()

with open('README.rst') as readme_fd:
    long_description = readme_fd.read()

setup(
    name='buildbot-aws-ecs',
    version=version,
    packages=find_packages('src'),
    package_dir={'': 'src'},
    install_requires=install_requires,
    include_package_data=True,
    author='Evan Borgstrom',
    author_email='eborgstrom@nerdwallet.com',
    license='GPLv2',
    description='Buildbot latent worker for AWS ECS',
    long_description=long_description,
    url='https://github.com/NerdWalletOSS/buildbot-aws-ecs',
    entry_points={
        'buildbot.worker': [
            'ECSWorker = buildbot_ecs_worker:ECSWorker'
        ]
    }
)
