"""passlib.utils -- helpers for writing password hashes"""
#=============================================================================
# imports
#=============================================================================
from passlib.utils.compat import JYTHON
# core
from binascii import b2a_base64, a2b_base64, Error as _BinAsciiError
from base64 import b64encode, b64decode
try:
    from collections.abc import Sequence
    from collections.abc import Iterable
except ImportError:
    # py2 compat
    from collections import Sequence
    from collections import Iterable
from codecs import lookup as _lookup_codec
from functools import update_wrapper
import itertools
import inspect
import logging; log = logging.getLogger(__name__)
import math
import os
import sys
import random
import re
if JYTHON: # pragma: no cover -- runtime detection
    # Jython 2.5.2 lacks stringprep module -
    # see http://bugs.jython.org/issue1758320
    try:
        import stringprep
    except ImportError:
        stringprep = None
        _stringprep_missing_reason = "not present under Jython"
else:
    import stringprep
import time
if stringprep:
    import unicodedata
import timeit
import types
from warnings import warn
# site
# pkg
from passlib.utils.binary import (
    # [remove these aliases in 2.0]
    BASE64_CHARS, AB64_CHARS, HASH64_CHARS, BCRYPT_CHARS,
    Base64Engine, LazyBase64Engine, h64, h64big, bcrypt64,
    ab64_encode, ab64_decode, b64s_encode, b64s_decode
)
from passlib.utils.decor import (
    # [remove these aliases in 2.0]
    deprecated_function,
    deprecated_method,
    memoized_property,
    classproperty,
    hybrid_method,
)
from passlib.exc import ExpectedStringError, ExpectedTypeError
from passlib.utils.compat import (add_doc, join_bytes, join_byte_values,
                                  join_byte_elems, irange, imap, PY3, u,
                                  join_unicode, unicode, byte_elem_value, nextgetter,
                                  unicode_or_str, unicode_or_bytes_types,
                                  get_method_function, suppress_cause)
# local
__all__ = [
    # constants
    'JYTHON',
    'sys_bits',
    'unix_crypt_schemes',
    'rounds_cost_values',

    # unicode helpers
    'consteq',
    'saslprep',

    # bytes helpers
    "xor_bytes",
    "render_bytes",

    # encoding helpers
    'is_same_codec',
    'is_ascii_safe',
    'to_bytes',
    'to_unicode',
    'to_native_str',

    # host OS
    'has_crypt',
    'test_crypt',
    'safe_crypt',
    'tick',

    # randomness
    'rng',
    'getrandbytes',
    'getrandstr',
    'generate_password',

    # object type / interface tests
    'is_crypt_handler',
    'is_crypt_context',
    'has_rounds_info',
    'has_salt_info',
]

#=============================================================================
# constants
#=============================================================================

# bitsize of system architecture (32 or 64)
sys_bits = int(math.log(sys.maxsize if PY3 else sys.maxint, 2) + 1.5)

# list of hashes algs supported by crypt() on at least one OS.
# XXX: move to .registry for passlib 2.0?
unix_crypt_schemes = [
    "sha512_crypt", "sha256_crypt",
    "sha1_crypt", "bcrypt",
    "md5_crypt",
    # "bsd_nthash",
    "bsdi_crypt", "des_crypt",
    ]

# list of rounds_cost constants
rounds_cost_values = [ "linear", "log2" ]

# legacy import, will be removed in 1.8
from passlib.exc import MissingBackendError

# internal helpers
_BEMPTY = b''
_UEMPTY = u("")
_USPACE = u(" ")

# maximum password size which passlib will allow; see exc.PasswordSizeError
MAX_PASSWORD_SIZE = int(os.environ.get("PASSLIB_MAX_PASSWORD_SIZE") or 4096)

#=============================================================================
# type helpers
#=============================================================================

class SequenceMixin(object):
    """
    helper which lets result object act like a fixed-length sequence.
    subclass just needs to provide :meth:`_as_tuple()`.
    """
    def _as_tuple(self):
        raise NotImplementedError("implement in subclass")

    def __repr__(self):
        return repr(self._as_tuple())

    def __getitem__(self, idx):
        return self._as_tuple()[idx]

    def __iter__(self):
        return iter(self._as_tuple())

    def __len__(self):
        return len(self._as_tuple())

    def __eq__(self, other):
        return self._as_tuple() == other

    def __ne__(self, other):
        return not self.__eq__(other)

