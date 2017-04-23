import sys
import os
from os import listdir
from os.path import isfile, join

import io
from PIL import Image
from kivy.app import App
from kivy.factory import Factory

from cobiv.common import set_action
from cobiv.modules.entity import Entity

import threading
import sqlite3

from cobiv.modules.imageset.ImageSet import create_thumbnail_data
from cobiv.modules.session.cursor import Cursor, CursorInterface

SUPPORTED_IMAGE_FORMATS = ["jpg", "gif", "png"]
CURRENT_SET_NAME = '_current'


class SqliteCursor(CursorInterface):
    set_head_key = None
    con = None
    current_set = True

    def __init__(self, row, backend=None, current=True):
        self.con = backend
        self.current_set = current
        self.init_row(row)
        self.thumbs_path = App.get_running_app().get_config_value('thumbnails.path')

    def init_row(self, row):
        if row is None:
            self.pos = None
            self.set_head_key = None
            self.filename = ''
            self.file_id = None
        else:
            self.pos = row['position']
            self.set_head_key = row['set_head_key']
            row1 = self.con.execute('select name from file where rowid=?', (row['file_key'],)).fetchone()
            self.filename = row1['name'] if row is not None else None
            self.file_id = row['file_key']

    def go_next(self):
        return self.go(self.pos + 1)

    def go_previous(self):
        return self.go(self.pos - 1)

    def get_tags(self):
        return []

    def go_first(self):
        return self.go(0)

    def go_last(self):
        if self.pos is None:
            return
        last_pos_row = self.con.execute('select max(position) from current_set where set_head_key=?',
                                        (self.set_head_key,)).fetchone()
        if last_pos_row is not None:
            return self.go(last_pos_row[0])
        else:
            return False

    def get(self, idx):
        if self.pos is None:
            return
        row = self.con.execute('select rowid,* from current_set where set_head_key=? and position=?',
                               (self.set_head_key, idx)).fetchone()
        return row

    def get_next_ids(self, amount):
        if self.pos is None:
            return []

        rows = self.con.execute(
            'select c.file_key,c.position,f.name from current_set c, file f where f.rowid=c.file_key and c.set_head_key=? and c.position>? and c.position<=? order by position',
            (self.set_head_key, self.pos, self.pos + amount)).fetchall()
        return rows

    def get_previous_ids(self, amount):
        if self.pos is None:
            return []

        rows = self.con.execute(
            'select c.file_key,c.position,f.name from current_set c, file f where f.rowid=c.file_key and c.set_head_key=? and c.position<? and c.position>=? order by position desc',
            (self.set_head_key, self.pos, self.pos - amount)).fetchall()
        return rows

    def go(self, idx):
        if self.pos is None:
            return
        row = self.con.execute('select rowid,* from current_set where set_head_key=? and position=?',
                               (self.set_head_key, idx)).fetchone()
        if row is not None:
            self.init_row(row)
        return row is not None

    def mark(self, value):
        if self.pos is None:
            return
        with self.con:
            if self.get_mark() and value is None or value == False:
                self.con.execute('delete from marked where file_key=?', (self.file_id,))
            else:
                self.con.execute('insert into marked values (?)', (self.file_id,))

    def get_mark(self):
        if self.pos is None:
            return
        return self.con.execute('select count(*) from marked where file_key=?', (self.file_id,)).fetchone()[0] > 0

    def get_all_marked(self):
        return [r[0] for r in self.con.execute('select file_key from marked', ).fetchall()]

    def __len__(self):
        if self.pos is None:
            return
        row = self.con.execute('select count(*) from current_set where set_head_key=?',
                               (self.set_head_key,)).fetchone()

        return 0 if row is None else row[0]

    def remove(self):
        if self.pos is None:
            return

        new_pos = self.pos
        next = self.get(self.pos + 1)
        if next is None:
            next = self.get(self.pos - 1)
            new_pos = self.pos - 1
        with self.con:
            self.con.execute('delete from current_set where file_key=?', (self.file_id,))
            self.con.execute('delete from marked where file_key=?', (self.file_id,))
            self.con.execute('update current_set set position=position-1 where set_head_key=? and position>?',
                             (self.set_head_key, self.pos))

        self.init_row(next)

        self.pos = new_pos

        return True

    def get_cursor_by_pos(self, pos):
        return SqliteCursor(self.get(pos), self.con)

    def get_thumbnail_filename(self, file_id):
        return os.path.join(self.thumbs_path, str(file_id) + '.png')

    def get_thumbnail(self):
        filename = self.get_thumbnail_filename(self.file_id)
        if not os.path.exists(filename):
            create_thumbnail_data(self.filename, 120, filename)
        return filename

    def move_to(self, pos):
        if pos == self.pos:
            return

        if pos < self.pos:
            query = 'update current_set set position=position+1 where set_head_key=? and position<? and position>=?'
        else:
            query = 'update current_set set position=position-1 where set_head_key=? and position>? and position<=?'

        with self.con:
            self.con.execute('update current_set set position=-1 where set_head_key=? and position=?',
                             (self.set_head_key, self.pos))
            self.con.execute(query, (self.set_head_key, self.pos, pos))
            self.con.execute('update current_set set position=? where set_head_key=? and position=-1',
                             (pos, self.set_head_key))

        self.pos = pos

    def get_position_mapping(self, file_id_list):
        if file_id_list is None:
            return []

        rows = self.con.execute(
            'select file_key,position from current_set where set_head_key=? and position in (%s)' % ','.join(
                '?' * len(file_id_list)),
            (self.set_head_key,) + tuple(file_id_list)).fetchall()

        return rows


