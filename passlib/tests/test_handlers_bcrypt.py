"""passlib.tests.test_handlers_bcrypt - tests for passlib hash algorithms"""
#=============================================================================
# imports
#=============================================================================
from __future__ import with_statement
# core
import hashlib
import logging; log = logging.getLogger(__name__)
import os
import sys
import warnings
# site
# pkg
from passlib import hash
from passlib.utils import repeat_string
from passlib.utils.compat import irange, PY3, u, get_method_function
from passlib.tests.utils import TestCase, HandlerCase, skipUnless, \
        TEST_MODE, b, catch_warnings, UserHandlerMixin, randintgauss, EncodingHandlerMixin
from passlib.tests.test_handlers import UPASS_WAV, UPASS_USD, UPASS_TABLE
# module

#=============================================================================
# bcrypt
#=============================================================================
class _bcrypt_test(HandlerCase):
    "base for BCrypt test cases"
    handler = hash.bcrypt
    secret_size = 72
    reduce_default_rounds = True

    known_correct_hashes = [
        #
        # from JTR 1.7.9
        #
        ('U*U*U*U*', '$2a$05$c92SVSfjeiCD6F2nAD6y0uBpJDjdRkt0EgeC4/31Rf2LUZbDRDE.O'),
        ('U*U***U', '$2a$05$WY62Xk2TXZ7EvVDQ5fmjNu7b0GEzSzUXUh2cllxJwhtOeMtWV3Ujq'),
        ('U*U***U*', '$2a$05$Fa0iKV3E2SYVUlMknirWU.CFYGvJ67UwVKI1E2FP6XeLiZGcH3MJi'),
        ('*U*U*U*U', '$2a$05$.WRrXibc1zPgIdRXYfv.4uu6TD1KWf0VnHzq/0imhUhuxSxCyeBs2'),
        ('', '$2a$05$Otz9agnajgrAe0.kFVF9V.tzaStZ2s1s4ZWi/LY4sw2k/MTVFj/IO'),

        #
        # test vectors from http://www.openwall.com/crypt v1.2
        # note that this omits any hashes that depend on crypt_blowfish's
        # various CVE-2011-2483 workarounds (hash 2a and \xff\xff in password,
        # and any 2x hashes); and only contain hashes which are correct
        # under both crypt_blowfish 1.2 AND OpenBSD.
        #
        ('U*U', '$2a$05$CCCCCCCCCCCCCCCCCCCCC.E5YPO9kmyuRGyh0XouQYb4YMJKvyOeW'),
        ('U*U*', '$2a$05$CCCCCCCCCCCCCCCCCCCCC.VGOzA784oUp/Z0DY336zx7pLYAy0lwK'),
        ('U*U*U', '$2a$05$XXXXXXXXXXXXXXXXXXXXXOAcXxm9kjPGEMsLznoKqmqw7tc8WCx4a'),
        ('', '$2a$05$CCCCCCCCCCCCCCCCCCCCC.7uG0VCzI2bS7j6ymqJi9CdcdxiRTWNy'),
        ('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
         '0123456789chars after 72 are ignored',
                '$2a$05$abcdefghijklmnopqrstuu5s2v8.iXieOjg/.AySBTTZIIVFJeBui'),
        (b('\xa3'),
                '$2a$05$/OK.fbVrR/bpIqNJ5ianF.Sa7shbm4.OzKpvFnX1pQLmQW96oUlCq'),
        (b('\xff\xa3345'),
            '$2a$05$/OK.fbVrR/bpIqNJ5ianF.nRht2l/HRhr6zmCp9vYUvvsqynflf9e'),
        (b('\xa3ab'),
                '$2a$05$/OK.fbVrR/bpIqNJ5ianF.6IflQkJytoRVc1yuaNtHfiuq.FRlSIS'),
        (b('\xaa')*72 + b('chars after 72 are ignored as usual'),
                '$2a$05$/OK.fbVrR/bpIqNJ5ianF.swQOIzjOiJ9GHEPuhEkvqrUyvWhEMx6'),
        (b('\xaa\x55'*36),
                '$2a$05$/OK.fbVrR/bpIqNJ5ianF.R9xrDjiycxMbQE2bp.vgqlYpW5wx2yy'),
        (b('\x55\xaa\xff'*24),
                '$2a$05$/OK.fbVrR/bpIqNJ5ianF.9tQZzcJfm3uj2NvJ/n5xkhpqLrMpWCe'),

        # keeping one of their 2y tests, because we are supporting that.
        (b('\xa3'),
                '$2y$05$/OK.fbVrR/bpIqNJ5ianF.Sa7shbm4.OzKpvFnX1pQLmQW96oUlCq'),

        #
        # from py-bcrypt tests
        #
        ('', '$2a$06$DCq7YPn5Rq63x1Lad4cll.TV4S6ytwfsfvkgY8jIucDrjc8deX1s.'),
        ('a', '$2a$10$k87L/MF28Q673VKh8/cPi.SUl7MU/rWuSiIDDFayrKk/1tBsSQu4u'),
        ('abc', '$2a$10$WvvTPHKwdBJ3uk0Z37EMR.hLA2W6N9AEBhEgrAOljy2Ae5MtaSIUi'),
        ('abcdefghijklmnopqrstuvwxyz',
                '$2a$10$fVH8e28OQRj9tqiDXs1e1uxpsjN0c7II7YPKXua2NAKYvM6iQk7dq'),
        ('~!@#$%^&*()      ~!@#$%^&*()PNBFRD',
                '$2a$10$LgfYWkbzEvQ4JakH7rOvHe0y8pHKF9OaFgwUZ2q7W2FFZmZzJYlfS'),

        #
        # custom test vectors
        #

        # ensures utf-8 used for unicode
        (UPASS_TABLE,
                '$2a$05$Z17AXnnlpzddNUvnC6cZNOSwMA/8oNiKnHTHTwLlBijfucQQlHjaG'),
        ]

    if TEST_MODE("full"):
        #
        # add some extra tests related to 2/2a
        #
        CONFIG_2 = '$2$05$' + '.'*22
        CONFIG_A = '$2a$05$' + '.'*22
        known_correct_hashes.extend([
            ("", CONFIG_2 + 'J2ihDv8vVf7QZ9BsaRrKyqs2tkn55Yq'),
            ("", CONFIG_A + 'J2ihDv8vVf7QZ9BsaRrKyqs2tkn55Yq'),
            ("abc", CONFIG_2 + 'XuQjdH.wPVNUZ/bOfstdW/FqB8QSjte'),
            ("abc", CONFIG_A + 'ev6gDwpVye3oMCUpLY85aTpfBNHD0Ga'),
            ("abc"*23, CONFIG_2 + 'XuQjdH.wPVNUZ/bOfstdW/FqB8QSjte'),
            ("abc"*23, CONFIG_A + '2kIdfSj/4/R/Q6n847VTvc68BXiRYZC'),
            ("abc"*24, CONFIG_2 + 'XuQjdH.wPVNUZ/bOfstdW/FqB8QSjte'),
            ("abc"*24, CONFIG_A + 'XuQjdH.wPVNUZ/bOfstdW/FqB8QSjte'),
            ("abc"*24+'x', CONFIG_2 + 'XuQjdH.wPVNUZ/bOfstdW/FqB8QSjte'),
            ("abc"*24+'x', CONFIG_A + 'XuQjdH.wPVNUZ/bOfstdW/FqB8QSjte'),
        ])

    known_correct_configs = [
        ('$2a$04$uM6csdM8R9SXTex/gbTaye', UPASS_TABLE,
         '$2a$04$uM6csdM8R9SXTex/gbTayezuvzFEufYGd2uB6of7qScLjQ4GwcD4G'),
    ]

    known_unidentified_hashes = [
        # invalid minor version
        "$2b$12$EXRkfkdmXnagzds2SSitu.MW9.gAVqa9eLS1//RYtYCmB1eLHg.9q",
        "$2`$12$EXRkfkdmXnagzds2SSitu.MW9.gAVqa9eLS1//RYtYCmB1eLHg.9q",
    ]

    known_malformed_hashes = [
        # bad char in otherwise correct hash
        #                 \/
        "$2a$12$EXRkfkdmXn!gzds2SSitu.MW9.gAVqa9eLS1//RYtYCmB1eLHg.9q",

        # unsupported (but recognized) minor version
        "$2x$12$EXRkfkdmXnagzds2SSitu.MW9.gAVqa9eLS1//RYtYCmB1eLHg.9q",

        # rounds not zero-padded (py-bcrypt rejects this, therefore so do we)
        '$2a$6$DCq7YPn5Rq63x1Lad4cll.TV4S6ytwfsfvkgY8jIucDrjc8deX1s.'

        # NOTE: salts with padding bits set are technically malformed,
        #      but we can reliably correct & issue a warning for that.
        ]

    platform_crypt_support = [
        ("freedbsd|openbsd|netbsd", True),
        ("darwin", False),
        # linux - may be present via addon, e.g. debian's libpam-unix2
        # solaris - depends on policy
    ]

    #===================================================================
    # override some methods
    #===================================================================
    def setUp(self):
        # ensure builtin is enabled for duration of test.
        if TEST_MODE("full") and self.backend == "builtin":
            key = "PASSLIB_BUILTIN_BCRYPT"
            orig = os.environ.get(key)
            if orig:
                self.addCleanup(os.environ.__setitem__, key, orig)
            else:
                self.addCleanup(os.environ.__delitem__, key)
            os.environ[key] = "enabled"
        super(_bcrypt_test, self).setUp()

    def populate_settings(self, kwds):
        # builtin is still just way too slow.
        if self.backend == "builtin":
            kwds.setdefault("rounds", 4)
        super(_bcrypt_test, self).populate_settings(kwds)

    #===================================================================
    # fuzz testing
    #===================================================================
    def os_supports_ident(self, hash):
        "check if OS crypt is expected to support given ident"
        if hash is None:
            return True
        # most OSes won't support 2x/2y
        # XXX: definitely not the BSDs, but what about the linux variants?
        from passlib.handlers.bcrypt import IDENT_2X, IDENT_2Y
        if hash.startswith(IDENT_2X) or hash.startswith(IDENT_2Y):
            return False
        return True

    def fuzz_verifier_bcrypt(self):
        # test against bcrypt, if available
        from passlib.handlers.bcrypt import IDENT_2, IDENT_2A, IDENT_2X, IDENT_2Y
        from passlib.utils import to_native_str, to_bytes
        try:
            import bcrypt
        except ImportError:
            return
        if not hasattr(bcrypt, "_ffi"):
            return
        def check_bcrypt(secret, hash):
            "bcrypt"
            secret = to_bytes(secret, self.fuzz_password_encoding)
            #if hash.startswith(IDENT_2Y):
            #    hash = IDENT_2A + hash[4:]
            if hash.startswith(IDENT_2):
                # bcryptor doesn't support $2$ hashes; but we can fake it
                # using the $2a$ algorithm, by repeating the password until
                # it's 72 chars in length.
                hash = IDENT_2A + hash[3:]
                if secret:
                    secret = repeat_string(secret, 72)
            hash = to_bytes(hash)
            try:
                return bcrypt.hashpw(secret, hash) == hash
            except ValueError:
                raise ValueError("bcrypt rejected hash: %r" % (hash,))
        return check_bcrypt

    def fuzz_verifier_pybcrypt(self):
        # test against py-bcrypt, if available
        from passlib.handlers.bcrypt import IDENT_2, IDENT_2A, IDENT_2X, IDENT_2Y
        from passlib.utils import to_native_str
        try:
            import bcrypt
        except ImportError:
            return
        if hasattr(bcrypt, "_ffi"):
            return
        def check_pybcrypt(secret, hash):
            "pybcrypt"
            secret = to_native_str(secret, self.fuzz_password_encoding)
            if hash.startswith(IDENT_2Y):
                hash = IDENT_2A + hash[4:]
            try:
                return bcrypt.hashpw(secret, hash) == hash
            except ValueError:
                raise ValueError("py-bcrypt rejected hash: %r" % (hash,))
        return check_pybcrypt

    def fuzz_verifier_bcryptor(self):
        # test against bcryptor, if available
        from passlib.handlers.bcrypt import IDENT_2, IDENT_2A, IDENT_2Y
        from passlib.utils import to_native_str
        try:
            from bcryptor.engine import Engine
        except ImportError:
            return
        def check_bcryptor(secret, hash):
            "bcryptor"
            secret = to_native_str(secret, self.fuzz_password_encoding)
            if hash.startswith(IDENT_2Y):
                hash = IDENT_2A + hash[4:]
            elif hash.startswith(IDENT_2):
                # bcryptor doesn't support $2$ hashes; but we can fake it
                # using the $2a$ algorithm, by repeating the password until
                # it's 72 chars in length.
                hash = IDENT_2A + hash[3:]
                if secret:
                    secret = repeat_string(secret, 72)
            return Engine(False).hash_key(secret, hash) == hash
        return check_bcryptor

    def get_fuzz_settings(self):
        secret, other, kwds = super(_bcrypt_test,self).get_fuzz_settings()
        from passlib.handlers.bcrypt import IDENT_2, IDENT_2X
        from passlib.utils import to_bytes
        ident = kwds.get('ident')
        if ident == IDENT_2X:
            # 2x is just recognized, not supported. don't test with it.
            del kwds['ident']
        elif ident == IDENT_2 and repeat_string(to_bytes(other), len(to_bytes(secret))) == to_bytes(secret):
            # avoid false failure due to flaw in 0-revision bcrypt:
            # repeated strings like 'abc' and 'abcabc' hash identically.
            other = self.get_fuzz_password()
        return secret, other, kwds

    def fuzz_setting_rounds(self):
        # decrease default rounds for fuzz testing to speed up volume.
        return randintgauss(5, 8, 6, 1)

    #===================================================================
    # custom tests
    #===================================================================
    known_incorrect_padding = [
        # password, bad hash, good hash

        # 2 bits of salt padding set
#        ("loppux",                  # \/
#         "$2a$12$oaQbBqq8JnSM1NHRPQGXORm4GCUMqp7meTnkft4zgSnrbhoKdDV0C",
#         "$2a$12$oaQbBqq8JnSM1NHRPQGXOOm4GCUMqp7meTnkft4zgSnrbhoKdDV0C"),
        ("test",                    # \/
         '$2a$04$oaQbBqq8JnSM1NHRPQGXORY4Vw3bdHKLIXTecPDRAcJ98cz1ilveO',
         '$2a$04$oaQbBqq8JnSM1NHRPQGXOOY4Vw3bdHKLIXTecPDRAcJ98cz1ilveO'),

        # all 4 bits of salt padding set
#        ("Passlib11",               # \/
#         "$2a$12$M8mKpW9a2vZ7PYhq/8eJVcUtKxpo6j0zAezu0G/HAMYgMkhPu4fLK",
#         "$2a$12$M8mKpW9a2vZ7PYhq/8eJVOUtKxpo6j0zAezu0G/HAMYgMkhPu4fLK"),
        ("test",                    # \/
         "$2a$04$yjDgE74RJkeqC0/1NheSScrvKeu9IbKDpcQf/Ox3qsrRS/Kw42qIS",
         "$2a$04$yjDgE74RJkeqC0/1NheSSOrvKeu9IbKDpcQf/Ox3qsrRS/Kw42qIS"),

        # bad checksum padding
        ("test",                                                   # \/
         "$2a$04$yjDgE74RJkeqC0/1NheSSOrvKeu9IbKDpcQf/Ox3qsrRS/Kw42qIV",
         "$2a$04$yjDgE74RJkeqC0/1NheSSOrvKeu9IbKDpcQf/Ox3qsrRS/Kw42qIS"),
    ]

    def test_90_bcrypt_padding(self):
        "test passlib correctly handles bcrypt padding bits"
        self.require_TEST_MODE("full")
        #
        # prevents reccurrence of issue 25 (https://code.google.com/p/passlib/issues/detail?id=25)
        # were some unused bits were incorrectly set in bcrypt salt strings.
        # (fixed since 1.5.3)
        #
        bcrypt = self.handler
        corr_desc = ".*incorrectly set padding bits"

        #
        # test encrypt() / genconfig() don't generate invalid salts anymore
        #
        def check_padding(hash):
            assert hash.startswith("$2a$") and len(hash) >= 28
            self.assertTrue(hash[28] in '.Oeu',
                            "unused bits incorrectly set in hash: %r" % (hash,))
        for i in irange(6):
            check_padding(bcrypt.genconfig())
        for i in irange(3):
            check_padding(bcrypt.encrypt("bob", rounds=bcrypt.min_rounds))

        #
        # test genconfig() corrects invalid salts & issues warning.
        #
        with self.assertWarningList(["salt too large", corr_desc]):
            hash = bcrypt.genconfig(salt="."*21 + "A.", rounds=5, relaxed=True)
        self.assertEqual(hash, "$2a$05$" + "." * 22)

        #
        # make sure genhash() corrects input
        #
        samples = self.known_incorrect_padding
        for pwd, bad, good in samples:
            with self.assertWarningList([corr_desc]):
                self.assertEqual(bcrypt.genhash(pwd, bad), good)
            with self.assertWarningList([]):
                self.assertEqual(bcrypt.genhash(pwd, good), good)

        #
        # and that verify() works good & bad
        #
        with self.assertWarningList([corr_desc]):
            self.assertTrue(bcrypt.verify(pwd, bad))
        with self.assertWarningList([]):
            self.assertTrue(bcrypt.verify(pwd, good))

        #
        # test normhash cleans things up correctly
        #
        for pwd, bad, good in samples:
            with self.assertWarningList([corr_desc]):
                self.assertEqual(bcrypt.normhash(bad), good)
            with self.assertWarningList([]):
                self.assertEqual(bcrypt.normhash(good), good)
        self.assertEqual(bcrypt.normhash("$md5$abc"), "$md5$abc")

hash.bcrypt._no_backends_msg() # call this for coverage purposes

# create test cases for specific backends
bcrypt_bcrypt_test, bcrypt_pybcrypt_test, bcrypt_bcryptor_test, bcrypt_os_crypt_test, bcrypt_builtin_test = \
               _bcrypt_test.create_backend_cases(["bcrypt", "pybcrypt", "bcryptor", "os_crypt", "builtin"])

#=============================================================================
# eof
#=============================================================================
