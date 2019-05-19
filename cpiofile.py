"""
Permits access to CPIO archives.
"""

import io
import struct


_ENTRY_HEADER = struct.Struct("<6s8s8s8s8s8s8s8s8s8s8s8s8s8s")


class BadCPIOFile(Exception):
    """
    Raised if a malformed CPIO is encountered.
    """


class CPIOFile:
    """
    A CPIO archive.

    Only the new ASCII format is supported.
    """

    __slots__ = ("_fp", "_writeable", "_writer_active")

    def __init__(self, fp, mode="r"):
        """
        Open a CPIO archive.

        fp -- a seekable, readable, and (if mode="w") writeable filelike object
            containing the CPIO archive
        mode -- one of "r" or "w", indicating whether writing is to take place
        """
        # Sanity check.
        if mode not in ("r", "w"):
            raise ValueError(f"Unknown mode {mode}.")

        # Populate variables.
        self._fp = fp
        self._writeable = mode == "w"
        self._writer_active = False

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def infolist(self):
        """
        Return an iterable of all entries in the archive, as CPIOInfo objects.
        """
        # There is no directory or anything like that, so just scan the entire
        # archive.
        self._fp.seek(0)
        while True:
            info = CPIOInfo._from_file(self._fp)
            if info.name == "TRAILER!!!":
                break
            yield info
            self._fp.seek(info._offset_after, io.SEEK_SET)

    def open(self, info, mode="r"):
        """
        Open a filelike object for reading or writing data to a CPIO member.

        When writing, the member must not already exist.

        info -- the member to access
        mode -- "r" to read the member, or "w" to write it
        """
        if mode == "r":
            return _ReadableMember(self._fp, info)
        elif mode == "w":
            if self._writeable:
                return _WriteableMember(self, info)
            else:
                raise ValueError("CPIO is open read-only.")
        else:
            raise ValueError(f"Unknown mode {mode}.")

    def close(self):
        """
        Close the CPIO.

        In the event of a writeable CPIO, the trailer is appended.
        """
        if self._writeable:
            if self._writer_active:
                raise ValueError("Cannot close CPIO until member writer has been closed.")
            with self.open(CPIOInfo(0, 0, 0o755, 0, 0, 1, 0, 0, 0, 0, 0, 0, "TRAILER!!!"), "w"):
                pass


class _ReadableMember(io.BufferedIOBase):
    __slots__ = ("_fp", "_start", "_length", "_pos")

    def __init__(self, fp, info):
        self._fp = fp
        self._start = info._offset_data
        self._length = info.filesize
        self._pos = 0

    def readable(self):
        return True

    def read(self, n=-1):
        return self._read(n, self._fp.read)

    def read1(self, n=-1):
        return self._read(n, self._fp.read1)

    def _read(self, n, fn):
        if n < 0 or n > (self._length - self._pos):
            n = self._length - self._pos
        self._fp.seek(self._start + self._pos, io.SEEK_SET)
        ret = fn(n)
        self._pos += len(ret)
        return ret


class _WriteableMember(io.BufferedIOBase):
    __slots__ = ("_archive", "_expected_length", "_actual_length", "_closed")

    def __init__(self, archive, info):
        if archive._writer_active:
            raise ValueError("Cannot open two CPIO member writers at the same time.")
        archive._writer_active = True
        self._archive = archive
        self._expected_length = info.filesize
        self._actual_length = 0
        self._closed = False
        self._archive._fp.seek(0, io.SEEK_END)
        self._archive._fp.write(info.encode())

    def writeable(self):
        return True

    def write(self, data):
        self._archive._fp.seek(0, io.SEEK_END)
        self._archive._fp.write(data)
        self._actual_length += len(data)

    def close(self):
        if self._closed:
            return
        if self._actual_length != self._expected_length:
            raise ValueError(f"Writer wrote {self._actual_length} bytes but info specified {self._expected_length} bytes.")
        padding = B"\x00" * ((4 - (self._actual_length % 4)) % 4)
        self._archive._fp.seek(0, io.SEEK_END)
        self._archive._fp.write(padding)
        self._closed = True
        self._archive._writer_active = False



