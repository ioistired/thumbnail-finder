from setuptools import setup, find_packages

setup(
	name='thumbnail_finder',
	version='0.2.0',
	url='https://github.com/bmintz/thumbnail-finder',

	author='reddit Inc',

	packages=find_packages(),

	install_requires=[
		'bs4',
		'flask',
		'requests',
		'pillow',
	],

	classifiers=[
		'Development Status :: 4 - Beta',
		'Programming Language :: Python :: 3 :: Only',
		'Operating System :: POSIX',
		'Intended Audience :: Developers',
		'Topic :: Internet :: WWW/HTTP',
	]
)