"""passlib.bcrypt

Implementation of OpenBSD's BCrypt algorithm.

PassLib will use the py-bcrypt package if it is available,
otherwise it will fall back to a slower builtin pure-python implementation.

Note that rounds must be >= 10 or an error will be returned.
"""
#=========================================================
#imports
#=========================================================
from __future__ import with_statement, absolute_import
#core
import re
import logging; log = logging.getLogger(__name__)
from warnings import warn
#site
try:
    from bcrypt import hashpw as pybcrypt_hashpw
except ImportError: #pragma: no cover - though should run whole suite w/o pybcrypt installed
    pybcrypt_hashpw = None
#libs
from passlib.utils import os_crypt, classproperty
from passlib.utils.handlers import MultiBackendHandler

#pkg
#local
__all__ = [
    "bcrypt",
]

#=========================================================
#handler
#=========================================================
class bcrypt(MultiBackendHandler):
    """This class implements the BCrypt password hash, and follows the :ref:`password-hash-api`.

    It supports a fixed-length salt, and a variable number of rounds.

    The :meth:`encrypt()` and :meth:`genconfig` methods accept the following optional keywords:

    :param salt:
        Optional salt string.
        If not specified, one will be autogenerated (this is recommended).
        If specified, it must be 22 characters, drawn from the regexp range ``[./0-9A-Za-z]``.

    :param rounds:
        Optional number of rounds to use.
        Defaults to 12, must be between 4 and 31, inclusive.
        This value is logarithmic, the actual number of iterations used will be :samp:`2**{rounds}`.

    :param ident:
        selects specific version of BCrypt hash that will be used.
        Typically you want to leave this alone, and let it default to ``2a``,
        but it can be set to ``2`` to use the older version of BCrypt.

    It will use the first available of two possible backends:

    * `py-bcrypt <http://www.mindrot.org/projects/py-bcrypt/>`_, if installed.
    * stdlib :func:`crypt()`, if the host OS supports BCrypt.

    You can see which backend is in use by calling the :meth:`get_backend()` method.
    """

    #=========================================================
    #class attrs
    #=========================================================
    name = "bcrypt"
    setting_kwds = ("salt", "rounds", "ident")

    min_salt_chars = max_salt_chars = 22

    default_rounds = 12 #current passlib default
    min_rounds = 4 # bcrypt spec specified minimum
    max_rounds = 31 # 32-bit integer limit (real_rounds=1<<rounds)
    rounds_cost = "log2"

    checksum_chars = 31

    #=========================================================
    #init
    #=========================================================
    _extra_init_settings = ("ident",)

    @classmethod
    def norm_ident(cls, ident, strict=False):
        if not ident:
            if strict:
                raise ValueError("no ident specified")
            ident = "2a"
        if ident not in ("2", "2a"):
            raise ValueError("invalid ident: %r" % (ident,))
        return ident

    #=========================================================
    #formatting
    #=========================================================
    @classmethod
    def identify(cls, hash):
        return bool(hash) and (hash.startswith("$2$") or hash.startswith("$2a$"))

    _pat = re.compile(r"""
        ^
        \$(?P<ident>2a?)
        \$(?P<rounds>\d{2})
        \$(?P<salt>[A-Za-z0-9./]{22})
        (?P<chk>[A-Za-z0-9./]{31})?
        $
        """, re.X)

    @classmethod
    def from_string(cls, hash):
        if not hash:
            raise ValueError("no hash specified")
        m = cls._pat.match(hash)
        if not m:
            raise ValueError("invalid bcrypt hash")
        ident, rounds, salt, chk = m.group("ident", "rounds", "salt", "chk")
        return cls(
            rounds=int(rounds),
            salt=salt,
            checksum=chk,
            ident=ident,
            strict=bool(chk),
        )

    def to_string(self):
        return "$%s$%02d$%s%s" % (self.ident, self.rounds, self.salt, self.checksum or '')

    #=========================================================
    #primary interface
    #=========================================================
    backends = ("pybcrypt", "os_crypt")

    @classproperty
    def _has_backend_pybcrypt(cls):
        return pybcrypt_hashpw is not None

    @classproperty
    def _has_backend_os_crypt(cls):
        return (
            os_crypt is not None
            and
            os_crypt("test", "$2a$04$......................") ==
                '$2a$04$......................qiOQjkB8hxU8OzRhS.GhRMa4VUnkPty'
            and
            os_crypt("test", "$2$04$......................") ==
                '$2$04$......................1O4gOrCYaqBG3o/4LnT2ykQUt1wbyju'
        )

    @classmethod
    def _no_backends_msg(cls):
        return "no BCrypt backends available - please install pybcrypt for BCrypt support"

    def _calc_checksum_os_crypt(self, secret):
        if isinstance(secret, unicode):
            secret = secret.encode("utf-8")
        return os_crypt(secret, self.to_string())[-31:]

    def _calc_checksum_pybcrypt(self, secret):
        if isinstance(secret, unicode):
            secret = secret.encode("utf-8")
        return pybcrypt_hashpw(secret, self.to_string())[-31:]

    #=========================================================
    #eoc
    #=========================================================

#=========================================================
#eof
#=========================================================