if PY3:
    # getargspec() is deprecated, use this under py3.
    # even though it's a lot more awkward to get basic info :|

    _VAR_KEYWORD = inspect.Parameter.VAR_KEYWORD
    _VAR_ANY_SET = set([_VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL])

    def accepts_keyword(func, key):
        """test if function accepts specified keyword"""
        params = inspect.signature(get_method_function(func)).parameters
        if not params:
            return False
        arg = params.get(key)
        if arg and arg.kind not in _VAR_ANY_SET:
            return True
        # XXX: annoying what we have to do to determine if VAR_KWDS in use.
        return params[list(params)[-1]].kind == _VAR_KEYWORD

else:

    def accepts_keyword(func, key):
        """test if function accepts specified keyword"""
        spec = inspect.getargspec(get_method_function(func))
        return key in spec.args or spec.keywords is not None

def update_mixin_classes(target, add=None, remove=None, append=False,
                         before=None, after=None, dryrun=False):
    """
    helper to update mixin classes installed in target class.

    :param target:
        target class whose bases will be modified.

    :param add:
        class / classes to install into target's base class list.

    :param remove:
        class / classes to remove from target's base class list.

    :param append:
        by default, prepends mixins to front of list.
        if True, appends to end of list instead.

    :param after:
        optionally make sure all mixins are inserted after
        this class / classes.

    :param before:
        optionally make sure all mixins are inserted before
        this class / classes.

    :param dryrun:
        optionally perform all calculations / raise errors,
        but don't actually modify the class.
    """
    if isinstance(add, type):
        add = [add]

    bases = list(target.__bases__)

    # strip out requested mixins
    if remove:
        if isinstance(remove, type):
            remove = [remove]
        for mixin in remove:
            if add and mixin in add:
                continue
            if mixin in bases:
                bases.remove(mixin)

    # add requested mixins
    if add:
        for mixin in add:
            # if mixin already present (explicitly or not), leave alone
            if any(issubclass(base, mixin) for base in bases):
                continue

            # determine insertion point
            if append:
                for idx, base in enumerate(bases):
                    if issubclass(mixin, base):
                        # don't insert mixin after one of it's own bases
                        break
                    if before and issubclass(base, before):
                        # don't insert mixin after any <before> classes.
                        break
                else:
                    # append to end
                    idx = len(bases)
            elif after:
                for end_idx, base in enumerate(reversed(bases)):
                    if issubclass(base, after):
                        # don't insert mixin before any <after> classes.
                        idx = len(bases) - end_idx
                        assert bases[idx-1] == base
                        break
                else:
                    idx = 0
            else:
                # insert at start
                idx = 0

            # insert mixin
            bases.insert(idx, mixin)

    # modify class
    if not dryrun:
        target.__bases__ = tuple(bases)

#=============================================================================
# collection helpers
#=============================================================================
def batch(source, size):
    """
    split iterable into chunks of <size> elements.
    """
    if size < 1:
        raise ValueError("size must be positive integer")
    if isinstance(source, Sequence):
        end = len(source)
        i = 0
        while i < end:
            n = i + size
            yield source[i:n]
            i = n
    elif isinstance(source, Iterable):
        itr = iter(source)
        while True:
            chunk_itr = itertools.islice(itr, size)
            try:
                first = next(chunk_itr)
            except StopIteration:
                break
            yield itertools.chain((first,), chunk_itr)
    else:
        raise TypeError("source must be iterable")

#=============================================================================
# unicode helpers
#=============================================================================

# XXX: should this be moved to passlib.crypto, or compat backports?

def consteq(left, right):
    """Check two strings/bytes for equality.

    This function uses an approach designed to prevent
    timing analysis, making it appropriate for cryptography.
    a and b must both be of the same type: either str (ASCII only),
    or any type that supports the buffer protocol (e.g. bytes).

    Note: If a and b are of different lengths, or if an error occurs,
    a timing attack could theoretically reveal information about the
    types and lengths of a and b--but not their values.
    """
    # NOTE:
    # resources & discussions considered in the design of this function:
    #   hmac timing attack --
    #       http://rdist.root.org/2009/05/28/timing-attack-in-google-keyczar-library/
    #   python developer discussion surrounding similar function --
    #       http://bugs.python.org/issue15061
    #       http://bugs.python.org/issue14955

    # validate types
    if isinstance(left, unicode):
        if not isinstance(right, unicode):
            raise TypeError("inputs must be both unicode or both bytes")
        is_py3_bytes = False
    elif isinstance(left, bytes):
        if not isinstance(right, bytes):
            raise TypeError("inputs must be both unicode or both bytes")
        is_py3_bytes = PY3
    else:
        raise TypeError("inputs must be both unicode or both bytes")

    # do size comparison.
    # NOTE: the double-if construction below is done deliberately, to ensure
    # the same number of operations (including branches) is performed regardless
    # of whether left & right are the same size.
    same_size = (len(left) == len(right))
    if same_size:
        # if sizes are the same, setup loop to perform actual check of contents.
        tmp = left
        result = 0
    if not same_size:
        # if sizes aren't the same, set 'result' so equality will fail regardless
        # of contents. then, to ensure we do exactly 'len(right)' iterations
        # of the loop, just compare 'right' against itself.
        tmp = right
        result = 1

    # run constant-time string comparision
    # TODO: use izip instead (but first verify it's faster than zip for this case)
    if is_py3_bytes:
        for l,r in zip(tmp, right):
            result |= l ^ r
    else:
        for l,r in zip(tmp, right):
            result |= ord(l) ^ ord(r)
    return result == 0

