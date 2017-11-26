# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.	The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
###############################################################################

from collections import OrderedDict
import re
import signal
import sys
import urllib.parse


def url_escape(string):
	# convert into a list of octets
	string = string.encode("utf8")
	return urllib.parse.quote_plus(string)


def coerce_url_to_protocol(url, protocol='http'):
	"""Given an absolute (but potentially protocol-relative) url, coerce it to
	a protocol."""
	parsed_url = UrlParser(url)
	parsed_url.scheme = protocol
	return parsed_url.unparse()


r_domain_prefix = re.compile('^www\d*\.')


def strip_www(domain):
	stripped = domain
	if domain.count('.') > 1:
		prefix = r_domain_prefix.findall(domain)
		if domain.startswith("www") and prefix:
			stripped = '.'.join(domain.split('.')[1:])
	return stripped


def query_string(dict):
	pairs = []
	for k,v in dict.items():
		if v is not None:
			try:
				k = url_escape(_force_unicode(k))
				v = url_escape(_force_unicode(v))
				pairs.append(k + '=' + v)
			except UnicodeDecodeError:
				continue
	if pairs:
		return '?' + '&'.join(pairs)
	else:
		return ''


# Characters that might cause parsing differences in different implementations
# Spaces only seem to cause parsing differences when occurring directly before
# the scheme
URL_PROBLEMATIC_RE = re.compile(
	r'(\A\x20|[\x00-\x19\xA0\u1680\u180E\u2000-\u2029\u205f\u3000\\])',
	re.UNICODE
)


def paranoid_urlparser_method(check):
	"""
	Decorator for checks on `UrlParser` instances that need to be paranoid
	"""
	def check_wrapper(parser, *args, **kwargs):
		return UrlParser.perform_paranoid_check(parser, check, *args, **kwargs)

	return check_wrapper


