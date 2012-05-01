"""passlib.handlers.postgres_md5 - MD5-based algorithm used by Postgres for pg_shadow table"""
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
#pkg
from passlib.utils import to_bytes
from passlib.utils.compat import b, bytes, str_to_uascii, unicode, u
import passlib.utils.handlers as uh
#local
__all__ = [
    "postgres_md5",
]

#=========================================================
#handler
#=========================================================
class postgres_md5(uh.HasUserContext, uh.StaticHandler):
    """This class implements the Postgres MD5 Password hash, and follows the :ref:`password-hash-api`.

    It does a single round of hashing, and relies on the username as the salt.

    The :meth:`~passlib.ifc.PasswordHash.encrypt`, :meth:`~passlib.ifc.PasswordHash.genhash`, and :meth:`~passlib.ifc.PasswordHash.verify` methods all require the
    following additional contextual keywords:

    :type user: str
    :param user: name of postgres user account this password is associated with.
    """
    #=========================================================
    # algorithm information
    #=========================================================
    name = "postgres_md5"
    _hash_prefix = u("md5")
    checksum_chars = uh.HEX_CHARS
    checksum_size = 32

    #=========================================================
    # primary interface
    #=========================================================
    def _calc_checksum(self, secret):
        if isinstance(secret, unicode):
            secret = secret.encode("utf-8")
        user = to_bytes(self.user, "utf-8", param="user")
        return str_to_uascii(md5(secret + user).hexdigest())

    #=========================================================
    #eoc
    #=========================================================

#=========================================================
#eof
#=========================================================