# keep copy of this around since stdlib's version throws error on non-ascii chars in unicode strings.
# our version does, but suffers from some underlying VM issues.  but something is better than
# nothing for plaintext hashes, which need this.  everything else should use consteq(),
# since the stdlib one is going to be as good / better in the general case.
str_consteq = consteq

try:
    # for py3.3 and up, use the stdlib version
    from hmac import compare_digest as consteq
except ImportError:
    pass

    # TODO: could check for cryptography package's version,
    #       but only operates on bytes, so would need a wrapper,
    #       or separate consteq() into a unicode & a bytes variant.
    # from cryptography.hazmat.primitives.constant_time import bytes_eq as consteq

def splitcomma(source, sep=","):
    """split comma-separated string into list of elements,
    stripping whitespace.
    """
    source = source.strip()
    if source.endswith(sep):
        source = source[:-1]
    if not source:
        return []
    return [ elem.strip() for elem in source.split(sep) ]

def saslprep(source, param="value"):
    """Normalizes unicode strings using SASLPrep stringprep profile.

    The SASLPrep profile is defined in :rfc:`4013`.
    It provides a uniform scheme for normalizing unicode usernames
    and passwords before performing byte-value sensitive operations
    such as hashing. Among other things, it normalizes diacritic
    representations, removes non-printing characters, and forbids
    invalid characters such as ``\\n``. Properly internationalized
    applications should run user passwords through this function
    before hashing.

    :arg source:
        unicode string to normalize & validate

    :param param:
        Optional noun identifying source parameter in error messages
        (Defaults to the string ``"value"``). This is mainly useful to make the caller's error
        messages make more sense contextually.

    :raises ValueError:
        if any characters forbidden by the SASLPrep profile are encountered.

    :raises TypeError:
        if input is not :class:`!unicode`

    :returns:
        normalized unicode string

    .. note::

        This function is not available under Jython,
        as the Jython stdlib is missing the :mod:`!stringprep` module
        (`Jython issue 1758320 <http://bugs.jython.org/issue1758320>`_).

    .. versionadded:: 1.6
    """
    # saslprep - http://tools.ietf.org/html/rfc4013
    # stringprep - http://tools.ietf.org/html/rfc3454
    #              http://docs.python.org/library/stringprep.html

    # validate type
    # XXX: support bytes (e.g. run through want_unicode)?
    #      might be easier to just integrate this into cryptcontext.
    if not isinstance(source, unicode):
        raise TypeError("input must be unicode string, not %s" %
                        (type(source),))

    # mapping stage
    #   - map non-ascii spaces to U+0020 (stringprep C.1.2)
    #   - strip 'commonly mapped to nothing' chars (stringprep B.1)
    in_table_c12 = stringprep.in_table_c12
    in_table_b1 = stringprep.in_table_b1
    data = join_unicode(
        _USPACE if in_table_c12(c) else c
        for c in source
        if not in_table_b1(c)
        )

    # normalize to KC form
    data = unicodedata.normalize('NFKC', data)
    if not data:
        return _UEMPTY

    # check for invalid bi-directional strings.
    # stringprep requires the following:
    #   - chars in C.8 must be prohibited.
    #   - if any R/AL chars in string:
    #       - no L chars allowed in string
    #       - first and last must be R/AL chars
    # this checks if start/end are R/AL chars. if so, prohibited loop
    # will forbid all L chars. if not, prohibited loop will forbid all
    # R/AL chars instead. in both cases, prohibited loop takes care of C.8.
    is_ral_char = stringprep.in_table_d1
    if is_ral_char(data[0]):
        if not is_ral_char(data[-1]):
            raise ValueError("malformed bidi sequence in " + param)
        # forbid L chars within R/AL sequence.
        is_forbidden_bidi_char = stringprep.in_table_d2
    else:
        # forbid R/AL chars if start not setup correctly; L chars allowed.
        is_forbidden_bidi_char = is_ral_char

    # check for prohibited output - stringprep tables A.1, B.1, C.1.2, C.2 - C.9
    in_table_a1 = stringprep.in_table_a1
    in_table_c21_c22 = stringprep.in_table_c21_c22
    in_table_c3 = stringprep.in_table_c3
    in_table_c4 = stringprep.in_table_c4
    in_table_c5 = stringprep.in_table_c5
    in_table_c6 = stringprep.in_table_c6
    in_table_c7 = stringprep.in_table_c7
    in_table_c8 = stringprep.in_table_c8
    in_table_c9 = stringprep.in_table_c9
    for c in data:
        # check for chars mapping stage should have removed
        assert not in_table_b1(c), "failed to strip B.1 in mapping stage"
        assert not in_table_c12(c), "failed to replace C.1.2 in mapping stage"

        # check for forbidden chars
        if in_table_a1(c):
            raise ValueError("unassigned code points forbidden in " + param)
        if in_table_c21_c22(c):
            raise ValueError("control characters forbidden in " + param)
        if in_table_c3(c):
            raise ValueError("private use characters forbidden in " + param)
        if in_table_c4(c):
            raise ValueError("non-char code points forbidden in " + param)
        if in_table_c5(c):
            raise ValueError("surrogate codes forbidden in " + param)
        if in_table_c6(c):
            raise ValueError("non-plaintext chars forbidden in " + param)
        if in_table_c7(c):
            # XXX: should these have been caught by normalize?
            # if so, should change this to an assert
            raise ValueError("non-canonical chars forbidden in " + param)
        if in_table_c8(c):
            raise ValueError("display-modifying / deprecated chars "
                             "forbidden in" + param)
        if in_table_c9(c):
            raise ValueError("tagged characters forbidden in " + param)

        # do bidi constraint check chosen by bidi init, above
        if is_forbidden_bidi_char(c):
            raise ValueError("forbidden bidi character in " + param)

    return data