class CPIOInfo:
    """
    Information about a single entry in a CPIO.
    """

    __slots__ = ("_offset", "ino", "mode", "uid", "gid", "nlink", "mtime", "filesize", "devmajor", "devminor", "rdevmajor", "rdevminor", "_name")

    def __init__(self, offset, ino, mode, uid, gid, nlink, mtime, filesize, devmajor, devminor, rdevmajor, rdevminor, name):
        """
        Create a CPIOInfo.

        offset -- the position in the CPIO at which the file header begins
        ino -- the inode number
        mode -- the file mode
        uid -- the owner’s user ID
        gid -- the owning group ID
        nlink -- the number of links to the file
        mtime -- the last-modified time
        filesize -- the size of the file, in bytes
        devmajor -- the major device number of the disk originally containing
            the file
        devminor -- the minor device number of the disk originally containing
            the file
        rdevmajor -- the major device number of the file (if a device)
        rdevminor -- the minor device number of the file (if a device)
        name -- the name of the file
        """
        self._offset = offset
        self.ino = ino
        self.mode = mode
        self.uid = uid
        self.gid = gid
        self.nlink = nlink
        self.mtime = mtime
        self.filesize = filesize
        self.devmajor = devmajor
        self.devminor = devminor
        self.rdevmajor = rdevmajor
        self.rdevminor = rdevminor
        self._name = name.encode()

    @staticmethod
    def _from_file(fp):
        """
        Read the next entry from the archive.

        fp -- the archive to read from
        """
        # Read and unpack the header.
        offset = fp.tell()
        header = fp.read(_ENTRY_HEADER.size)
        if len(header) != _ENTRY_HEADER.size:
            raise BadCPIOFile("CPIO truncated.")
        magic, ino, mode, uid, gid, nlink, mtime, filesize, devmajor, devminor, rdevmajor, rdevminor, namesize, _ = _ENTRY_HEADER.unpack(header)

        # Sanity check the magic number.
        if magic != B"070701":
            raise BadCPIOFile(f"Bad magic or not a new-ASCII CPIO, got magic {magic}, expected 070701.")

        # Decode the hex fields.
        try:
            ino = int(ino, 16)
            mode = int(mode, 16)
            uid = int(uid, 16)
            gid = int(gid, 16)
            nlink = int(nlink, 16)
            mtime = int(mtime, 16)
            filesize = int(filesize, 16)
            devmajor = int(devmajor, 16)
            devminor = int(devminor, 16)
            rdevmajor = int(rdevmajor, 16)
            rdevminor = int(rdevminor, 16)
            namesize = int(namesize, 16)
        except ValueError:
            raise BadCPIOFile("CPIO header contains non-hex-encoded integer.")

        # Sanity check.
        if namesize == 0:
            raise BadCPIOFile("CPIO entry with zero-length filename.")

        # Read the filename, which appears immediately after the header.
        name = fp.read(namesize)
        if len(name) != namesize:
            raise BadCPIOFile("CPIO truncated.")
        if name[-1] != 0:
            raise BadCPIOFile(f"CPIO entry with non-NUL-terminated filename {name!r}.")
        name = name[:-1].decode()

        # Return the object.
        return CPIOInfo(offset, ino, mode, uid, gid, nlink, mtime, filesize, devmajor, devminor, rdevmajor, rdevminor, name)

    @property
    def _offset_data(self):
        """
        The byte position in the CPIO at which the entry’s data begins.
        """
        # Round the header plus name length (including terminating NUL) up to a
        # multiple of 4.
        return self._offset + (_ENTRY_HEADER.size + len(self._name) + 1 + 3) // 4 * 4

    @property
    def _offset_after(self):
        """
        The byte position in the CPIO immediately following the entry.
        """
        # Round the data size up to a multiple of 4.
        return self._offset_data + (self.filesize + 3) // 4 * 4

    @property
    def name(self):
        """
        The name of this entry.
        """
        return self._name.decode()

    def encode(self):
        """
        Return the header, encoded, including filename and padding but not
        including file data.
        """
        values = (self.ino, self.mode, self.uid, self.gid, self.nlink, self.mtime, self.filesize, self.devmajor, self.devminor, self.rdevmajor, self.rdevminor, len(self._name) + 1, 0)
        values = (f"{x:08x}".encode("ASCII") for x in values)
        ret = _ENTRY_HEADER.pack(B"070701", *values)
        ret += self._name + B"\x00"
        ret += B"\x00" * ((4 - (len(ret) % 4)) % 4)
        return ret
