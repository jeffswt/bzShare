
import math
import mimetypes
import re
import time
import uuid

################################################################################
# MIME Types

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

################################################################################
# File data management

def get_static_data(filename):
    filename = re.sub('[?&].*$', '', filename)
    hfile = open(filename, 'rb')
    data = hfile.read()
    return data

def get_static_data_utf(filename):
    return get_static_data(filename).decode('utf-8', 'ignore')

def format_file_size(size_b, use_binary=False, verbose=False):
    if not use_binary:
        if not verbose:
            complexity_idx = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
        else:
            complexity_idx = ['Bytes', 'Kilobytes', 'Megabytes', 'Gigabytes', 'Terabytes', 'Petabytes', 'Exabytes', 'Zettabytes', 'Yottabytes']
        try:
            complexity = int(math.log(size_b, 1000))
        except:
            complexity = 0
        size_f = size_b / 1000 ** complexity
        complexity_s = complexity_idx[complexity]
    else:
        if not verbose:
            complexity_idx = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
        else:
            complexity_idx = ['Bytes', 'Kibibytes', 'Mebibytes', 'Gibibytes', 'Tebibytes', 'Pebibytes', 'Exbibytes', 'Zebibytes', 'Yobibytes']
        try:
            complexity = int(math.log(size_b, 1000))
        except:
            complexity = 0
        size_f = size_b / 1024 ** complexity
        complexity_s = complexity_idx[complexity]
    return '%.2f %s' % (size_f, complexity_s)

################################################################################
# Time operations

def get_current_time():
    """Gets the current time, in float since epoch."""
    return float(time.time())

################################################################################
# UUID operations

def get_new_uuid(uuid_, uuid_list=None):
    """Creates a new UUID that is not in 'uuid_list' if given."""
    if not uuid_:
        uuid_ = uuid.uuid4()
        if type(uuid_list) in [set, dict]:
            while uuid_ in uuid_list:
                uuid_ = uuid.uuid4()
    return uuid_