# replace saslprep() with stub when stringprep is missing
if stringprep is None: # pragma: no cover -- runtime detection
    def saslprep(source, param="value"):
        """stub for saslprep()"""
        raise NotImplementedError("saslprep() support requires the 'stringprep' "
                            "module, which is " + _stringprep_missing_reason)

#=============================================================================
# bytes helpers
#=============================================================================
def render_bytes(source, *args):
    """Peform ``%`` formating using bytes in a uniform manner across Python 2/3.

    This function is motivated by the fact that
    :class:`bytes` instances do not support ``%`` or ``{}`` formatting under Python 3.
    This function is an attempt to provide a replacement:
    it converts everything to unicode (decoding bytes instances as ``latin-1``),
    performs the required formatting, then encodes the result to ``latin-1``.

    Calling ``render_bytes(source, *args)`` should function roughly the same as
    ``source % args`` under Python 2.

    .. todo::
        python >= 3.5 added back limited support for bytes %,
        can revisit when 3.3/3.4 is dropped.
    """
    if isinstance(source, bytes):
        source = source.decode("latin-1")
    result = source % tuple(arg.decode("latin-1") if isinstance(arg, bytes)
                            else arg for arg in args)
    return result.encode("latin-1")

if PY3:
    # new in py32
    def bytes_to_int(value):
        return int.from_bytes(value, 'big')
    def int_to_bytes(value, count):
        return value.to_bytes(count, 'big')
else:
    # XXX: can any of these be sped up?
    from binascii import hexlify, unhexlify
    def bytes_to_int(value):
        return int(hexlify(value),16)
    def int_to_bytes(value, count):
        return unhexlify(('%%0%dx' % (count<<1)) % value)

add_doc(bytes_to_int, "decode byte string as single big-endian integer")
add_doc(int_to_bytes, "encode integer as single big-endian byte string")

def xor_bytes(left, right):
    """Perform bitwise-xor of two byte strings (must be same size)"""
    return int_to_bytes(bytes_to_int(left) ^ bytes_to_int(right), len(left))

def repeat_string(source, size):
    """
    repeat or truncate <source> string, so it has length <size>
    """
    mult = 1 + (size - 1) // len(source)
    return (source * mult)[:size]


def utf8_repeat_string(source, size):
    """
    variant of repeat_string() which truncates to nearest UTF8 boundary.
    """
    mult = 1 + (size - 1) // len(source)
    return utf8_truncate(source * mult, size)


_BNULL = b"\x00"
_UNULL = u("\x00")

def right_pad_string(source, size, pad=None):
    """right-pad or truncate <source> string, so it has length <size>"""
    cur = len(source)
    if size > cur:
        if pad is None:
            pad = _UNULL if isinstance(source, unicode) else _BNULL
        return source+pad*(size-cur)
    else:
        return source[:size]


