"""passlib.drivers.digests - plain hash digests
"""
#=========================================================
#imports
#=========================================================
#core
from hashlib import md5, sha1
import logging; log = logging.getLogger(__name__)
import re
from warnings import warn
#site
#libs
from passlib.utils.drivers import ExtHash, BaseHash
#pkg
#local
__all__ = [
    "ldap_md5",
    "ldap_sha1",
    "ldap_salted_md5",
    "ldap_salted_sha1",
]

#=========================================================
#ldap helpers
#=========================================================
#reference - http://www.openldap.org/doc/admin24/security.html

class _Base64DigestHelper(BaseHash):
    "helper for ldap_md5 / ldap_sha1"

    #_ident
    #_hash
    #_pat

    @classmethod
    def identify(cls, hash):
        return bool(hash and cls._pat.match(hash))

    @classmethod
    def genhash(cls, secret, hash):
        if secret is None:
            raise TypeError, "no secret provided"
        if isinstance(secret, unicode):
            secret = secret.encode("utf-8")
        if hash is not None and not cls.identify(hash):
            raise ValueError, "not a %s hash" % (cls.name,)
        return cls._ident + cls._hash(secret).digest().encode("base64").strip()

class _SaltedBase64DigestHelper(ExtHash):
    "helper for ldap_salted_md5 / ldap_salted_sha1"
    setting_kwds = ("salt",)

    #_ident
    #_hash
    #_pat
    #_default_chk
    min_salt_chars = max_salt_chars = 4
    salt_charset = ''.join(chr(x) for x in xrange(256))

    @classmethod
    def identify(cls, hash):
        return bool(hash and cls._pat.match(hash))

    @classmethod
    def from_string(cls, hash):
        if not hash:
            raise ValueError, "no hash specified"
        m = cls._pat.match(hash)
        if not m:
            raise ValueError, "not a %s hash" % (cls.name,)
        tmp = m.group("tmp").decode("base64")
        chk, salt = tmp[:-4], tmp[-4:]
        return cls(checksum=chk, salt=salt, strict=True)

    def to_string(self):
        return self._ident + ((self.checksum or self._default_chk) + self.salt).encode("base64").strip()

    def calc_checksum(self, secret):
        if secret is None:
            raise TypeError, "no secret provided"
        if isinstance(secret, unicode):
            secret = secret.encode("utf-8")
        return self._hash(secret + self.salt).digest()

#=========================================================
#implementations
#=========================================================
class ldap_md5(_Base64DigestHelper):
    """This class stores passwords using LDAP's plain MD5 format, and follows the :ref:`password-hash-api`.

    The :meth:`encrypt()` and :meth:`genconfig` methods have no optional keywords.
    """
    name = "ldap_md5"
    setting_kwds = ()

    _ident = "{MD5}"
    _hash = md5
    _pat = re.compile(r"^\{MD5\}(?P<chk>[+/a-zA-Z0-9]{22}==)$")

class ldap_sha1(_Base64DigestHelper):
    """This class stores passwords using LDAP's plain SHA1 format, and follows the :ref:`password-hash-api`.

    The :meth:`encrypt()` and :meth:`genconfig` methods have no optional keywords.
    """
    name = "ldap_sha1"
    setting_kwds = ()

    _ident = "{SHA}"
    _hash = sha1
    _pat = re.compile(r"^\{SHA\}(?P<chk>[+/a-zA-Z0-9]{27}=)$")

class ldap_salted_md5(_SaltedBase64DigestHelper):
    """This class stores passwords using LDAP's salted MD5 format, and follows the :ref:`password-hash-api`.

    It supports a 4-byte salt.

    The :meth:`encrypt()` and :meth:`genconfig` methods accept the following optional keyword:

    :param salt:
        Optional salt string.
        If not specified, one will be autogenerated (this is recommended).
        If specified, it must be a 4 byte string; each byte may have any value from 0x00 .. 0xff.
    """
    name = "ldap_salted_md5"
    _ident = "{SMD5}"
    _hash = md5
    _pat = re.compile(r"^\{SMD5\}(?P<tmp>[+/a-zA-Z0-9]{27}=)$")
    _default_chk = '\x00' * 16

class ldap_salted_sha1(_SaltedBase64DigestHelper):
    """This class stores passwords using LDAP's salted SHA1 format, and follows the :ref:`password-hash-api`.

    It supports a 4-byte salt.

    The :meth:`encrypt()` and :meth:`genconfig` methods accept the following optional keyword:

    :param salt:
        Optional salt string.
        If not specified, one will be autogenerated (this is recommended).
        If specified, it must be a 4 byte string; each byte may have any value from 0x00 .. 0xff.
    """
    name = "ldap_salted_sha1"
    _ident = "{SSHA}"
    _hash = sha1
    _pat = re.compile(r"^\{SSHA\}(?P<tmp>[+/a-zA-Z0-9]{32})$")
    _default_chk = '\x00' * 20

class ldap_cleartext(BaseHash):
    """This class stores passwords in plaintext, and follows the :ref:`password-hash-api`.

    Unicode passwords will be encoded using utf-8.
    """
    name = "ldap_cleartext"
    setting_kwds = ()
    context_kwds = ()

    _pat = re.compile(r"^\{CLEARTEXT\}(?P<pwd>.*)$")

    @classmethod
    def identify(cls, hash):
        return bool(hash and cls._pat.match(hash))

    @classmethod
    def genhash(cls, secret, hash):
        if hash is not None and not cls.identify(hash):
            raise ValueError, "not a valid ldap_cleartext hash"
        if secret is None:
            raise TypeError, "secret must be string"
        if isinstance(secret, unicode):
            secret = secret.encode("utf-8")
        return "{CLEARTEXT}" + secret

    @classmethod
    def verify(cls, secret, hash):
        if hash is None:
            raise ValueError, "no hash specified"
        return hash == cls.genhash(secret, hash)

#TODO: support {CRYPT} somehow (adapt per host?)

#=========================================================
#eof
#=========================================================
