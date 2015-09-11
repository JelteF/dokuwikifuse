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


try:
    from config import Config
except:
    from default_config import DefaultConfig as Config

from pprint import pprint  # noqa


class WikiEntry(EntryAttributes):
    _prints = ('inode', 'path')

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
        if parent:
            parent._children[self.filename] = self

        self.st_uid = os.getuid()
        self.st_gid = os.getgid()

        # mode = -rw-r--r--
        self.st_mode = stat.S_IRUSR | stat.S_IWUSR | \
            stat.S_IRGRP | stat.S_IROTH

        self.ops = ops
        self.ops[self.inode] = self

    def __repr__(self):
        string = '<%s(' % self.__class__.__name__
        print(self._prints)
        for i, attr in enumerate(self._prints):
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
    def path(self):
        return '/'.join(self.parents + [self.filename])

    @property
    def parents(self):
        if self.inode == ROOT_INODE or self.parent.inode == ROOT_INODE:
            return ['']
        return self.parent.parents + [self.parent.filename]

    def update_modified(self):
        self.modified = time.time()


class WikiFile(WikiEntry):
    _text = None
    _prints = WikiEntry._prints + ('pagename',)

    def __init__(self, name, *args, **kwargs):
        print('Creating a file called: ' + name)
        self.name = name
        super().__init__(*args, **kwargs)
        self.update_modified()
        self.st_size = 0

        self.st_mode |= stat.S_IFREG

    @classmethod
    def from_wiki_data(cls, wiki_data, *args, **kwargs):
        self = cls(wiki_data['id'], *args, **kwargs)

        self.modified = wiki_data['mtime']

        self.st_size = wiki_data['size']
        return self

    @property
    def filename(self):
        return self.name + '.doku'

    @property
    def text(self):
        if self._text is None:
            self._refresh_text()
        return self._text

    def _refresh_text(self):
        self._text = self.ops.dw.pages.get(self.pagename)

    @text.setter
    def text(self, value):
        self._text = value

    @property
    def bytes(self):
        return self.text.encode('utf8')

    @bytes.setter
    def bytes(self, value):
        print('setting bytes')
        print(value)
        self.text = value.decode('utf8')
        self.st_size = len(value)

    @property
    def pagename(self):
        return ':'.join(self.parents + [self.name])

    def save(self):
        self.ops.dw.pages.set(self.pagename, self.text)

    def delete(self):
        if len(self.text):
            # Don't delete files that are already empty, since a removed page
            # is just an empty page in dokuwiki
            self.ops.dw.pages.delete(self.pagename)
        del self.parent._children[self.filename]



class WikiDir(WikiEntry):
    _children = None

    def __init__(self, name, *args, **kwargs):
        print('Creating a directory called: ' + name)
        self.name = name
        super().__init__(*args, **kwargs)
        # mode = drwxr-xr-x
        self.st_mode |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH | \
            stat.S_IFDIR

        self.update_modified()

    @property
    def children(self):
        if self._children is None:
            self._refresh_children()
        return self._children

    def _refresh_children(self):
        print('Refreshing children of ' + str(self))
        pages = self.ops.dw.pages.list(self.path, depth=self.depth + 2)
        self._children = {}
        print('depth = ', self.depth)

        for p in pages:
            path = p['id'].split(':')[self.depth:]
            if len(path) > 1:
                dir_name = path[0]
                print('Checking of directory ' + dir_name + ' already exists')
                if dir_name + '.doku' in self._children:
                    print('already exists')
                    continue

                print('Didn\'t exist yet')
                wiki_entry = WikiDir(dir_name, self.ops, self)

            else:
                p['id'] = path[-1]
                wiki_entry = WikiFile.from_wiki_data(p, self.ops, self)


class Operations(BaseOperations, UserDict):
    def __init__(self, *args, **kwargs):
        super().__init__()

        self.dw = DokuWiki(Config.url, Config.user, Config.password)

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

    def setattr(self, inode, attrs):
        entry = self.getattr(inode)
        print(attrs.st_size)
        if attrs.st_size is not None:
            if entry.st_size < attrs.st_size:
                entry.bytes = + b'\0' * (attrs.st_size - entry.st_size)
            else:
                entry.bytes = entry.bytes[:attrs.st_size]

        return entry

    def lookup(self, parent_inode, name):
        print('lookup')
        name = fsdecode(name)
        print(name, self[parent_inode])
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
            except KeyError:
                print('not found')
                raise FUSEError(errno.ENOENT)

        return self.getattr(inode)

    def access(self, inode, mode, ctx):
        print('access', self[inode])
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

    def open(self, inode, mode):
        print('open', self[inode], stat.filemode(mode), mode)
        # TODO: Keep track of amount of times open
        print(inode)
        return inode

    def read(self, inode, offset, length):
        print('read')
        print(inode, offset, length)
        return self[inode].bytes[offset: offset + length]

    def write(self, inode, offset, buf):
        file = self[inode]
        print('write', file)
        original = file.bytes
        new = original[:offset] + buf + original[offset + len(buf):]
        file.bytes = new
        file.update_modified()
        file.save()
        return len(buf)

    def create(self, parent_inode, name, mode, flags, ctx):
        print('create')
        parent = self[parent_inode]
        # TODO: Add lots of checks here
        name = fsdecode(name)
        if not name.endswith('.doku'):
            # Raise read only filesystem error when writing non doku files
            raise FUSEError(errno.EROFS)
        elif name in parent.children:
            raise FUSEError(errno.EEXIST)

        name = name[:-5]  # Remove .doku extension from filename
        entry = WikiFile(name, self, parent)

        return (entry.inode, entry)

    def unlink(self, parent_inode, name):
        '''File removal'''
        print('unlink')
        name = fsdecode(name)
        parent = self[parent_inode]

        entry = parent.children[name]
        entry.delete()

'''
    def release(self, inode):
        print('release')
        pass

    def releasedir(self, inode):
        print('releasedir')
        pass

    def rmdir(self, inode):
        print('rmdir')
        pass

    def forget(self, *args, **kwargs):
        print('forget')
        pass

    def rename(self, *args, **kwargs):
        print('rename')
        pass

    def rename(self, *args, **kwargs):
        print('rename')
        pass

    def rename(self, *args, **kwargs):
        print('rename')
        pass

    def destroy(self, *args, **kwargs):
        print('destroy')
        pass

    def link(self, *args, **kwargs):
        print('link')
        pass

    def mkdir(self, *args, **kwargs):
        print('mkdir')
        pass

    def mknod(self, *args, **kwargs):
        print('mknod')
        pass

    def readlink(self, *args, **kwargs):
        print('readlink')
        pass

    def removexattr(self, *args, **kwargs):
        print('removexattr')
        pass

    def getexttr(self, *args, **kwargs):
        print('getexattr')
        pass

    def fsync(self, *args, **kwargs):
        print('fsync')
        pass

    def fsyncdir(self, *args, **kwargs):
        print('fsyncdir')
        pass

    def listxattr(self, *args, **kwargs):
        print('listxattr')
        pass

    def setxattr(self, *args, **kwargs):
        print('setxattr')
        pass

    def statfs(self, *args, **kwargs):
        print('statfs')
        pass

    def symlink(self, *args, **kwargs):
        print('symlink')
        pass
'''


if __name__ == '__main__':
    try:
        llfuse.init(Operations(), Config.mountpoint, ['nonempty',
                                                      'fsname=tmpfs'])
    except:
        llfuse.close()
        raise

    try:
        llfuse.main(single=True)
    except:
        llfuse.close()
        raise
    llfuse.close()
