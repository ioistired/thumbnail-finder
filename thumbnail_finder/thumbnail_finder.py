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

import functools
import gzip
import io
import json
import logging
import re
import traceback
import urllib.parse
from urllib.error import HTTPError, URLError

from bs4 import BeautifulSoup
import requests
from PIL import Image, ImageFile

from .utils import (
	coerce_url_to_protocol,
	TimeoutFunction,
	TimeoutFunctionException,
	memoize,
)


_SESSION = requests.Session()


logging.basicConfig(level=logging.WARNING)


def _clean_url(url):
	"""url quotes unicode data out of urls"""
	return ''.join(urllib.parse.quote(c) if ord(c) >= 127 else c for c in url)


def _initialize_request(url, referer, gzip=False):
	url = _clean_url(url)

	if not url.startswith(("http://", "https://")):
		return

	req = urllib.request.Request(url)
	if gzip:
		req.add_header('Accept-Encoding', 'gzip')
	req.add_header(
		'User-Agent',
		'Mozilla/5.0 (Windows NT 6.3; Win64; x64) Gecko/20100101 Firefox/53.0'
	)
	if referer:
		req.add_header('Referer', referer)
	return req


def _fetch_url(url, referer=None):
	request = _initialize_request(url, referer=referer, gzip=True)
	if not request:
		return None, None
	response = urllib.request.urlopen(request)
	response_data = response.read()
	content_encoding = response.info().get("Content-Encoding")
	if content_encoding and content_encoding.lower() in ["gzip", "x-gzip"]:
		buf = io.BytesIO(response_data)
		f = gzip.GzipFile(fileobj=buf)
		response_data = f.read()
	return response.headers.get("Content-Type"), response_data


@memoize
def _fetch_image_size(url, referer):
	"""Return the size of an image by URL downloading as little as possible."""

	request = _initialize_request(url, referer)
	if not request:
		return None

	parser = ImageFile.Parser()
	response = None
	try:
		response = urllib.request.urlopen(request)

		while True:
			chunk = response.read(1024)
			if not chunk:
				break

			parser.feed(chunk)
			if parser.image:
				return parser.image.size
	except urllib.error.URLError:
		return None
	finally:
		if response:
			response.close()


@memoize
def get_thumbnail_url(url):
	def get_url(url):
		try:
			return Scraper.for_url(url).scrape()
		except (HTTPError, URLError):
			return None

	try:
		return TimeoutFunction(get_url, 30)(url)
	except TimeoutFunctionException:
		logging.error('Timed out on ' + url)
	except:
		logging.error('Error fetching ' + url)
		logging.error(traceback.format_exc())

@memoize
def fetch(url):
	if url is not None:
		return _SESSION.get(url).content


class Scraper(object):
	@classmethod
	def for_url(cls, url, autoplay=False, maxwidth=600, use_youtube_scraper=True):
		if use_youtube_scraper and _YouTubeScraper.matches(url):
			return _YouTubeScraper(url, maxwidth=maxwidth)

		return _ThumbnailOnlyScraper(url)

	def scrape(self):
		# should return a 4-tuple of:
		#	  thumbnail, preview_object, media_object, secure_media_obj
		raise NotImplementedError

	@classmethod
	def media_embed(cls, media_object):
		# should take a media object and return an appropriate MediaEmbed
		raise NotImplementedError


class _ThumbnailOnlyScraper(Scraper):
	def __init__(self, url):
		self.url = url
		# Having the source document's protocol on hand makes it easier to deal
		# with protocol-relative urls we extract from it.
		self.protocol = urllib.parse.urlparse(url).scheme

	def _extract_image_urls(self, soup):
		for img in soup.findAll("img", src=True):
			yield self._absolutify(img["src"])

	def _absolutify(self, relative_url):
		return urllib.parse.urljoin(self.url, relative_url)

	def scrape(self):
		"""Find what we think is the best thumbnail image URL for a link.

		Returns an image url.
		A value of None means we couldn't find an image
		"""
		content_type, content = _fetch_url(self.url)

		# if it's an image, it's pretty easy to guess what we should thumbnail.
		if content_type and 'image' in content_type and content:
			return self.url

		if content_type and "html" in content_type and content:
			soup = BeautifulSoup(content, 'lxml')
		else:
			return None

		scrapers = (
			self._scrape_og_url,
			self._scrape_thumbnail_spec,
			self._find_largest_image_url
		)

		for scraper in scrapers:
			logging.debug('Calling ' + scraper.__name__)
			result = scraper(soup)
			if result is not None:
				return result

	def _scrape_og_url(self, soup):
		# Allow the content author to specify the thumbnail using the Open
		# Graph protocol: http://ogp.me/
		og_image = (
			soup.find('meta', property='og:image')
			or soup.find('meta', attrs={'name': 'og:image'})
			or soup.find('meta', property='og:image:url')
			or soup.find('meta', attrs={'name': 'og:image:url'})
		)
		if og_image and og_image.get('content'):
			return self._absolutify(og_image['content'])

	def _scrape_thumbnail_spec(self, soup):
		# <link rel="image_src" href="http://...">
		thumbnail_spec = soup.find('link', rel='image_src')
		if thumbnail_spec and thumbnail_spec['href']:
			return self._absolutify(thumbnail_spec['href'])

	def _find_largest_image_url(self, soup):
		# ok, we have no guidance from the author. look for the largest
		# image on the page with a few caveats. (see below)
		max_area = 0
		max_url = None
		for image_url in self._extract_image_urls(soup):
			logging.debug('Extracted image URL', image_url)
			# When isolated from the context of a webpage, protocol-relative
			# URLs are ambiguous, so let's absolutify them now.
			if image_url.startswith('//'):
				image_url = coerce_url_to_protocol(image_url, self.protocol)
			size = _fetch_image_size(image_url, referer=self.url)
			if not size:
				continue

			area = size[0] * size[1]

			# ignore little images
			if area < 5000:
				logging.debug('ignore little %s' % image_url)
				continue

			# ignore excessively long/wide images
			if max(size) / min(size) > 2:
				logging.debug('ignore dimensions %s' % image_url)
				continue

			# penalize images with "sprite" in their name
			if 'sprite' in image_url.lower():
				logging.debug('penalizing sprite %s' % image_url)
				area /= 10

			if area > max_area:
				max_area = area
				max_url = image_url

		logging.debug('Max URL ' + max_url)
		return max_url



class _YouTubeScraper(Scraper):
	OEMBED_ENDPOINT = "https://www.youtube.com/oembed"
	URL_MATCH = re.compile(r"https?://((www\.)?youtube\.com/watch|youtu\.be/)")

	def __init__(self, url, maxwidth):
		self.url = url
		self.maxwidth = maxwidth

	@classmethod
	def matches(cls, url):
		return cls.URL_MATCH.match(url)

	def _fetch_from_youtube(self):
		params = {
			"url": self.url,
			"format": "json",
			"maxwidth": self.maxwidth,
		}

		return json.loads(_SESSION.get(self.OEMBED_ENDPOINT, params=params).text)

	def scrape(self):
		oembed = self._fetch_from_youtube()
		if not oembed:
			return

		return oembed.get("thumbnail_url")
