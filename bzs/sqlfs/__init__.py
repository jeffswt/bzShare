
from . import file_storage
from . import file_system

from .. import db
from .. import utils

# Initialize file storage system

FileStorage = file_storage.FileStorage(
    database = db.Database,
    utils_package = utils)

# Initialize filesystem

Filesystem = file_system.Filesystem(
    database      = db.Database,
    filestorage   = FileStorage,
    utils_package = utils)