class UrlParser(object):
	"""
	Wrapper for urlparse and urlunparse for making changes to urls.

	All attributes present on the tuple-like object returned by
	urlparse are present on this class, and are setable, with the
	exception of netloc, which is instead treated via a getter method
	as a concatenation of hostname and port.

	Unlike urlparse, this class allows the query parameters to be
	converted to a dictionary via the query_dict method (and
	correspondingly updated via update_query).	The extension of the
	path can also be set and queried.

	The class also contains reddit-specific functions for setting,
	checking, and getting a path's subreddit.
	"""

	__slots__ = ['scheme', 'path', 'params', 'query',
	             'fragment', 'username', 'password', 'hostname', 'port',
	             '_orig_url', '_orig_netloc', '_query_dict']

	valid_schemes = ('http', 'https', 'ftp', 'mailto')

	def __init__(self, url):
		u = urllib.parse.urlparse(url)
		for s in self.__slots__:
			if hasattr(u, s):
				setattr(self, s, getattr(u, s))
		self._orig_url	  = url
		self._orig_netloc = getattr(u, 'netloc', '')
		self._query_dict  = None

	def __eq__(self, other):
		"""A loose equality method for UrlParsers.

		In particular, this returns true for UrlParsers whose resultant urls
		have the same query parameters, but in a different order.  These are
		treated the same most of the time, but if you need strict equality,
		compare the string results of unparse().
		"""
		if not isinstance(other, UrlParser):
			return False

		(s_scheme, s_netloc, s_path, s_params, s_query, s_fragment) = self._unparse()
		(o_scheme, o_netloc, o_path, o_params, o_query, o_fragment) = other._unparse()
		# Check all the parsed components for equality, except the query, which
		# is easier to check in its pure-dictionary form.
		if (s_scheme != o_scheme or
				s_netloc != o_netloc or
				s_path != o_path or
				s_params != o_params or
				s_fragment != o_fragment):
			return False
		# Coerce query dicts from OrderedDicts to standard dicts to avoid an
		# order-sensitive comparison.
		if dict(self.query_dict) != dict(other.query_dict):
			return False

		return True

	def update_query(self, **updates):
		"""Add or change query parameters."""
		# Since in HTTP everything's a string, coercing values to strings now
		# makes equality testing easier.  Python will throw an error if you try
		# to pass in a non-string key, so that's already taken care of for us.
		updates = {k: _force_unicode(v) for k, v in updates.items()}
		self.query_dict.update(updates)

	@property
	def query_dict(self):
		"""A dictionary of the current query parameters.

		Keys and values pulled from the original url are un-url-escaped.

		Modifying this function's return value will result in changes to the
		unparse()-d url, but it's recommended instead to make any changes via
		`update_query()`.
		"""
		if self._query_dict is None:
			def _split(param):
				p = param.split('=')
				return (unquote_plus(p[0]),
						unquote_plus('='.join(p[1:])))
			self._query_dict = OrderedDict(
								 _split(p) for p in self.query.split('&') if p)
		return self._query_dict

	def path_extension(self):
		"""Fetches the current extension of the path.

		If the url does not end in a file or the file has no extension, returns
		an empty string.
		"""
		filename = self.path.split('/')[-1]
		filename_parts = filename.split('.')
		if len(filename_parts) == 1:
			return ''

		return filename_parts[-1]

	def has_image_extension(self):
		"""Guess if the url leads to an image."""
		extension = self.path_extension().lower()
		return extension in {'gif', 'jpeg', 'jpg', 'png', 'tiff'}

	def has_static_image_extension(self):
		"""Guess if the url leads to a non-animated image."""
		extension = self.path_extension().lower()
		return extension in {'jpeg', 'jpg', 'png', 'tiff'}

	def set_extension(self, extension):
		"""
		Changes the extension of the path to the provided value (the
		"." should not be included in the extension as a "." is
		provided)
		"""
		pieces = self.path.split('/')
		dirs = pieces[:-1]
		base = pieces[-1].split('.')
		base = '.'.join(base[:-1] if len(base) > 1 else base)
		if extension:
			base += '.' + extension
		dirs.append(base)
		self.path =	 '/'.join(dirs)
		return self

	def unparse(self):
		"""
		Converts the url back to a string, applying all updates made
		to the fields thereof.

		Note: if a host name has been added and none was present
		before, will enforce scheme -> "http" unless otherwise
		specified.	Double-slashes are removed from the resultant
		path, and the query string is reconstructed only if the
		query_dict has been modified/updated.
		"""
		return urllib.parse.urlunparse(self._unparse())

	def _unparse(self):
		q = query_string(self.query_dict).lstrip('?')

		# make sure the port is not doubly specified
		if getattr(self, 'port', None) and ":" in self.hostname:
			self.hostname = self.hostname.split(':')[0]

		# if there is a netloc, there had better be a scheme
		if self.netloc and not self.scheme:
			self.scheme = "http"

		return (
			self.scheme, self.netloc,
			self.path.replace('//', '/'),
			self.params, q, self.fragment
		)

	def perform_paranoid_check(self, check, *args, **kwargs):
		"""
		Perform a check on a URL that needs to account for bugs in `unparse()`

		If you need to account for quirks in browser URL parsers, you should
		use this along with `is_web_safe_url()`. Trying to parse URLs like
		a browser would just makes things really hairy.
		"""
		variants_to_check = (
			self,
			UrlParser(self.unparse())
		)
		# If the check doesn't pass on *every* variant, it's a fail.
		return all(
			check(variant, *args, **kwargs) for variant in variants_to_check
		)

	@paranoid_urlparser_method
	def is_web_safe_url(self):
		"""Determine if this URL could cause issues with different parsers"""

		# There's no valid reason for this, and just serves to confuse UAs.
		# and urllib2.
		if self._orig_url.startswith("///"):
			return False

		# Double-checking the above
		if not self.hostname and self.path.startswith('//'):
			return False

		# A host-relative link with a scheme like `https:/baz` or `https:?quux`
		if self.scheme and not self.hostname:
			return False

		# Credentials in the netloc? Not on reddit!
		if "@" in self._orig_netloc:
			return False

		# `javascript://www.reddit.com/%0D%Aalert(1)` is not safe, obviously
		if self.scheme and self.scheme.lower() not in self.valid_schemes:
			return False

		# Reject any URLs that contain characters known to cause parsing
		# differences between parser implementations
		for match in re.finditer(URL_PROBLEMATIC_RE, self._orig_url):
			# XXX: Yuck. We have non-breaking spaces in title slugs! They
			# should be safe enough to allow after three slashes. Opera 12's the
			# only browser that trips over them, and it doesn't fall for
			# `http:///foo.com/`.
			# Check both in case unicode promotion fails
			if match.group(0) in {'\xa0', '\xa0'}:
				if match.string[0:match.start(0)].count('/') < 3:
					return False
			else:
				return False

		return True

	@property
	def netloc(self):
		"""
		Getter method which returns the hostname:port, or empty string
		if no hostname is present.
		"""
		if not self.hostname:
			return ""
		elif getattr(self, "port", None):
			return self.hostname + ":" + str(self.port)
		return self.hostname

	def __repr__(self):
		return "<URL %s>" % repr(self.unparse())

	@classmethod
	def base_url(cls, url):
		u = cls(url)

		# strip off any www and lowercase the hostname:
		netloc = strip_www(u.netloc.lower())

		# http://code.google.com/web/ajaxcrawling/docs/specification.html
		fragment = u.fragment if u.fragment.startswith("!") else ""

		return urlunparse((u.scheme.lower(), netloc,
						   u.path, u.params, u.query, fragment))


class TimeoutFunctionException(Exception):
	pass


class TimeoutFunction:
	"""Force an operation to timeout after N seconds. Works with POSIX
	   signals, so it's not safe to use in a multi-treaded environment"""
	def __init__(self, function, timeout):
		self.timeout = timeout
		self.function = function

	def handle_timeout(self, signum, frame):
		raise TimeoutFunctionException()

	def __call__(self, *args, **kwargs):
		# can only be called from the main thread
		old = signal.signal(signal.SIGALRM, self.handle_timeout)
		signal.alarm(self.timeout)
		try:
			result = self.function(*args, **kwargs)
		finally:
			signal.alarm(0)
			signal.signal(signal.SIGALRM, old)
		return result
