"""passlib.hash.des_crypt - traditional unix (DES) crypt

Old Unix-Crypt Algorithm, as originally used on unix before md5-crypt arrived.
This implementation uses the builtin ``crypt`` module when available,
but contains a pure-python fallback so that this algorithm can always be used.
"""
#references -
# http://www.phpbuilder.com/manual/function.crypt.php
# http://dropsafe.crypticide.com/article/1389

#=========================================================
#imports
#=========================================================
#core
import re
import logging; log = logging.getLogger(__name__)
from warnings import warn
#site
#libs
from passlib.utils import norm_salt, h64
from passlib.utils.des import mdes_encrypt_int_block
#pkg
#local
__all__ = [
    "genhash",
    "genconfig",
    "encrypt",
    "identify",
    "verify",
]

#=========================================================
#pure-python backend
#=========================================================
def _crypt_secret_to_key(secret):
    "hash secret -> key using crypt format"
    key_value = 0
    for i, c in enumerate(secret[:8]):
        key_value |= (ord(c)&0x7f) << (57-8*i)
    return key_value

def raw_crypt(secret, salt):
    "pure-python fallback if stdlib support not present"
    assert len(salt) == 2

    #NOTE: technically might be able to use
    #fewer salt chars, not sure what standard behavior is,
    #so forbidding it for handler.

    try:
        salt_value = h64.decode_int12(salt)
    except ValueError:
        raise ValueError, "invalid chars in salt"
    #FIXME: ^ this will throws error if bad salt chars are used
    # whereas linux crypt does something (inexplicable) with it

    #convert secret string into an integer
    key_value = _crypt_secret_to_key(secret)

    #run data through des using input of 0
    result = mdes_encrypt_int_block(key_value, 0, salt=salt_value, rounds=25)

    #run h64 encode on result
    return h64.encode_int64(result)

#=========================================================
#choose backend
#=========================================================
backend = "builtin"

try:
    #try stdlib module, which is only present under posix
    from crypt import crypt
    if crypt("test", "ab") == 'abgOeLfPimXQo':
        backend = "os-crypt"
    else:
        #shouldn't be any unix os which has crypt but doesn't support this format.
        warn("crypt() failed runtime test for DES-CRYPT support")
        crypt = None
except ImportError:
    #XXX: could check for openssl passwd -des support in libssl

    #TODO: need to reconcile our implementation's behavior
    # with the stdlib's behavior so error types, messages, and limitations
    # are the same. (eg: handling of None and unicode chars)
    crypt = None

#=========================================================
#algorithm information
#=========================================================
name = "des_crypt"
#stats: 66 bit checksum, 12 bit salt, max 8 chars of secret

setting_kwds = ("salt",)
context_kwds = ()

#=========================================================
#internal helpers
#=========================================================
#FORMAT: 2 chars of H64-encoded salt + 11 chars of H64-encoded checksum
_pat = re.compile(r"""
    ^
    (?P<salt>[./a-z0-9]{2})
    (?P<chk>[./a-z0-9]{11})?
    $""", re.X|re.I)

def parse(hash):
    if not hash:
        raise ValueError, "no hash specified"
    m = _pat.match(hash)
    if not m:
        raise ValueError, "invalid des-crypt hash"
    salt, chk = m.group("salt", "chk")
    return dict(
        salt=salt,
        checksum=chk,
    )

def render(salt, checksum=None):
    if len(salt) < 2:
        raise ValueError, "invalid salt"
    return "%s%s" % (salt[:2], checksum or '')

#=========================================================
#primary interface
#=========================================================
def genconfig(salt=None):
    """generate xxx configuration string

    :param salt:
        optional salt string to use.

        if omitted, one will be automatically generated (recommended).

        length must be 2 characters.
        characters must be in range ``A-Za-z0-9./``.

    :returns:
        xxx configuration string.
    """
    salt = norm_salt(salt, 2, name=name)
    return render(salt, None)

def genhash(secret, config):
    #parse and run through genconfig to validate configuration
    info = parse(config)
    info.pop("checksum")
    config = genconfig(**info)

    #forbidding nul chars because linux crypt (and most C implementations) won't accept it either.
    if '\x00' in secret:
        raise ValueError, "null char in secret"

    #XXX: des-crypt predates unicode, not sure if there's an official policy for handing it.
    #for now, just coercing to utf-8.
    if isinstance(secret, unicode):
        secret = secret.encode("utf-8")

    #run through chosen backend
    if crypt:
        #XXX: given a single letter salt, linux crypt returns a hash with the original salt doubled,
        #     but appears to calculate the hash based on the letter + "G" as the second byte.
        #     this results in a hash that won't validate, which is DEFINITELY wrong.
        #     need to find out it's underlying logic, and if it's part of spec,
        #     or just weirdness that should actually be an error.
        #     until then, passlib raises an error in genconfig()

        #XXX: given salt chars outside of h64.CHARS range, linux crypt
        #     does something unknown when decoding salt to 12 bit int,
        #     successfully creates a hash, but reports the original salt.
        #     need to find out it's underlying logic, and if it's part of spec,
        #     or just weirdness that should actually be an error.
        #     until then, passlib raises an error for bad salt chars.
        return crypt(secret, config)
    else:
        salt = config[:2]
        return render(salt, raw_crypt(secret, salt))

#=========================================================
#secondary interface
#=========================================================
def encrypt(secret, **settings):
    return genhash(secret, genconfig(**settings))

def verify(secret, hash):
    return hash == genhash(secret, hash)

def identify(hash):
    return bool(hash and _pat.match(hash))

#=========================================================
#eof
#=========================================================
