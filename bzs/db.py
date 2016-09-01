
import io
import psycopg2
import psycopg2.extras

from . import const
from . import utils

################################################################################

class DatabaseType:
    def __init__(self):
        self.connect_params = dict(
            database=const.get_const('db-name'),
            user=const.get_const('db-user'),
            password=const.get_const('db-password'),
            host=const.get_const('db-host-addr'),
            port=const.get_const('db-host-port')
        )
        psycopg2.extras.register_uuid()
        self.init_db(False)
        return

    def execute(self, command, args=None, fetch_func='all'):
        with psycopg2.connect(**self.connect_params) as l_db:
            with l_db.cursor() as l_cur:
                try:
                    l_cur.execute(command, args)
                except psycopg2.ProgrammingError as err:
                    print('Exception occured in PostgreSQL while executing the command:\n    %s: %s\n    %s\n' % (type(err), err, command))
                    # raise err
                try:
                    if fetch_func == 'one':
                        final_arr = l_cur.fetchone()
                    elif fetch_func == 'all':
                        final_arr = l_cur.fetchall()
                    else:
                        final_arr = None
                except Exception:
                    final_arr = None
        return final_arr

    def execute_raw(self):
        return psycopg2.connect(**self.connect_params)

    def init_db(self, force=True):
        # If database already initialized, and not forced to init, then ignore
        if not force and self.execute("SELECT data FROM core WHERE index = %s;", ('db_initialized',)):
            return True
        print('Initializing PostgreSQL database.')
        # Purge database of obsolete tables
        self.execute("""
            DROP TABLE IF EXISTS core;
        """)
        self.execute("""
            DROP TABLE IF EXISTS users;
        """)
        self.execute("""
            DROP TABLE IF EXISTS file_storage;
        """)
        self.execute("""
            DROP TABLE IF EXISTS file_storage_sparse;
        """)
        self.execute("""
            DROP TABLE IF EXISTS file_system;
        """)
        # Creating new tables in order to function
        # TIMESTAMPs has lower precision than DOUBLE, so we are using DOUBLE PRECISION instead.
        self.execute("""
            CREATE TABLE core (
                index       TEXT,
                data        BYTEA
            );
            CREATE TABLE users (
                handle      TEXT,
                data        BYTEA
            );
            CREATE TABLE file_storage (
                uuid        UUID,
                size        BIGINT,
                count       BIGINT,
                hash        TEXT,
                content     OID
            );
            CREATE TABLE file_storage_sparse (
                uuid        UUID,
                size        BIGINT,
                count       BIGINT,
                sub_uuid    UUID[],
                sub_size    BIGINT[],
                sub_count   BIGINT[],
                sub_hash    TEXT[],
                sub_content BYTEA[]
            );
            CREATE TABLE file_system(
                uuid        UUID,
                file_name   TEXT,
                owners      TEXT[],
                permissions TEXT,
                upload_time DOUBLE PRECISION,
                sub_folders UUID[],
                sub_files   TEXT[][]
            );
        """)
        # Marking this database as initialized
        self.execute("INSERT INTO core (index, data) VALUES ('db_initialized', %s)", (b'\x80\x03\x88\x2E',))
        return True
    pass

Database = DatabaseType()

################################################################################
