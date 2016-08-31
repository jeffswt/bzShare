
import urllib
import urllib.parse

print('')
print('SQLFS Interactive Console')
print('=' * 60)

from bzs import sqlfs

try:
    sqlfs.Filesystem.shell()
except Exception:
    pass

print('')
print('Exitting.')
print('')