def utf8_truncate(source, index):
    """
    helper to truncate UTF8 byte string to nearest character boundary ON OR AFTER <index>.
    returned prefix will always have length of at least <index>, and will stop on the
    first byte that's not a UTF8 continuation byte (128 - 191 inclusive).
    since utf8 should never take more than 4 bytes to encode known unicode values,
    we can stop after ``index+3`` is reached.

    :param bytes source:
    :param int index:
    :rtype: bytes
    """
    # general approach:
    #
    # * UTF8 bytes will have high two bits (0xC0) as one of:
    #   00 -- ascii char
    #   01 -- ascii char
    #   10 -- continuation of multibyte char
    #   11 -- start of multibyte char.
    #   thus we can cut on anything where high bits aren't "10" (0x80; continuation byte)
    #
    # * UTF8 characters SHOULD always be 1 to 4 bytes, though they may be unbounded.
    #   so we just keep going until first non-continuation byte is encountered, or end of str.
    #   this should work predictably even for malformed/non UTF8 inputs.

    if not isinstance(source, bytes):
        raise ExpectedTypeError(source, bytes, "source")

    # validate index
    end = len(source)
    if index < 0:
        index = max(0, index + end)
    if index >= end:
        return source

    # can stop search after 4 bytes, won't ever have longer utf8 sequence.
    end = min(index + 3, end)

    # loop until we find non-continuation byte
    while index < end:
        if byte_elem_value(source[index]) & 0xC0 != 0x80:
            # found single-char byte, or start-char byte.
            break
        # else: found continuation byte.
        index += 1
    else:
        assert index == end

    # truncate at final index
    result = source[:index]

    def sanity_check():
        # try to decode source
        try:
            text = source.decode("utf-8")
        except UnicodeDecodeError:
            # if source isn't valid utf8, byte level match is enough
            return True

        # validate that result was cut on character boundary
        assert text.startswith(result.decode("utf-8"))
        return True

    assert sanity_check()

    return result

#=============================================================================
# encoding helpers
#=============================================================================
_ASCII_TEST_BYTES = b"\x00\n aA:#!\x7f"
_ASCII_TEST_UNICODE = _ASCII_TEST_BYTES.decode("ascii")

def is_ascii_codec(codec):
    """Test if codec is compatible with 7-bit ascii (e.g. latin-1, utf-8; but not utf-16)"""
    return _ASCII_TEST_UNICODE.encode(codec) == _ASCII_TEST_BYTES

def is_same_codec(left, right):
    """Check if two codec names are aliases for same codec"""
    if left == right:
        return True
    if not (left and right):
        return False
    return _lookup_codec(left).name == _lookup_codec(right).name

_B80 = b'\x80'[0]
_U80 = u('\x80')
def is_ascii_safe(source):
    """Check if string (bytes or unicode) contains only 7-bit ascii"""
    r = _B80 if isinstance(source, bytes) else _U80
    return all(c < r for c in source)

def to_bytes(source, encoding="utf-8", param="value", source_encoding=None):
    """Helper to normalize input to bytes.

    :arg source:
        Source bytes/unicode to process.

    :arg encoding:
        Target encoding (defaults to ``"utf-8"``).

    :param param:
        Optional name of variable/noun to reference when raising errors

    :param source_encoding:
        If this is specified, and the source is bytes,
        the source will be transcoded from *source_encoding* to *encoding*
        (via unicode).

    :raises TypeError: if source is not unicode or bytes.

    :returns:
        * unicode strings will be encoded using *encoding*, and returned.
        * if *source_encoding* is not specified, byte strings will be
          returned unchanged.
        * if *source_encoding* is specified, byte strings will be transcoded
          to *encoding*.
    """
    assert encoding
    if isinstance(source, bytes):
        if source_encoding and not is_same_codec(source_encoding, encoding):
            return source.decode(source_encoding).encode(encoding)
        else:
            return source
    elif isinstance(source, unicode):
        return source.encode(encoding)
    else:
        raise ExpectedStringError(source, param)

def to_unicode(source, encoding="utf-8", param="value"):
    """Helper to normalize input to unicode.

    :arg source:
        source bytes/unicode to process.

    :arg encoding:
        encoding to use when decoding bytes instances.

    :param param:
        optional name of variable/noun to reference when raising errors.

    :raises TypeError: if source is not unicode or bytes.

    :returns:
        * returns unicode strings unchanged.
        * returns bytes strings decoded using *encoding*
    """
    assert encoding
    if isinstance(source, unicode):
        return source
    elif isinstance(source, bytes):
        return source.decode(encoding)
    else:
        raise ExpectedStringError(source, param)

