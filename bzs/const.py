
universal_options_list = {
    'author': 'Geoffrey, Tang.',
    'copyright': 'Copyright 2016, Geoffrey Tang. All lefts reversed.',
    'db-name': 'postgres',
    'db-user': 'root',
    'db-password': '123456',
    'db-host-addr': '127.0.0.1',
    'db-host-port': '8079',
    'license': 'GNU GPL v3',
    'server-name': 'Apache/2.4.1 (Linux 2.6.32)',
    'time-zone': 'Asia/Shanghai',
    'version': 'indev'
}

def get_const(_):
    return universal_options_list[_] if _ in universal_options_list else None
