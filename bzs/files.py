
import mimetypes
import re

mime_types_dict = {}

def parse_mime_types():
    global mime_types_dict
    mime_types_dict = mimetypes.read_mime_types('./bzs/mime.types')
    if not mime_types_dict:
        mime_types_dict = {}
    return True

def guess_mime_type(filename):
    extension = re.findall(r'(.[^.]*)$', filename)
    extension = extension[0] if extension else '.'
    extension = mime_types_dict[extension] if extension in mime_types_dict else 'application/octet-stream'
    return extension

parse_mime_types()

# File data management

def get_static_data(filename):
    filename = re.sub('[?&].*$', '', filename)
    hfile = open(filename, 'rb')
    data = hfile.read()
    return data

def get_static_data_utf(filename):
    return get_static_data(filename).decode('utf-8', 'ignore')
