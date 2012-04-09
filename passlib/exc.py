"""passlib.exc -- exceptions & warnings raised by passlib"""
#==========================================================================
# exceptions
#==========================================================================
class MissingBackendError(RuntimeError):
    """Error raised if multi-backend handler has no available backends;
    or if specifically requested backend is not available.

    :exc:`!MissingBackendError` derives
    from :exc:`RuntimeError`, since this usually indicates
    lack of an external library or OS feature.

    This is primarily used by handlers which derive
    from :class:`~passlib.utils.handlers.HasManyBackends`.
    """

class PasswordSizeError(ValueError):
    """Error raised if the password provided exceeds the limit set by Passlib.

    Many password hashes take proportionately larger amounts of
    time and/or memory depending on the size of the password provided.
    This could present a potential denial of service (DOS) situation
    if a maliciously large password was provided to the application.

    Because of this, Passlib enforces a maximum of 4096 characters.
    This error will be thrown if a password larger than
    this is provided to any of the hashes in Passlib.

    Applications wishing to use a different limit should set the
    ``PASSLIB_MAX_PASSWORD_SIZE`` environmental variable before Passlib
    is loaded.
    """
    def __init__(self):
        ValueError.__init__(self, "password exceeds maximum allowed size")

    # this also prevents a glibc crypt segfault issue, detailed here ...
    # http://www.openwall.com/lists/oss-security/2011/11/15/1

#==========================================================================
# warnings
#==========================================================================
class PasslibWarning(UserWarning):
    """base class for Passlib's user warnings"""

class PasslibConfigWarning(PasslibWarning):
    """Warning issued when non-fatal issue is found related to the configuration
    of a :class:`~passlib.context.CryptContext` instance.

    This occurs primarily in one of two cases:

    * the policy contains rounds limits which exceed the hard limits
      imposed by the underlying algorithm.
    * an explicit rounds value was provided which exceeds the limits
      imposed by the policy.

    In both of these cases, the code will perform correctly & securely;
    but the warning is issued as a sign the configuration may need updating.
    """

class PasslibHashWarning(PasslibWarning):
    """Warning issued when non-fatal issue is found with parameters
    or hash string passed to a passlib hash class.

    This occurs primarily in one of two cases:

    * a rounds value or other setting was explicitly provided which
      exceeded the handler's limits (and has been clamped).

    * a hash malformed hash string was encountered, which while parsable,
      should be re-encoded.
    """

class PasslibRuntimeWarning(PasslibWarning):
    """Warning issued when something unexpected happens during runtime.

    The fact that it's a warning instead of an error means Passlib
    was able to correct for the issue, but that it's anonmalous enough
    that the developers would love to hear under what conditions it occurred.
    """

class PasslibSecurityWarning(PasslibWarning):
    """Special warning issued when Passlib encounters something
    that might affect security.

    The main reason this is issued is when Passlib's pure-python bcrypt
    backend is used, to warn that it's 20x too slow to acheive real security.
    """

#==========================================================================
# eof
#==========================================================================