if PY3:
    def to_native_str(source, encoding="utf-8", param="value"):
        if isinstance(source, bytes):
            return source.decode(encoding)
        elif isinstance(source, unicode):
            return source
        else:
            raise ExpectedStringError(source, param)
else:
    def to_native_str(source, encoding="utf-8", param="value"):
        if isinstance(source, bytes):
            return source
        elif isinstance(source, unicode):
            return source.encode(encoding)
        else:
            raise ExpectedStringError(source, param)

add_doc(to_native_str,
    """Take in unicode or bytes, return native string.

    Python 2: encodes unicode using specified encoding, leaves bytes alone.
    Python 3: leaves unicode alone, decodes bytes using specified encoding.

    :raises TypeError: if source is not unicode or bytes.

    :arg source:
        source unicode or bytes string.

    :arg encoding:
        encoding to use when encoding unicode or decoding bytes.
        this defaults to ``"utf-8"``.

    :param param:
        optional name of variable/noun to reference when raising errors.

    :returns: :class:`str` instance
    """)

@deprecated_function(deprecated="1.6", removed="1.7")
def to_hash_str(source, encoding="ascii"): # pragma: no cover -- deprecated & unused
    """deprecated, use to_native_str() instead"""
    return to_native_str(source, encoding, param="hash")

_true_set = set("true t yes y on 1 enable enabled".split())
_false_set = set("false f no n off 0 disable disabled".split())
_none_set = set(["", "none"])

def as_bool(value, none=None, param="boolean"):
    """
    helper to convert value to boolean.
    recognizes strings such as "true", "false"
    """
    assert none in [True, False, None]
    if isinstance(value, unicode_or_bytes_types):
        clean = value.lower().strip()
        if clean in _true_set:
            return True
        if clean in _false_set:
            return False
        if clean in _none_set:
            return none
        raise ValueError("unrecognized %s value: %r" % (param, value))
    elif isinstance(value, bool):
        return value
    elif value is None:
        return none
    else:
        return bool(value)

#=============================================================================
# host OS helpers
#=============================================================================

def is_safe_crypt_input(value):
    """
    UT helper --
    test if value is safe to pass to crypt.crypt();
    under PY3, can't pass non-UTF8 bytes to crypt.crypt.
    """
    if crypt_accepts_bytes or not isinstance(value, bytes):
        return True
    try:
        value.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False

try:
    from crypt import crypt as _crypt
except ImportError: # pragma: no cover
    _crypt = None
    has_crypt = False
    def safe_crypt(secret, hash):
        return None
else:
    has_crypt = True
    _NULL = '\x00'

    # some crypt() variants will return various constant strings when
    # an invalid/unrecognized config string is passed in; instead of
    # returning NULL / None. examples include ":", ":0", "*0", etc.
    # safe_crypt() returns None for any string starting with one of the
    # chars in this string...
    _invalid_prefixes = u("*:!")

    if PY3:

        # * pypy3 (as of v7.3.1) has a crypt which accepts bytes, or ASCII-only unicode.
        # * whereas CPython3 (as of v3.9) has a crypt which doesn't take bytes,
        #   but accepts ANY unicode (which it always encodes to UTF8).
        crypt_accepts_bytes = True
        try:
            _crypt(b"\xEE", "xx")
        except TypeError:
            # CPython will throw TypeError
            crypt_accepts_bytes = False
        except:  # no pragma
            # don't care about other errors this might throw,
            # just want to see if we get past initial type-coercion step.
            pass

        def safe_crypt(secret, hash):
            if crypt_accepts_bytes:
                # PyPy3 -- all bytes accepted, but unicode encoded to ASCII,
                # so handling that ourselves.
                if isinstance(secret, unicode):
                    secret = secret.encode("utf-8")
                if _BNULL in secret:
                    raise ValueError("null character in secret")
                if isinstance(hash, unicode):
                    hash = hash.encode("ascii")
            else:
                # CPython3's crypt() doesn't take bytes, only unicode; unicode which is then
                # encoding using utf-8 before passing to the C-level crypt().
                # so we have to decode the secret.
                if isinstance(secret, bytes):
                    orig = secret
                    try:
                        secret = secret.decode("utf-8")
                    except UnicodeDecodeError:
                        return None
                    # sanity check it encodes back to original byte string,
                    # otherwise when crypt() does it's encoding, it'll hash the wrong bytes!
                    assert secret.encode("utf-8") == orig, \
                                "utf-8 spec says this can't happen!"
                if _NULL in secret:
                    raise ValueError("null character in secret")
                if isinstance(hash, bytes):
                    hash = hash.decode("ascii")
            try:
                result = _crypt(secret, hash)
            except OSError:
                # new in py39 -- per https://bugs.python.org/issue39289,
                # crypt() now throws OSError for various things, mainly unknown hash formats
                # translating that to None for now (may revise safe_crypt behavior in future)
                return None
            # NOTE: per issue 113, crypt() may return bytes in some odd cases.
            #       assuming it should still return an ASCII hash though,
            #       or there's a bigger issue at hand.
            if isinstance(result, bytes):
                result = result.decode("ascii")
            if not result or result[0] in _invalid_prefixes:
                return None
            return result
    else:

        #: see feature-detection in PY3 fork above
        crypt_accepts_bytes = True

        # Python 2 crypt handler
        def safe_crypt(secret, hash):
            if isinstance(secret, unicode):
                secret = secret.encode("utf-8")
            if _NULL in secret:
                raise ValueError("null character in secret")
            if isinstance(hash, unicode):
                hash = hash.encode("ascii")
            result = _crypt(secret, hash)
            if not result:
                return None
            result = result.decode("ascii")
            if result[0] in _invalid_prefixes:
                return None
            return result

