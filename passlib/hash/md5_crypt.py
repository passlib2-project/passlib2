"""passlib.hash.md5_crypt - md5-crypt algorithm"""
#=========================================================
#imports
#=========================================================
#core
from hashlib import md5
import re
import logging; log = logging.getLogger(__name__)
from warnings import warn
#site
#libs
from passlib.utils import norm_rounds, norm_salt, h64, autodocument
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
def raw_md5_crypt(secret, salt, apr=False):
    "perform raw md5 encryption"
    #NOTE: regarding 'apr' format: really, apache? you had to invent a whole new "$apr1$" format,
    # when all you did was change the ident incorporated into the hash?
    # would love to find webpage explaining why just using a portable
    # implementation of $1$ wasn't sufficient.

    #validate secret
    if not isinstance(secret, str):
        raise TypeError, "secret must be string"

    #validate salt
    if len(salt) > 8:
        salt = salt[:8]

    #primary hash = secret+id+salt+...
    h = md5(secret)
    h.update("$apr1$" if apr else "$1$")
    h.update(salt)

    # primary hash - add len(secret) chars of tmp hash,
    # where temp hash is md5(secret+salt+secret)
    tmp = md5(secret + salt + secret).digest()
    assert len(tmp) == 16
    slen = len(secret)
    h.update(tmp * (slen//16) + tmp[:slen % 16])

    # primary hash - add null chars & first char of secret !?!
    #
    # this may have historically been a bug,
    # where they meant to use tmp[0] instead of '\x00',
    # but the code memclear'ed the buffer,
    # and now all implementations have to use this.
    #
    # sha-crypt replaced this step with
    # something more useful, anyways
    idx = len(secret)
    evenchar = secret[:1] #NOTE: empty string if secret is empty
    while idx > 0:
        h.update('\x00' if idx & 1 else evenchar)
        idx >>= 1
    result = h.digest()

    # do 1000 rounds of md5 to make things harder.
    # each round we do digest of content,
    # where content is formed from concatenation of...
    #   idx % 2 => secret else result
    #   idx % 3 => salt
    #   idx % 7 => secret
    #   idx % 2 => result else secret
    # first we pre-compute some strings and hashes to speed up calculation
    secret_secret = secret*2
    salt_secret = salt+secret
    salt_secret_secret = salt + secret*2
    secret_hash = md5(secret).copy
    secret_secret_hash = md5(secret*2).copy
    secret_salt_hash = md5(secret+salt).copy
    secret_salt_secret_hash = md5(secret+salt+secret).copy
    for idx in xrange(1000):
        if idx & 1:
            if idx % 3:
                if idx % 7:
                    h = secret_salt_secret_hash()
                else:
                    h = secret_salt_hash()
            elif idx % 7:
                h = secret_secret_hash()
            else:
                h = secret_hash()
            h.update(result)
        else:
            h = md5(result)
            if idx % 3:
                if idx % 7:
                    h.update(salt_secret_secret)
                else:
                    h.update(salt_secret)
            elif idx % 7:
                h.update(secret_secret)
            else:
                h.update(secret)
        result = h.digest()

    #encode resulting hash
    return h64.encode_transposed_bytes(result, _chk_offsets)

_chk_offsets = (
    12,6,0,
    13,7,1,
    14,8,2,
    15,9,3,
    5,10,4,
    11,
)

#=========================================================
#choose backend
#=========================================================

#fallback to default backend (defined above)
backend = "builtin"

#check if stdlib crypt is available, and if so, if OS supports $1$
#XXX: is this test expensive enough it should be delayed
#until md5-crypt is requested?

try:
    from crypt import crypt
except ImportError:
    crypt = None
else:
    if crypt("test", "$1$test") == '$1$test$pi/xDtU5WFVRqYS6BMU8X/':
        backend = "os-crypt"
    else:
        crypt = None

#TODO: could check for libssl support (openssl passwd -1)

#=========================================================
#algorithm information
#=========================================================
name = "md5_crypt"
#stats: 128 bit checksum, 48 bit salt

setting_kwds = ("salt",)
context_kwds = ()

min_salt_chars = 0
max_salt_chars = 8

#=========================================================
#internal helpers
#=========================================================
_pat = re.compile(r"""
    ^
    \$1
    \$(?P<salt>[A-Za-z0-9./]{,8})
    (\$(?P<chk>[A-Za-z0-9./]{22})?)?
    $
    """, re.X)

def parse(hash):
    if not hash:
        raise ValueError, "no hash specified"
    m = _pat.match(hash)
    if not m:
        raise ValueError, "invalid md5-crypt hash"
    salt, chk = m.group("salt", "chk")
    return dict(
        salt=salt,
        checksum=chk,
    )

def render(salt, checksum=None):
    return "$1$%s$%s" % (salt, checksum or '')

#=========================================================
#primary interface
#=========================================================
def genconfig(salt=None):
    ##"""generate md5-crypt configuration string
    ##
    ##:param salt:
    ##    optional salt string to use.
    ##
    ##    if omitted, one will be automatically generated (recommended).
    ##
    ##    length must be between 0 and 8 characters inclusive.
    ##    characters must be in range ``A-Za-z0-9./``.
    ##
    ##:returns:
    ##    md5-crypt configuration string.
    ##"""
    salt = norm_salt(salt, min_salt_chars, max_salt_chars, name=name)
    return render(salt, None)

def genhash(secret, config):
    #parse and run through genconfig to validate configuration
    info = parse(config)
    info.pop("checksum")
    config = genconfig(**info)

    #FIXME: can't find definitive policy on how md5-crypt handles non-ascii.
    if isinstance(secret, unicode):
        secret = secret.encode("utf-8")

    #run through chosen backend
    if crypt:
        #use OS's crypt(), should be faster than builtin backend
        return crypt(secret, config)

    else:
        #fallback to builtin backend
        info = parse(config)
        salt = info['salt']
        checksum = raw_md5_crypt(secret, salt)
        return render(salt, checksum)

#=========================================================
#secondary interface
#=========================================================
def encrypt(secret, **settings):
    return genhash(secret, genconfig(**settings))

def verify(secret, hash):
    return hash == genhash(secret, hash)

def identify(hash):
    return bool(hash and _pat.match(hash))

autodocument(globals())
#=========================================================
#eof
#=========================================================
