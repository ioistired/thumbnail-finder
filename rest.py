#!/usr/bin/env python3
# encoding: utf-8

import logging

from flask import Flask, request, Response

from thumbnail_finder import get_thumbnail_url

app = Flask(__name__)

DEBUG = False

API_VERSION = 0
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUG else logging.WARNING)

@app.route('/api/v{}/thumbnail'.format(API_VERSION))
def main():
	page_url = request.args.get('page_url')
	logger.debug('Got page url ' + page_url)
	image_url = get_thumbnail_url(request.args.get('page_url'))
	result = image_url if image_url is not None else 'null'
	logger.debug('Returning thumbnail url ' + result)
	return Response(result, mimetype='text/plain')


if __name__ == '__main__':
	app.run(debug=DEBUG)
	print('Running')
