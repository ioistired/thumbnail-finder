import thumbnail_finder
from flask import Flask, request
app = Flask(__name__)

@app.route('/')
def main():
    url = request.args.get('url')
    image = thumbnail_finder.get_thumbnail_url(url)
    print(url)
    print(image)
    if not image == None:
        return image
    return "null"