class SqliteDb(Entity):
    cancel_operation = False
    session = None

    def ready(self):
        if not os.path.exists(self.get_app().get_user_path('thumbnails')):
            os.makedirs(self.get_app().get_user_path('thumbnails'))

        self.conn = sqlite3.connect(
            self.get_global_config_value('database.path', self.get_app().get_user_path('cobiv.db')),
            check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        self.conn.execute('PRAGMA temp_store = MEMORY')
        self.conn.execute('PRAGMA locking_mode = EXCLUSIVE')

        # add actions
        set_action("search", self.search_tag, "viewer")
        set_action("search", self.search_tag, "browser")
        set_action("add-tag", self.add_tag, "viewer")
        set_action("rm-tag", self.remove_tag, "viewer")
        set_action("ls-tag", self.list_tags, "viewer")
        set_action("updatedb", self.updatedb)
        set_action("mark-all", self.mark_all)
        set_action("mark-invert", self.invert_marked)

        self.session = self.get_app().lookup("session", "Entity")

        must_initialize = True
        try:
            must_initialize = self.conn.execute('select 1 from catalog limit 1').fetchone() is None
        except sqlite3.OperationalError:
            pass

        if must_initialize:
            self.create_database()
        with self.conn:
            self.conn.execute('create temporary table marked (file_key int)')
            self.conn.execute('create temporary table current_set as select * from set_detail where 1=2')

    def create_database(self):
        with self.conn:
            self.conn.execute('create table catalog (name text)')
            self.conn.execute('create table repository (catalog_key int, path text, recursive num)')
            self.conn.execute('create table file (repo_key int, name text, filename text, path text, ext text)')
            self.conn.execute('create table tag (file_key int, kind text, value text)')
            self.conn.execute('create table set_head ( name text, readonly num)')
            self.conn.execute('create table set_detail (set_head_key int, position int, file_key int)')
            self.conn.execute('create table thumbs (file_key int primary key, data blob)')

            # indexes
            self.conn.execute('create unique index file_idx on file(name)')
            self.conn.execute('create unique index tag_idx on tag(file_key,kind,value)')
            self.conn.execute('create unique index set_detail_pos_idx on set_detail(set_head_key,position)')
            self.conn.execute('create unique index set_detail_file_idx on set_detail(set_head_key,file_key)')

        self.create_catalogue("default")

        repos = self.get_global_config_value('repository', self.get_app().get_user_path('Pictures'))
        self.add_repository("default", repos)
        self.updatedb()

    def create_catalogue(self, name):
        try:
            with self.conn:
                c = self.conn.execute("insert into catalog (name) values(?) ", (name,))
            return c.lastrowid
        except sqlite3.IntegrityError:
            return False

    def add_repository(self, catalogue, path, recursive=True):
        try:
            with self.conn:
                c = self.conn.execute('insert into repository (catalog_key,path,recursive) values (?,?,?)',
                                      (catalogue, path, 1 if recursive else 0))
            return c.lastrowid
        except sqlite3.IntegrityError:
            return False

    def updatedb(self):
        threading.Thread(target=self._threaded_updatedb).start()

    def _threaded_updatedb(self):
        self.start_progress("Initializing update...")
        c = self.conn.execute('select rowid, path, recursive from repository')
        differences = []
        thread_max_files = 0

        rows = c.fetchall()
        self.set_progress_max_count(len(rows))
        for row in rows:
            repo_id = row[0]
            to_add, to_remove = self._update_get_diff(repo_id, row[1], row[2])
            differences.append((repo_id, to_add, to_remove))
            thread_max_files += len(to_add) + len(to_remove) + 1 if len(to_add) > 0 else 0 + 1 if len(
                to_remove) > 0 else 0
            self.tick_progress()

        if thread_max_files > 0:
            self.reset_progress("Updating files...")
            self.set_progress_max_count(thread_max_files)

            for diff in differences:
                self._update_dir(diff[0], diff[1], diff[2])
                if self.cancel_operation:
                    break

            self.regenerate_set('*', "select rowid from file", caption="Creating default set...")

        self.stop_progress()

    def _update_get_diff(self, repo_id, path, recursive):
        if recursive:
            result = [os.path.join(dp, f) for dp, dn, filenames in os.walk(path) for f in filenames if
                      os.path.splitext(f)[1][1:] in SUPPORTED_IMAGE_FORMATS]
        else:
            result = [join(path, f) for f in listdir(path) if
                      isfile(join(path, f)) and f.split('.')[-1] in SUPPORTED_IMAGE_FORMATS]

        c = self.conn.execute('select name from file where repo_key=?', (repo_id,))
        existing = [n['name'] for n in c.fetchall()]

        new_files = set(result) - set(existing)
        removed_files = set(existing) - set(result)
        return new_files, removed_files

    def _update_dir(self, repo_id, to_add, to_rem):
        with self.conn:
            c = self.conn.cursor()

            # remove old ones
            if len(to_rem) > 0:
                query_to_rem = [(n,) for n in to_rem]
                self.conn.executemany('delete from file where name=?', query_to_rem)
                self.tick_progress()

            query_to_add = []
            # add new ones
            for f in to_add:
                if self.cancel_operation:
                    return
                query_to_add.append((repo_id, f, os.path.basename(f), os.path.dirname(f), os.path.splitext(f)[1][1:]))
                self.tick_progress()

            c.executemany('insert into file(repo_key, name, filename, path, ext) values(?,?,?,?,?)', query_to_add)
            self.tick_progress()
            tags_to_add = []
            for f in to_add:
                id = c.execute('select rowid from file where repo_key=? and name=? limit 1', (repo_id, f)).fetchone()[0]
                lines = self.read_tags(id, f)
                if len(lines) > 0:
                    tags_to_add.extend(lines)
                self.tick_progress()

            if len(tags_to_add) > 0:
                c.executemany('insert into tag values (?,?,?)', tags_to_add)
                self.tick_progress()

    def read_tags(self, node_id, name):
        to_add = []
        img = Image.open(name)
        if img.info:
            for i, v in img.info.iteritems():
                if i == "tags":
                    tag_list = v.split(",")
                    for tag in tag_list:
                        to_add.append((node_id, 'tag', tag.strip()))
        return to_add

    def regenerate_set(self, set_name, query, caption=None):

        is_current = set_name == "_current"

        with self.conn:
            c = self.conn.cursor()

            if is_current:
                self.conn.execute('drop table if exists current_set') \
                    .execute(
                    'create temporary table current_set as select * from set_detail where 1=2')
                head_key = 0
            else:
                row = c.execute('select rowid from set_head where name=?', (set_name,)).fetchone()
                if row is not None:
                    head_key = row[0]
                    c.execute('delete from set_detail where set_head_key=?', (head_key,))
                else:
                    c.execute('insert into set_head values (?,?)', (set_name, '0'))
                    head_key = c.lastrowid

            resultset = c.execute(query).fetchall()
            self.set_progress_max_count(len(resultset) + 1)
            self.reset_progress(caption)
            lines = []
            thread_count = 0
            for row in resultset:
                lines.append((head_key, thread_count, row['rowid']))
                self.tick_progress()
                thread_count += 1

            query = 'insert into %s (set_head_key, position, file_key) values (?,?,?)' % (
                'current_set' if is_current else 'set_detail')
            c.executemany(query, lines)
            self.tick_progress()

    def copy_set_to_current(self, set_name):
        with self.conn:
            self.conn.execute('drop table if exists current_set') \
                .execute(
                'create temporary table current_set as select d.* from set_detail d,set_head h where d.set_head_key=h.rowid and h.name=? order by d.position',
                set_name)

    def search_tag(self, *args):
        if len(args) == 0:
            self.copy_set_to_current('*')
        else:
            to_include = []
            to_exclude = []

            for arg in args:
                if arg[0] == "-":
                    to_exclude.append(arg[1:])
                else:
                    to_include.append(arg)

            query = 'select f.rowid,f.name from file f ,tag t where t.file_key=f.rowid '
            if len(to_include) > 0:
                query += 'and t.value in ("' + '", "'.join(to_include) + '") '
            if len(to_exclude) > 0:
                query += 'and t.value not in ("' + '", "'.join(to_exclude) + '") '

            self.regenerate_set(CURRENT_SET_NAME, query)

        row = self.conn.execute('select rowid, * from current_set where position=0 limit 1').fetchone()
        self.session.cursor.set_implementation(None if row is None else SqliteCursor(row, self.conn))

        self.get_app().root.execute_cmd("load-set")

    def add_tag(self, *args):
        if len(args) == 0:
            return
        filekey = self.session.cursor.file_id
        if filekey is None:
            return

        with self.conn:
            for tag in args:
                c = self.conn.execute('select 1 from tag where value=? and file_key=? limit 1', (tag, filekey))
                if c.fetchone() is None:
                    c.execute('insert into tag values (?,?,?)', (self.session.cursor.file_id, 'tag', tag))

    def remove_tag(self, *args):
        if len(args) == 0:
            return
        filekey = self.session.cursor.file_id
        if filekey is None:
            return

        with self.conn:
            self.conn.execute('delete from tag where file_key=? and value in (?)', (filekey,
                                                                                    ', '.join(args)))

    def list_tags(self):
        filekey = self.session.cursor.file_id
        if filekey is None:
            return

        c = self.conn.execute('select t.value from tag t where file_key=?', (filekey,))
        text = '\n'.join([r['value'] for r in c.fetchall()])
        App.get_running_app().root.notify(text)

    def on_application_quit(self):
        self.cancel_operation = True

    def mark_all(self, value=None):
        with self.conn:
            if value is None:
                value = self.conn.execute(
                    'select count(*) from current_set c left join marked m on m.file_key=c.file_key' +
                    ' where m.file_key is null').fetchone()[0] > 0
            else:
                value = value != "False" or value != "0"

            self.conn.execute('delete from marked')
            if value:
                self.conn.execute('insert into marked (file_key) select file_key from current_set')
        self.get_app().root.execute_cmd("refresh-marked")

    def invert_marked(self):
        with self.conn:
            self.conn.execute(
                'create temporary table marked1 as select cs.file_key from current_set cs left join marked m on m.file_key=cs.file_key' +
                ' where m.file_key is null')
            self.conn.execute('delete from marked')
            self.conn.execute('insert into marked select file_key from marked1')
            self.conn.execute('drop table marked1')
            self.get_app().root.execute_cmd("refresh-marked")

    def build_yaml_config(self, config):
        config[self.get_name()] = {
            'database': {
                'path': self.get_app().get_user_path('cobiv.db')
            }
        }


Factory.register('Cursor', module=SqliteCursor)
