"""passlib.utils.h64 - hash64 encoding helpers"""
#=================================================================================
#imports
#=================================================================================
#core
from cStringIO import StringIO
import logging; log = logging.getLogger(__name__)
#site
#pkg
#local
__all__ = [
    "CHARS",

    "decode_bytes",                "encode_bytes",
    "decode_transposed_bytes",     "encode_transposed_bytes",

    "decode_int6",  "encode_int6",
    "decode_int12", "encode_int12"
    "decode_int18", "encode_int18"
    "decode_int24", "encode_int24",
    "decode_int64", "encode_int64",
    "decode_int",   "encode_int",
]

#=================================================================================
#6 bit value <-> char mapping, and other internal helpers
#=================================================================================
CHARS = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

#base64 char sequence
encode_6bit = CHARS.__getitem__ # int -> char

#inverse map (char->value)
_CHARIDX = dict( (c,i) for i,c in enumerate(CHARS))
decode_6bit = _CHARIDX.__getitem__ # char -> int

_sjoin = "".join

try:
    _bjoin = bytes().join
except NameError:
    _bjoin = _sjoin

#=================================================================================
#encode offsets from buffer - used by md5_crypt, sha_crypt, et al
#=================================================================================

def encode_bytes(source):
    "encode byte string to h64 format"
    #FIXME: do something much more efficient here.
    # can't quite just use base64 and then translate chars,
    # since this scheme is little-endian.
    out = StringIO()
    write = out.write
    end = len(source)
    tail = end % 3
    end -= tail
    idx = 0
    while idx < end:
        v1 = ord(source[idx])
        v2 = ord(source[idx+1])
        v3 = ord(source[idx+2])
        write(encode_int24(v1 + (v2<<8) + (v3<<16)))
        idx += 3
    if tail:
        v1 = ord(source[idx])
        if tail == 1:
            #NOTE: 4 msb of int are always 0
            write(encode_int12(v1))
        else:
            #NOTE: 2 msb of int are always 0
            v2 = ord(source[idx+1])
            write(encode_int18(v1 + (v2<<8)))
    return out.getvalue()

def decode_bytes(source):
    "decode h64 format into byte string"
    out = StringIO()
    write = out.write
    end = len(source)
    tail = end % 4
    if tail == 1:
        #only 6 bits left, can't encode a whole byte!
        raise ValueError, "input string length cannot be == 1 mod 4"
    end -= tail
    idx = 0
    while idx < end:
        v = decode_int24(source[idx:idx+4])
        write(chr(v&0xff) + chr((v>>8)&0xff) + chr(v>>16))
        idx += 4
    if tail:
        if tail == 2:
            #NOTE: 2 msb of int are ignored (should be 0)
            v = decode_int12(source[idx:idx+2])
            write(chr(v&0xff))
        else:
            #NOTE: 4 msb of int are ignored (should be 0)
            v = decode_int18(source[idx:idx+3])
            write(chr(v&0xff) + chr((v>>8)&0xff))
    return out.getvalue()

def encode_transposed_bytes(source, offsets):
    "encode byte string to h64 format, using offset list to transpose elements"
    #XXX: could make this a dup of encode_bytes(), which directly accesses source[offsets[idx]],
    # but speed isn't *that* critical for this function
    tmp = _bjoin(source[off] for off in offsets)
    return encode_bytes(tmp)

def decode_transposed_bytes(source, offsets):
    "decode h64 format into byte string, then undoing specified transposition; inverse of :func:`encode_transposed_bytes`"
    #NOTE: if transposition does not use all bytes of source, original can't be recovered
    tmp = decode_bytes(source)
    buf = [None] * len(offsets)
    for off, char in zip(offsets, tmp):
        buf[off] = char
    return _bjoin(buf)

#=================================================================================
# int <-> b64 string, used by des_crypt, ext_des_crypt
#=================================================================================

def encode_int6(value):
    "encode 6 bit integer to single char of hash-64 format"
    return encode_6bit(value)

def decode_int6(value):
    "decode 1 char of hash-64 format, returning 6-bit integer"
    return decode_6bit(value)

#---------------------------------------------------------------------