add_doc(safe_crypt, """Wrapper around stdlib's crypt.

    This is a wrapper around stdlib's :func:`!crypt.crypt`, which attempts
    to provide uniform behavior across Python 2 and 3.

    :arg secret:
        password, as bytes or unicode (unicode will be encoded as ``utf-8``).

    :arg hash:
        hash or config string, as ascii bytes or unicode.

    :returns:
        resulting hash as ascii unicode; or ``None`` if the password
        couldn't be hashed due to one of the issues:

        * :func:`crypt()` not available on platform.

        * Under Python 3, if *secret* is specified as bytes,
          it must be use ``utf-8`` or it can't be passed
          to :func:`crypt()`.

        * Some OSes will return ``None`` if they don't recognize
          the algorithm being used (though most will simply fall
          back to des-crypt).

        * Some OSes will return an error string if the input config
          is recognized but malformed; current code converts these to ``None``
          as well.
    """)

def test_crypt(secret, hash):
    """check if :func:`crypt.crypt` supports specific hash
    :arg secret: password to test
    :arg hash: known hash of password to use as reference
    :returns: True or False
    """
    # safe_crypt() always returns unicode, which means that for py3,
    # 'hash' can't be bytes, or "== hash" will never be True.
    # under py2 unicode & str(bytes) will compare fine;
    # so just enforcing "unicode_or_str" limitation
    assert isinstance(hash, unicode_or_str), \
        "hash must be unicode_or_str, got %s" % type(hash)
    assert hash, "hash must be non-empty"
    return safe_crypt(secret, hash) == hash

timer = timeit.default_timer
# legacy alias, will be removed in passlib 2.0
tick = timer

def parse_version(source):
    """helper to parse version string"""
    m = re.search(r"(\d+(?:\.\d+)+)", source)
    if m:
        return tuple(int(elem) for elem in m.group(1).split("."))
    return None

#=============================================================================
# randomness
#=============================================================================

#------------------------------------------------------------------------
# setup rng for generating salts
#------------------------------------------------------------------------

# NOTE:
# generating salts (e.g. h64_gensalt, below) doesn't require cryptographically
# strong randomness. it just requires enough range of possible outputs
# that making a rainbow table is too costly. so it should be ok to
# fall back on python's builtin mersenne twister prng, as long as it's seeded each time
# this module is imported, using a couple of minor entropy sources.

try:
    os.urandom(1)
    has_urandom = True
except NotImplementedError: # pragma: no cover
    has_urandom = False

def genseed(value=None):
    """generate prng seed value from system resources"""
    from hashlib import sha512
    if hasattr(value, "getstate") and hasattr(value, "getrandbits"):
        # caller passed in RNG as seed value
        try:
            value = value.getstate()
        except NotImplementedError:
            # this method throws error for e.g. SystemRandom instances,
            # so fall back to extracting 4k of state
            value = value.getrandbits(1 << 15)
    text = u("%s %s %s %.15f %.15f %s") % (
        # if caller specified a seed value, mix it in
        value,

        # add current process id
        # NOTE: not available in some environments, e.g. GAE
        os.getpid() if hasattr(os, "getpid") else None,

        # id of a freshly created object.
        # (at least 1 byte of which should be hard to predict)
        id(object()),

        # the current time, to whatever precision os uses
        time.time(),
        tick(),

        # if urandom available, might as well mix some bytes in.
        os.urandom(32).decode("latin-1") if has_urandom else 0,
        )
    # hash it all up and return it as int/long
    return int(sha512(text.encode("utf-8")).hexdigest(), 16)

