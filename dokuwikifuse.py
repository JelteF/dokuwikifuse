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
import logging
import argparse
import http.client

from pprint import pprint  # noqa

try:
    from config import Config
except:
    from default_config import DefaultConfig as Config

parser = argparse.ArgumentParser(description='A CLI utility to mount dokuwiki'
                                 ' as a filesystem')

parser.add_argument('--url', help='url of the host running dokuwiki')
parser.add_argument('--user', '-u', help='user used to log in')
parser.add_argument('--password', '-p', help='password for the user')
parser.add_argument('--mountpoint', help='mountpoint for the filesystem')
parser.add_argument('--chroot', help='directory to chroot into')
parser.add_argument('--log', default='INFO', help='loglevel')
args = vars(parser.parse_args())

loglevel = getattr(logging, args['log'].upper(), None)

if not isinstance(loglevel, int):
    raise ValueError('Invalid log level: %s' % args['log'])

logging.basicConfig(level=loglevel, format='[%(levelname)s] %(message)s')

del args['log']

for key, val in args.items():
    if val is not None:
        setattr(Config, key, val)

if not Config.chroot.endswith('/'):
    Config.chroot += '/'


class WikiEntry(EntryAttributes):
    _prints = ('inode', 'path')

    def __init__(self, ops, parent, *, inode=None):
        super().__init__()

        if inode is None:
            inode = uuid4().int & (1 << 32)-1
            while inode in ops:
                inode = uuid4().int & (1 << 32)-1

        self.inode = inode

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
        return self.st_mtime_ns

    @modified.setter
    def modified(self, value):
        value *= 10**9
        self.st_atime_ns = value
        self.st_ctime_ns = value
        self.st_mtime_ns = value

    @property
    def depth(self):
        if self.inode == ROOT_INODE:
            return len(Config.chroot.split('/')) - 2
        return self.parent.depth + 1

    @property
    def path(self):
        return '/'.join(self.parents + [self.filename])

    @property
    def parents(self):
        if self.inode == ROOT_INODE or self.parent.inode == ROOT_INODE:
            # Ignore the last empty string when splitting
            return Config.chroot.split('/')[:-1]
        return self.parent.parents + [self.parent.filename]

    def update_modified(self):
        self.modified = time.time()


class WikiFile(WikiEntry):
    _text = None
    _prints = WikiEntry._prints + ('pagename',)

    def __init__(self, name, *args, **kwargs):
        logging.info('Creating a dokuwiki file called: %s.doku' % name)
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
            try:
                self._refresh_text()
            except http.client.BadStatusLine as e:
                logging.warning('Trying again because, requesting %s '
                                'failed with: %s', self.name, e)
                raise FUSEError(errno.EAGAIN)
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
        logging.debug('setting bytes')
        logging.debug(value)
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

class WikiAttachment(WikiEntry):
    _bytes = b''

    def __init__(self, name, *args, **kwargs):
        logging.info('Creating an attachment file called: %s' % name)
        # TODO: Add check that file has no .doku extension
        self.name = name
        super().__init__(*args, **kwargs)
        self.update_modified()
        self.st_size = 0

        self.st_mode |= stat.S_IFREG

    @classmethod
    def from_wiki_data(cls, wiki_data, *args, **kwargs):
        self = cls(wiki_data['file'], *args, **kwargs)
        # To make sure they are refreshed when read the first time
        self._bytes = None

        self.modified = wiki_data['mtime']

        self.st_size = wiki_data['size']
        return self


    @property
    def bytes(self):
        if self._bytes is None:
            try:
                self._refresh_bytes()
            except http.client.BadStatusLine as e:
                logging.warning('Trying again because, requesting %s '
                                'failed with: %s', self.name, e)
                raise FUSEError(errno.EAGAIN)
        return self._bytes

    def _refresh_bytes(self):
        self._bytes = self.ops.dw.medias.get(self.doku_path)

    @bytes.setter
    def bytes(self, value):
        self._bytes = value

    @property
    def doku_path(self):
        return ':'.join(self.parents + [self.name])

    def save(self):
        self.ops.dw.medias.set(self.doku_path, self.bytes, overwrite=True)

    def delete(self):
        self.ops.dw.medias.delete(self.doku_path)



class WikiDir(WikiEntry):
    _children = None

    def __init__(self, name, *args, **kwargs):
        logging.info('Creating a directory called: ' + name)
        self.name = name
        super().__init__(*args, **kwargs)
        # mode = drwxr-xr-x
        self.st_mode |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH | \
            stat.S_IFDIR

        self.update_modified()

    @property
    def children(self):
        if self._children is None:
            try:
                self._refresh_children()
            except http.client.BadStatusLine as e:
                logging.warning('Trying again because, requesting children of '
                                '%s failed with: %s', self.name, e)
                raise FUSEError(errno.EAGAIN)
        return self._children

    def _refresh_children(self):
        pages = self.ops.dw.pages.list(self.path, depth=self.depth + 2)
        attachments = self.ops.dw.medias.list(self.path, depth=self.depth + 2)

        self._children = {}

        for p in pages:
            path = p['id'].split(':')[self.depth:]
            if len(path) > 1:
                dir_name = path[0]
                if dir_name in self._children:
                    continue

                WikiDir(dir_name, self.ops, self)

            else:
                p['id'] = path[-1]
                WikiFile.from_wiki_data(p, self.ops, self)

        for a in attachments:
            path = a['id'].split(':')[self.depth:]
            if len(path) > 1:
                dir_name = path[0]
                if dir_name in self._children:
                    continue

                WikiDir(dir_name, self.ops, self)
            else:
                WikiAttachment.from_wiki_data(a, self.ops, self)