def decode_int12(value):
    "decode 2 chars of hash-64 format used by crypt, returning 12-bit integer"
    #NOTE: this is optimized form of decode_int(value) for 4 chars
    try:
        return (decode_6bit(value[1])<<6)+decode_6bit(value[0])
    except KeyError:
        raise ValueError, "invalid character"

def encode_int12(value):
    "encode 2 chars of hash-64 format from a 12-bit integer"
    #NOTE: this is optimized form of encode_int(value,2)
    return  encode_6bit(value & 0x3f) + encode_6bit((value>>6) & 0x3f)

#---------------------------------------------------------------------
def decode_int18(value):
    "decode 3 chars of hash-64 format, returning 18-bit integer"
    #NOTE: this is optimized form of decode_int(value) for 3 chars
    return (
        decode_6bit(value[0]) +
        (decode_6bit(value[1])<<6) +
        (decode_6bit(value[2])<<12)
        )

def encode_int18(value):
    "encode 18-bit integer into 3 chars of hash-64 format"
    #NOTE: this is optimized form of encode_int(value,3)
    return (
        encode_6bit(value & 0x3f) +
        encode_6bit((value>>6) & 0x3f) +
        encode_6bit((value>>12) & 0x3f)
        )

#---------------------------------------------------------------------

def decode_int24(value):
    "decode 4 chars of hash-64 format in little-endian order, returning 24-bit integer"
    #NOTE: this is optimized form of decode_int(value) for 4 chars
    try:
        return  decode_6bit(value[0]) +\
                (decode_6bit(value[1])<<6)+\
                (decode_6bit(value[2])<<12)+\
                (decode_6bit(value[3])<<18)
    except KeyError:
        raise ValueError, "invalid character"

def encode_int24(value):
    "encode 4 chars of hash-64 format in little-endian order, from a 24-bit integer"
    #NOTE: this is optimized form of encode_int(value,4)
    return  encode_6bit(value & 0x3f) + \
            encode_6bit((value>>6) & 0x3f) + \
            encode_6bit((value>>12) & 0x3f) + \
            encode_6bit((value>>18) & 0x3f)

#---------------------------------------------------------------------

def decode_int64(value):
    "decodes 11 char hash64 string -> 64-bit integer (little-endian order; 2 msb assumed to be padding)"
    return decode_int(value)

def encode_int64(value):
    "encodes 64-bit integer -> 11 char hash64 string (little-endian order; 2 msb of 0's added as padding)"
    return encode_int(value, 11)

def decode_dc_int64(value):
    """decode 11 char hash64 string -> 64-bit integer (big-endian order; 2 lsb assumed to be padding)

    this format is used primarily by des-crypt & variants to encode the DES output value
    used as a checksum.
    """
    return decode_int(value, 11, True)>>2

def encode_dc_int64(value):
    """encode 64-bit integer -> 11 char hash64 string (big-endian order; 2 lsb added as padding)

    this format is used primarily by des-crypt & variants to encode the DES output value
    used as a checksum.
    """
    #NOTE: insert 2 padding bits as lsb, to make 66 bits total
    return encode_int(value<<2,11,True)

#---------------------------------------------------------------------

def decode_int(source, big=False):
    """decode hash64 string -> integer

    :arg source: hash64 string of any length
    :arg big: if ``True``, big-endian encoding is used instead of little-endian (the default).

    :raises ValueError: if the string contains invalid hash64 characters.

    :returns:
        a integer whose value is in ``range(0,2**(6*len(source)))``
    """
    #FORMAT: little-endian, each char contributes 6 bits,
    # char value = index in H64_CHARS string
    if not big:
        source = reversed(source)
    try:
        out = 0
        for c in source:
                out = (out<<6) + decode_6bit(c)
        return out
    except KeyError:
        raise ValueError, "invalid character in string"

def encode_int(value, count, big=False):
    """encode integer into hash-64 format

    :arg value: non-negative integer to encode
    :arg count: number of output characters / 6 bit chunks to encode
    :arg big: if ``True``, big-endian encoding is used instead of little-endian (the default).

    :returns:
        a hash64 string of length ``count``.
    """
    if big:
        itr = xrange(6*count-6, -6, -6)
    else:
        itr = xrange(0, 6*count, 6)
    return _sjoin(
        encode_6bit((value>>off) & 0x3f)
        for off in itr
    )

#=================================================================================
#eof
#=================================================================================