if has_urandom:
    rng = random.SystemRandom()
else: # pragma: no cover -- runtime detection
    # NOTE: to reseed use ``rng.seed(genseed(rng))``
    # XXX: could reseed on every call
    rng = random.Random(genseed())

#------------------------------------------------------------------------
# some rng helpers
#------------------------------------------------------------------------
def getrandbytes(rng, count):
    """return byte-string containing *count* number of randomly generated bytes, using specified rng"""
    # NOTE: would be nice if this was present in stdlib Random class

    ###just in case rng provides this...
    ##meth = getattr(rng, "getrandbytes", None)
    ##if meth:
    ##    return meth(count)

    if not count:
        return _BEMPTY
    def helper():
        # XXX: break into chunks for large number of bits?
        value = rng.getrandbits(count<<3)
        i = 0
        while i < count:
            yield value & 0xff
            value >>= 3
            i += 1
    return join_byte_values(helper())

def getrandstr(rng, charset, count):
    """return string containing *count* number of chars/bytes, whose elements are drawn from specified charset, using specified rng"""
    # NOTE: tests determined this is 4x faster than rng.sample(),
    # which is why that's not being used here.

    # check alphabet & count
    if count < 0:
        raise ValueError("count must be >= 0")
    letters = len(charset)
    if letters == 0:
        raise ValueError("alphabet must not be empty")
    if letters == 1:
        return charset * count

    # get random value, and write out to buffer
    def helper():
        # XXX: break into chunks for large number of letters?
        value = rng.randrange(0, letters**count)
        i = 0
        while i < count:
            yield charset[value % letters]
            value //= letters
            i += 1

    if isinstance(charset, unicode):
        return join_unicode(helper())
    else:
        return join_byte_elems(helper())

_52charset = '2346789ABCDEFGHJKMNPQRTUVWXYZabcdefghjkmnpqrstuvwxyz'

@deprecated_function(deprecated="1.7", removed="2.0",
                     replacement="passlib.pwd.genword() / passlib.pwd.genphrase()")
def generate_password(size=10, charset=_52charset):
    """generate random password using given length & charset

    :param size:
        size of password.

    :param charset:
        optional string specified set of characters to draw from.

        the default charset contains all normal alphanumeric characters,
        except for the characters ``1IiLl0OoS5``, which were omitted
        due to their visual similarity.

    :returns: :class:`!str` containing randomly generated password.

    .. note::

        Using the default character set, on a OS with :class:`!SystemRandom` support,
        this function should generate passwords with 5.7 bits of entropy per character.
    """
    return getrandstr(rng, charset, size)

#=============================================================================
# object type / interface tests
#=============================================================================
_handler_attrs = (
        "name",
        "setting_kwds", "context_kwds",
        "verify", "hash", "identify",
        )

def is_crypt_handler(obj):
    """check if object follows the :ref:`password-hash-api`"""
    # XXX: change to use isinstance(obj, PasswordHash) under py26+?
    return all(hasattr(obj, name) for name in _handler_attrs)

_context_attrs = (
        "needs_update",
        "genconfig", "genhash",
        "verify", "encrypt", "identify",
        )

def is_crypt_context(obj):
    """check if object appears to be a :class:`~passlib.context.CryptContext` instance"""
    # XXX: change to use isinstance(obj, CryptContext)?
    return all(hasattr(obj, name) for name in _context_attrs)

##def has_many_backends(handler):
##    "check if handler provides multiple baceknds"
##    # NOTE: should also provide get_backend(), .has_backend(), and .backends attr
##    return hasattr(handler, "set_backend")

def has_rounds_info(handler):
    """check if handler provides the optional :ref:`rounds information <rounds-attributes>` attributes"""
    return ('rounds' in handler.setting_kwds and
            getattr(handler, "min_rounds", None) is not None)

def has_salt_info(handler):
    """check if handler provides the optional :ref:`salt information <salt-attributes>` attributes"""
    return ('salt' in handler.setting_kwds and
            getattr(handler, "min_salt_size", None) is not None)

##def has_raw_salt(handler):
##    "check if handler takes in encoded salt as unicode (False), or decoded salt as bytes (True)"
##    sc = getattr(handler, "salt_chars", None)
##    if sc is None:
##        return None
##    elif isinstance(sc, unicode):
##        return False
##    elif isinstance(sc, bytes):
##        return True
##    else:
##        raise TypeError("handler.salt_chars must be None/unicode/bytes")

#=============================================================================
# eof
#=============================================================================
