Overview
========

The Android Debug interface (ADB) is really useful for lots of things. However,
it typically has to be enabled by the user, and each computer it will be used
with needs to be authenticated by its public key and authorized for access to
the device. Most of the time this isn’t a problem; however, if you need ADB in
early boot (e.g. before or during the password entry screen for encrypted
storage), there’s no way to turn ADB on via the UI, nor does the UI for
authorizing a computer work yet. In this scenario, a different method is
needed. This tool implements one of the two parts of this method (the other is
fairly easy to do by hand via a shell in a recovery).

The two steps needed are:
* ADB needs to be enabled during early boot (this is easy to do from the
  recovery), and
* the computer’s key needs to be authorized for access (this is the part that
  this tool does).

The first step, enabling ADB during early boot, simply requires editing the
`build.prop` file on the `/system` partition. This can be done by mounting
`/system` read-write and modifying the file directly (it is a text file and
therefore easy to edit using a variety of tools).

The second step, however, requires that the key be placed somewhere where the
ADB authentication infrastructure will find it. By default there are two such
places, `/adb_keys` and `/data/misc/adb/adb_keys`. During early boot, the
second is not an option because, prior to entering a decryption password,
`/data` is not mounted; therefore, `/adb_keys` is the only option. However, the
root directory is populated from the initramfs packed in `boot.img`, which is
not easy to modify from a recovery environment. This tool modifies `boot.img`
to add `/adb_keys` to the initramfs.


How to use it
=============

1. Make sure you have the ability to modify `/system`. This might be via an
   appropriate recovery, such as TWRP.
2. Obtain an OS image ZIP file that you want to install. This file must contain
   a `/boot.img` among other things.
3. Run the `adb-keys-initramfs` tool. It creates a new ZIP file which is
   identical to the original except that `boot.img` has been modified to embed
   the ADB keys in the initramfs.
4. Use the recovery to install the patched ZIP file.
5. With `/system` mounted read-write, add the following three lines to the end
   of `/system/build.prop`:
```
persist.service.adb.enable=1
persist.service.debuggable=1
persist.sys.usb.config=mtp,adb
```
6. Reboot and enjoy your new ADB access during early boot!
