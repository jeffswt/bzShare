
universal_options_list = {
    'author': 'Geoffrey, Tang.',
    'copyright': 'Copyright 2016, Geoffrey Tang. All lefts reversed.',
    'license': 'GNU GPL v3',
    'version': 'indev',
    'server-name': 'Apache/2.4.1 (Linux 2.6.32)'
}

def get_const(_):
    return universal_options_list[_] if _ in universal_options_list else None
