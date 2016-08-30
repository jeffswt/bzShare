
print('')
print('SQLFS Interactive Console')
print('=' * 60)

from bzs import db

try:
    db.Filesystem.shell()
except Exception:
    pass

print('')
print('Exitting.')
print('')
