from setuptools import setup

setup(name='pf9watcher',
      version='0.0.2',
      description='Host monitoring and evacuation',
      url='http://github.com/platform9/pf9-watcher',
      author='Jeremy Brooks',
      author_email='jeremy@platform9.com',
      license='MIT',
      packages=['pf9watcher'],
      install_requires=[
          'pycrypto',
          'python-keystoneclient',
          'python-novaclient',
      ],
      zip_safe=False)
