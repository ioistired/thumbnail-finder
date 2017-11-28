from setuptools import setup, find_packages

setup(
	name='thumbnail_finder',
	version='0.4.0',
	url='https://github.com/bmintz/thumbnail-finder',

	author='reddit Inc',

	packages=find_packages(),

	install_requires=[
		'async_timeout',
		'bs4',
		'flask',
		'lxml',
		'requests',
		'pillow',
	],

	classifiers=[
		'Development Status :: 4 - Beta',
		'Programming Language :: Python :: 3 :: Only',
		'Operating System :: POSIX',
		'Intended Audience :: Developers',
		'Topic :: Internet :: WWW/HTTP',
	],
)