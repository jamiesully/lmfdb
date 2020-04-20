import os, yaml
from flask import url_for

class Box(object):
    def __init__(self, title):
        self.title = title
        self.content = None
        self.links = []
        self.target = "/"
        self.img = None

    def add_link(self, title, href):
        self.links.append((title, href))


def load_boxes():
    boxes = []
    _curdir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(_curdir, "index_boxes.yaml")) as boxfile:
        listboxes = yaml.load_all(boxfile, Loader=yaml.FullLoader)
        for b in listboxes:
            B = Box(b['title'])
            B.content = b['content']
            if 'image' in b:
                B.img = url_for('static', filename='images/'+b['image']+'.png')
            for title, url in b['links']:
                B.add_link(title, url)
            boxes.append(B)
    return boxes
