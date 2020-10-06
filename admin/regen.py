"""
helper script which rebuilds all autogenerated bits of code w/in passlib.
"""
#=============================================================================
# imports
#=============================================================================
# core
import datetime
import re
import os
# all
__all__ = [
    "main",
    "replace_section",
]

#=============================================================================
# helpers
#=============================================================================

now = datetime.datetime.now().strftime("%Y-%m-%d")

def replace_section(data, ident, content):
    """
    helper to replace autogenerated section of content.

    :param data:
        existing file contents

    :param ident:
        identifying string for section start and end.
        will look for "begin <ident>" section marker,
        and "end <ident>" section marker.

    :param content:
        replacement content to replace whatever's present
        between section start & end.

    :returns:
        modified data
    """
    m = re.match(r"""(?ixms)
        (?P<head>.*?\n)
        \#[-=]{10,}\n
        \# \s begin \s* %(ident)s .* \n
        \#[-=]{10,}\n
        .*?
        \#[-=]{10,}\n
        \# \s end \s* %(ident)s \s* \n
        \#[-=]{10,}\n
        (?P<tail>.*)
    """ % dict(ident=re.escape(ident).replace("\\ ", "\\s+"),),
                 data.replace("\r\n", "\n"))
    assert m, "%r section not found" % (ident,)

    begin_row = "# begin " + ident + " (autogenerated " + now + ")\n"

    head, tail = m.group("head", "tail")
    divline = "#" + "-" * max(40, len(begin_row) - 1) + "\n"
    return "".join([
        head,
        divline,
        begin_row,
        divline,
        content,
        divline,
        "# end ", ident, "\n",
        divline,
        tail,
        ])

#=============================================================================
# main
#=============================================================================

from passlib.hash import sha256_crypt

source_dir = os.path.abspath(os.path.join(__file__, *[".."]*2))

def main():
    """rebuild autogenerated sections in passlib"""

    #------------------------------------------------
    # rebuild autocomplete helper in passlib/hash.py
    #------------------------------------------------
    content = "if False:\n"
    from passlib.registry import _locations
    modules = {}
    for name, path in _locations.items():
        modules.setdefault(path, []).append(name)
    for path, names in sorted(modules.items()):
        row = "    from %s import %s\n" % (path, ", ".join(sorted(names)))
        content += row

    hash_path = os.path.join(source_dir, "passlib", "hash.py")
    data = open(hash_path).read()
    data = replace_section(data, "autocomplete hack", content)
    open(hash_path, "w").write(data)

if __name__ == "__main__":
    main()

#=============================================================================
# eof
#=============================================================================
