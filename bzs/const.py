
import urllib
import urllib.parse
import os

urllib.parse.uses_netloc.append('postgres')
if 'DATABASE_URL' in os.environ:
    db_url = urllib.parse.urlparse(os.environ['DATABASE_URL'])
else:
    db_url = None

universal_options_list = {
    'author': '@ht35268',
    'copyright': 'Copyright 2016, @ht35268. All lefts reversed.',
    'db-name': db_url.path[1:] if db_url
        else 'db_bzshare',
    'db-user': db_url.username if db_url
        else 'postgres',
    'db-password': db_url.password if db_url
        else '123456',
    'db-host-addr': db_url.hostname if db_url
        else '127.0.0.1',
    'db-host-port': db_url.port if db_url
        else '8079',
    'license': 'GNU GPL v3',
    'max-body-size': 256 * 1024 * 1024,
    'server-admin-password': os.environ.get('BZS_SERVER_ADMIN_PASSWORD', '12345678'),
    'server-name': 'Tornado/4.4',
    'server-port': int(os.environ.get('PORT',80)),
    'server-threads': 1,
    'time-format': '%a %d/%m/%Y, %H:%M:%S',
    'time-zone': 'Asia/Shanghai',
    'users-invite-code': os.environ.get('BZS_USERS_INVITE_CODE', '571428'),
    'users-max-groups-allowed': 3,
    'version': 'r0.24-dev'
}

def get_const(_):
    return universal_options_list[_] if _ in universal_options_list else None
