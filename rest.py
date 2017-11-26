#!/usr/bin/env python3
# encoding: utf-8

from flask import Flask, request, Response

from thumbnail_finder import get_thumbnail_url


app = Flask(__name__)
DEBUG = True
API_VERSION = 0

@app.route('/api/v{}/thumbnail'.format(API_VERSION))
def main():
	image_url = get_thumbnail_url(request.args.get('page_url'))
	result = image_url if image_url is not None else 'null'
	return Response(result, mimetype='text/plain')


if __name__ == '__main__':
	app.run(debug=DEBUG)
	print('Running')
