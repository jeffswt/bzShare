
import base64
import binascii
import gzip
import hashlib
import mako
import mako.template
import math
import mimetypes
import random
import re
import time
import uuid

from . import const

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

def preprocess_webpage(data, content_user, **additional_arguments):
    if type(data) == bytes:
        data = data.decode('utf-8', 'ignore')
    data = mako.template.Template(
        text=data,
        input_encoding='utf-8',
        output_encoding='utf-8').render(
            placeholder_version_number = const.get_const('version'),
            placeholder_copyright_message = const.get_const('copyright'),
            user_is_administrator = content_user.handle == 'kernel',
            user_is_standard_user = content_user.handle != 'guest',
            current_user = content_user,
            **additional_arguments if additional_arguments else dict()
        )
    return data

################################################################################
# Time operations

def get_current_time():
    """Gets the current time, in float since epoch."""
    return float(time.time())

################################################################################
# Hash operations

def sha512_hex(data):
    if type(data) == str:
        data = data.encode('utf-8', 'ignore')
    sha_bin = hashlib.sha512(data).digest()
    sha_hex = binascii.hexlify(sha_bin)
    return sha_hex.decode('utf-8', 'ignore')

def password_hashed(pswin):
    """ Create a high computational complexity password hashing algorithm. """
    def MD100_xmcp_shile(pswin):
        """ MD100 hashing algorithm created by @xmcp. Each call on this function
        causes 1 iteration and only. Source:

        https://github.com/xmcp/shile/blob/master/hasher.py """
        psw1=hashlib.sha224()
        psw1.update(pswin.encode())
        psw2=hashlib.sha256()
        psw2.update(pswin[::-1].encode())
        psw3=hashlib.sha384()
        psw3.update(pswin.center(100, 'a').encode())
        psw4=hashlib.sha512()
        psw4.update(pswin.swapcase().encode())
        psw5=hashlib.sha1()
        psw5.update(base64.b64encode(pswin.encode()))
        psw6=hashlib.md5()
        psw6.update(base64.b32encode(pswin.rjust(100, 'a').encode()))
        return psw1.hexdigest()[0:16] + psw2.hexdigest()[0:16] + \
               psw3.hexdigest()[0:16] + psw4.hexdigest()[0:16] + \
               psw5.hexdigest()[0:16] + psw6.hexdigest()[0:16]
    # Iterations...
    magic_str = 'esloplwnmhcelfqbevnmjcxyhvshiejhdvecrebngyrsahqlirwtgpieopqwokdb'
    magic_num = 233 # Laugh out loud
    magic_cnt = 42
    for i in range(0, magic_num):
        pswin = sha512_hex((magic_str + MD100_xmcp_shile(pswin)) * magic_cnt)
    return pswin

def password_make(inp):
    return sha512_hex(inp)

def password_make_hashed(inp):
    return password_hashed(password_make(inp))

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

def get_new_cookie(cookies_list=None):
    cookie = ''
    if not cookies_list:
        cookies_list = ['']
    while cookie in cookies_list or not cookie:
        cookie = base64.b64encode(str(random.randrange(0, 10**1024)).ljust(128)[:128].encode(
'utf-8', 'ignore')).decode('utf-8', 'ignore')
    return cookie

def encode_str_to_hexed_b64(data):
    return binascii.b2a_hex(base64.b64encode(data.encode('utf-8'))).decode('utf-8')

def decode_hexed_b64_to_str(data):
    return base64.b64decode(binascii.unhexlify(data.encode('utf-8'))).decode('utf-8')

################################################################################
# Content validity operations

def get_safe_keys(*args):
    safe_keys = dict(
        letters_alpha = 'abcdefghijklmnopqrstuvwxyz',
        letters_cap = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
        letters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
        numbers = '0123456789',
        numbers_symbols = '!@#$%^&*()-=_+',
        symbols_alpha = '`[];\'\\,./',
        symbols_cap = '~{}:"|<>?',
        symbols = '!@#$%^&*()-=_+`[];\'\\,./~{}:"|<>? ',
        html_escape = '<>&'
    )
    final = ''
    for i in args:
        if i in safe_keys:
            final += safe_keys[i]
    distinct_fin = ''
    for i in final:
        if i not in distinct_fin:
            distinct_fin += i
    return distinct_fin

def is_safe_string(src, *args):
    ar = get_safe_keys(*args)
    for i in src:
        if i not in ar:
            return False
    return True

def is_unsafe_string(src, *args):
    ar = get_safe_keys(*args)
    for i in src:
        if i in ar:
            return True
    return False
