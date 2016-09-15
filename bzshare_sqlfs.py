
import urllib
import urllib.parse

print('')
print('SQLFS Interactive Console')
print('=' * 60)

from bzs import sqlfs

while True:
    try:
        sqlfs.Filesystem.shell()
    except KeyboardInterrupt:
        break
    except EOFError:
        break
    except Exception as err:
        raise err
        continue
    break

print('')
print('Exitting.')
print('')
