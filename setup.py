from setuptools import setup
import os
import re


with open(os.path.join(os.path.abspath(os.path.dirname(
        __file__)), 'aiohttp_session', '__init__.py'), 'r', encoding='latin1') as fp:
    try:
        version = re.findall(r"^__version__ = '([^']+)'$", fp.read(), re.M)[0]
    except IndexError:
        raise RuntimeError('Unable to determine version.')


def read(f):
    return open(os.path.join(os.path.dirname(__file__), f)).read().strip()

install_requires = ['aiohttp>=3.0.1']
extras_require = {
    'aioredis': ['aioredis>=1.0.0'],
    'aiomcache': ['aiomcache>=0.5.2'],
    'pycrypto': ['cryptography'],
    'secure': ['cryptography'],
    'pynacl': ['pynacl'],
}


setup(name='aiohttp-session',
      version=version,
      description=("sessions for aiohttp.web"),
      long_description='\n\n'.join((read('README.rst'), read('CHANGES.txt'))),
      classifiers=[
          'License :: OSI Approved :: Apache Software License',
          'Intended Audience :: Developers',
          'Programming Language :: Python',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.5',
          'Programming Language :: Python :: 3.6',
          'Topic :: Internet :: WWW/HTTP',
          'Framework :: AsyncIO',
      ],
      author='Andrew Svetlov',
      author_email='andrew.svetlov@gmail.com',
      url='https://github.com/aio-libs/aiohttp_session/',
      license='Apache 2',
      packages=['aiohttp_session'],
      python_requires=">=3.5",
      install_requires=install_requires,
      include_package_data=True,
      extras_require=extras_require)
