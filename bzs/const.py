
universal_options_list = {
    'author': 'Geoffrey, Tang.',
    'copyright': 'Copyright 2016, @ht35268. All lefts reversed.',
    'db-name': 'testdb',
    'db-user': 'postgres',
    'db-password': '123456',
    'db-host-addr': '127.0.0.1',
    'db-host-port': '8079',
    'license': 'GNU GPL v3',
    'server-name': 'Tornado/4.4',
    'time-format': '%a %Y/%m/%d, %H:%M:%S',
    'time-zone': 'Asia/Shanghai',
    'version': 'r0.17'
}

def get_const(_):
    return universal_options_list[_] if _ in universal_options_list else None
