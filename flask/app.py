#!/usr/bin/env python3
# encoding: utf-8

import imghdr as _imghdr
import logging
import sys as _sys

from flask import Flask, request, render_template, Response

from thumbnail_finder import get_thumbnail_url, fetch



app = Flask(__name__)
DEBUG = False
API_VERSION = 0
BASE_URL = '/api/v{}/'.format(API_VERSION)
logging.basicConfig(level=logging.DEBUG if DEBUG else logging.WARNING)


@app.route(BASE_URL + 'thumbnail')
def thumbnail():
	page_url = request.args.get('page_url')
	logging.debug('User requested page url ' + page_url)
	image_url = get_thumbnail_url(page_url)
	if request.args.get('preview') in ('true', ''): # also allow ?preview
		logging.debug('User requested image proxy')
		response = respond_to_image(fetch(image_url))
		# TODO find a cleaner way to do this
		if response is not None:
			return response
		else:
			return make_plain(nullify(None))
	return make_plain(nullify(image_url))


@app.route('/docs')
# we set the path to '/docs' so that
# /static can be rewritten to / by Caddy
# otherwise, we would have to proxy / to Flask
# and all of the static requests would be proxied too
def index():
	return render_template('index.html', version=API_VERSION)

@app.errorhandler(500)
def internal_server_error(e):
	return error_response(500)

@app.errorhandler(404)
def not_found(e):
	return error_response(404)


### UTILITY FUNCS

def error_response(error_code):
	return make_plain(
		'ya dun guffed ({})'.format(error_code),
		status=error_code,
	)


def make_plain(*args, **kwargs):
	kwargs['mimetype'] = 'text/plain'
	return Response(*args, **kwargs)

def make_gen(iterable):
	yield from iterable

def respond_to_image(b: bytes):
	mimetypes = {
		'rgb': 'image/x-rgb',
		'gif': 'image/gif',
		'pbm': 'image/x-portable-bitmap',
		'pgm': 'image/x-portable-graymap',
		'tiff': 'image/tiff',
		# not sure about this one, might be x-cmu-raster
		'rast': 'image/cmu-raster',
		'xbm': 'image/x-xbm',
		'jpeg': 'image/jpg',
		'bmp': 'image/bmp',
		'png': 'image/png',
		'webp': 'image/webp',
		'exr': 'image/x-exr',
	}
	# stream the bytes to Flask
	if b is not None:
		return Response(b, mimetype=mimetypes.get(_imghdr.what(None, b)))


def nullify(thing):
	'''convert None values of `thing` to "null"'''
	return "null" if thing is None else thing


if __name__ == '__main__':
	app.run(debug=DEBUG)
	logging.info('Running')
	# sometimes the status message isn't written until the app is closed
	# unless we flush stdout
