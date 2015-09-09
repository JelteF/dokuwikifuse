import llfuse
from llfuse import Operations as BaseOperations
from llfuse import EntryAttributes, FUSEError, ROOT_INODE

from dokuwiki import DokuWiki

import errno
import os
import stat

from os import fsencode, fsdecode
from collections import UserDict
from uuid import uuid4
import time

from pprint import pprint  # noqa


class WikiEntry(EntryAttributes):
    def __init__(self, ops, parent, *, inode=None):
        super().__init__()

        if inode is None:
            print('going to generate a unique inode number')
            inode = uuid4().int & (1 << 32)-1
            while inode in ops:
                inode = uuid4().int & (1 << 32)-1

        self.inode = inode
        print('inode is', self.inode)
        self.parent = parent

        self.st_uid = os.getuid()
        self.st_gid = os.getgid()

        # mode = -rw-r--r--
        self.st_mode = stat.S_IRUSR | stat.S_IWUSR | \
            stat.S_IRGRP | stat.S_IROTH

        self.ops = ops
        self.ops[self.inode] = self

    def __repr__(self):
        string = '<%s(' % self.__class__.__name__
        for i, attr in enumerate(['inode', 'path']):
            if i:
                string += ', '
            string += repr(getattr(self, attr))
        string += ', '
        string += stat.filemode(self.st_mode)

        string += ')>'
        return string

    def to_readdir_format(self):
        return fsencode(self.filename), self, self.inode

    @property
    def filename(self):
        return self.name

    @property
    def inode(self):
        return self.st_ino

    @inode.setter
    def inode(self, value):
        self.st_ino = value

    @property
    def modified(self):
        return self.st_mtime

    @modified.setter
    def modified(self, value):
        self.st_atime = value
        self.st_ctime = value
        self.st_mtime = value

    @property
    def depth(self):
        if self.inode == ROOT_INODE:
            return 0
        return self.parent.depth + 1

    @property
    def location(self):
        if self.inode == ROOT_INODE or self.parent.inode == ROOT_INODE:
            return ''
        return self.parent.path

    @property
    def path(self):

        return self.location + '/' + self.filename


class WikiFile(WikiEntry):
    _text = None

    def __init__(self, wiki_data, *args, **kwargs):
        self.name = wiki_data['id']
        print('Creating a file called: ' + self.name)

        super().__init__(*args, **kwargs)

        self.modified = wiki_data['mtime']

        self.st_size = wiki_data['size']

        # mode = drwxr-xr-x
        self.st_mode |= stat.S_IFREG

    @property
    def filename(self):
        return self.name + '.doku'

    @property
    def text(self):
        if self._text is None:
            self._refresh_text()
        return self._text

    def _refresh_text(self):
        self._text = self.ops.dw.pages.get(self.name)

    @property
    def bytes(self):
        return self.text.encode('utf8')


class WikiDir(WikiEntry):
    _children = None

    def __init__(self, name, *args, **kwargs):
        print('Creating a directory called: ' + name)
        self.name = name
        super().__init__(*args, **kwargs)
        # mode = drwxr-xr-x
        self.st_mode |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH | \
            stat.S_IFDIR

        self.modified = time.time()

    @property
    def children(self):
        if self._children is None:
            self._refresh_children()
        return self._children

    def _refresh_children(self):
        print('Refreshing children of ' + str(self))
        pages = self.ops.dw.pages.list(self.path, depth=2)
        self._children = {}
        print('depth = ', self.depth)

        for p in pages:
            path = p['id'].split(':')[self.depth:-1]
            if path:
                dir_name = path[-1]
                print('Checking of directory ' + dir_name + ' already exists')
                if dir_name + '.doku' in self._children:
                    print('already exists')
                    continue

                print('Didn\'t exist yet')
                wiki_entry = WikiDir(dir_name, self.ops, self)

            else:
                wiki_entry = WikiFile(p, self.ops, self)
            print(wiki_entry)
            self._children[wiki_entry.filename] = wiki_entry


class Operations(BaseOperations, UserDict):
    def __init__(self, *args, **kwargs):
        super().__init__()

        self.dw = DokuWiki('https://os3.nl', '', '')

        self.data = {}
        WikiDir('', self, None, inode=ROOT_INODE)

    def getattr(self, inode):
        print('trying to find inode: ' + str(inode))
        try:
            entry = self[inode]
            print('found it: ', entry)
            return entry
        except KeyError:
            print('Didn\'t find it :(')
            raise FUSEError(errno.ENOENT)

    def lookup(self, parent_inode, name):
        print('lookup')
        name = fsdecode(name)
        print(name)
        if name == '.':
            inode = parent_inode
        elif name == '..':
            inode = ROOT_INODE
        elif name.startswith('.'):
            raise FUSEError(errno.ENOENT)
        else:
            parent = self[parent_inode]
            try:
                inode = parent.children[name].inode
                print('found')
            except:
                print('not found')
                raise FUSEError(errno.ENOENT)

        return self.getattr(inode)

    def access(self, inode, mode, ctx):
        print('access')
        print(inode)
        return True

    def opendir(self, inode):
        print('opendir')
        print(inode)
        return inode

    def readdir(self, inode, off):
        print('readdir', inode, off)
        # pages = self.dw.pages.list(depth=1)
        # print(pages)
        wiki_dir = self[inode]
        print(wiki_dir)
        wiki_dir.children
        special_entries = [(fsencode('.'), self.getattr(inode), inode)]
        entries = [c.to_readdir_format() for c in wiki_dir.children.values()]
        entries += special_entries
        entries = sorted(entries)
        entries = entries[off:]
        return entries

    def open(self, inode, flags):
        print('open')
        print(inode)
        # TODO: Keep track of amount of times open
        return inode

    def read(self, inode, offset, length):
        print('read')
        print(inode, offset, length)
        return self[inode].bytes[offset: offset + length]


if __name__ == '__main__':

    try:
        llfuse.init(Operations(), 'wiki', [])
    except:
        llfuse.close()
        raise

    try:
        llfuse.main(single=True)
    except:
        llfuse.close()
        raise
    llfuse.close()