class Operations(BaseOperations, UserDict):
    def __init__(self, *args, **kwargs):
        super().__init__()

        self.dw = DokuWiki(Config.url, Config.user, Config.password)

        self.data = {}
        WikiDir('', self, None, inode=ROOT_INODE)

    def getattr(self, inode, ctx=None):
        logging.debug('getattr %s', inode)
        try:
            logging.debug('found')
            entry = self[inode]
            return entry
        except KeyError:
            logging.debug('not found')
            raise FUSEError(errno.ENOENT)

    def setattr(self, inode, attr, fields, fh, ctx=None):
        logging.debug('setattr %s %s %s', inode, attr, fields)
        entry = self.getattr(inode)
        if fields.update_size:
            if entry.st_size < attr.st_size:
                entry.bytes = + b'\0' * (attr.st_size - entry.st_size)
            else:
                entry.bytes = entry.bytes[:attr.st_size]

        return entry

    def lookup(self, parent_inode, name, ctx=None):
        logging.debug('lookup %s', name)
        name = fsdecode(name)
        if name == '.':
            inode = parent_inode
        elif name == '..':
            inode = ROOT_INODE
        elif name.startswith('.'):
            logging.debug('not found')
            raise FUSEError(errno.ENOENT)
        else:
            parent = self[parent_inode]
            try:
                inode = parent.children[name].inode
            except KeyError:
                logging.debug('not found')
                raise FUSEError(errno.ENOENT)

        return self.getattr(inode)

    def access(self, inode, mode, ctx=None):
        logging.debug('access %s', self[inode])
        return True

    def opendir(self, inode, ctx=None):
        logging.debug('opendir %s', inode)
        return inode

    def readdir(self, inode, off):
        logging.debug('readdir %s %s', inode, off)
        # pages = self.dw.pages.list(depth=1)
        # print(pages)
        wiki_dir = self[inode]
        wiki_dir.children
        special_entries = [(fsencode('.'), self.getattr(inode), inode)]
        entries = [c.to_readdir_format() for c in wiki_dir.children.values()]
        entries += special_entries
        entries = sorted(entries)
        entries = entries[off:]
        return entries

    def open(self, inode, mode, ctx=None):
        logging.debug('open %s %s %s', self[inode], stat.filemode(mode), mode)
        # TODO: Keep track of amount of times open
        return inode

    def read(self, inode, offset, length):
        logging.debug('read %s %s %s', inode, offset, length)
        return self[inode].bytes[offset: offset + length]

    def write(self, inode, offset, buf):
        logging.debug('write')
        file = self[inode]
        logging.info('Writing %s to wiki', file.name)
        original = file.bytes
        new = original[:offset] + buf + original[offset + len(buf):]
        file.bytes = new
        file.update_modified()
        file.save()
        return len(buf)

    def create(self, parent_inode, name, mode, flags, ctx=None):
        logging.debug('create %s %s', parent_inode, name)
        parent = self[parent_inode]
        # TODO: Add lots of checks here
        name = fsdecode(name)
        if name in parent.children:
            raise FUSEError(errno.EEXIST)

        if name.endswith('.doku'):
            name = name[:-5]  # Remove .doku extension from filename
            entry = WikiFile(name, self, parent)
        elif '.' not in name or name.endswith('~') or name.startswith('.'):
            # Raise read only filesystem error when writing files without an
            # extension and other temporary files
            # TODO: make the filesystem writethrough for these files
            logging.info('File called %s was not created', name)
            raise FUSEError(errno.EROFS)
        else:
            entry = WikiAttachment(name, self, parent)


        return (entry.inode, entry)

    def unlink(self, parent_inode, name, ctx=None):
        '''File removal'''
        logging.debug('unlink %s', name)
        name = fsdecode(name)
        parent = self[parent_inode]

        entry = parent.children[name]
        logging.info('Deleting %s from wiki', name)
        entry.delete()

    def mkdir(self, parent_inode, name, mode, ctx):
        logging.debug('mkdir %s', name)
        return WikiDir(name.decode(), self, self[parent_inode])

'''
    def release(self, inode):
        logging.debug('release')
        pass

    def releasedir(self, inode):
        logging.debug('releasedir')
        pass

    def rmdir(self, inode):
        logging.debug('rmdir')
        pass

    def forget(self, *args, **kwargs):
        logging.debug('forget')
        pass

    def rename(self, *args, **kwargs):
        logging.debug('rename')
        pass

    def rename(self, *args, **kwargs):
        logging.debug('rename')
        pass

    def rename(self, *args, **kwargs):
        logging.debug('rename')
        pass

    def destroy(self, *args, **kwargs):
        logging.debug('destroy')
        pass

    def link(self, *args, **kwargs):
        logging.debug('link')
        pass

    def mknod(self, *args, **kwargs):
        logging.debug('mknod')
        pass

    def readlink(self, *args, **kwargs):
        logging.debug('readlink')
        pass

    def removexattr(self, *args, **kwargs):
        logging.debug('removexattr')
        pass

    def getexttr(self, *args, **kwargs):
        logging.debug('getexattr')
        pass

    def fsync(self, *args, **kwargs):
        logging.debug('fsync')
        pass

    def fsyncdir(self, *args, **kwargs):
        logging.debug('fsyncdir')
        pass

    def listxattr(self, *args, **kwargs):
        logging.debug('listxattr')
        pass

    def setxattr(self, *args, **kwargs):
        logging.debug('setxattr')
        pass

    def statfs(self, *args, **kwargs):
        logging.debug('statfs')
        pass

    def symlink(self, *args, **kwargs):
        logging.debug('symlink')
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
        llfuse.main(workers=1)
    except:
        llfuse.close()
        raise
    llfuse.close()
