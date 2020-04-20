# -*- coding: utf-8 -*-
"""
This module provides functions for encoding data for storage in Postgres
and decoding the results.
"""
from six import string_types
from six import integer_types as six_integers

import binascii
import json
import datetime

from psycopg2.extras import Json as pgJson
from psycopg2.extensions import adapt, ISQLQuote

def numeric_converter(value, cur=None):
    """
    Used for converting numeric values from Postgres to Python.

    INPUT:

    - ``value`` -- a string representing a decimal number.
    - ``cur`` -- a cursor, unused

    OUTPUT:

    - either a sage integer (if there is no decimal point) or a real number whose precision depends on the number of digits in value.
    """
    if value is None:
        return None
    if "." in value:
        # The following is a good guess for the bit-precision,
        # but we use LmfdbRealLiterals to ensure that our number
        # prints the same as we got it.
        prec = ceil(len(value) * 3.322)
        return LmfdbRealLiteral(RealField(prec), value)
    else:
        return Integer(value)


class Array(object):
    """
    Since we use Json by default for lists, this class lets us
    get back the original behavior of encoding as a Postgres array when needed.
    """

    def __init__(self, seq):
        self._seq = seq
        self._conn = None

    def __conform__(self, protocol):
        if protocol == ISQLQuote:
            return self
        else:
            raise NotImplementedError

    def prepare(self, conn):
        self._conn = conn

    def getquoted(self):
        # this is the important line: note how every object in the
        # list is adapted and then how getquoted() is called on it
        pobjs = [adapt(o) for o in self._seq]
        if self._conn is not None:
            for obj in pobjs:
                if hasattr(obj, "prepare"):
                    obj.prepare(self._conn)
        qobjs = [o.getquoted() for o in pobjs]
        return b"ARRAY[" + b", ".join(qobjs) + b"]"

    def __str__(self):
        return str(self.getquoted())


class RealEncoder(object):
    def __init__(self, value):
        self._value = value

    def getquoted(self):
        if isinstance(self._value, RealLiteral):
            return self._value.literal
        else:
            return str(self._value)

    def __str__(self):
        return self.getquoted()


class Json(pgJson):
    @classmethod
    def dumps(cls, obj):
        return json.dumps(cls.prep(obj))

    @classmethod
    def loads(cls, s):
        return cls.extract(json.loads(s))

    @classmethod
    def prep(cls, obj, escape_backslashes=False):
        """
        Returns a version of the object that is parsable by the standard json dumps function.
        For example, replace Integers with ints, encode various Sage types using dictionaries....
        """
        # For now we just hard code the encoding.
        # It would be nice to have something more abstracted/systematic eventually
        if isinstance(obj, tuple):
            return cls.prep(list(obj), escape_backslashes)
        elif isinstance(obj, list):
            # Lists of complex numbers occur, and we'd like to save space
            # We currently only support Python's complex numbers
            # but support for Sage complex numbers would be easy to add
            return [cls.prep(x, escape_backslashes) for x in obj]
        elif isinstance(obj, dict):
            if all(isinstance(k, string_types) for k in obj):
                return {k: cls.prep(v, escape_backslashes) for k, v in obj.items()}
            else:
                raise TypeError("keys must be strings or integers")

        elif escape_backslashes and isinstance(obj, string_types):
            # For use in copy_dumps below
            return (
                obj.replace("\\", "\\\\")
                .replace("\r", r"\r")
                .replace("\n", r"\n")
                .replace("\t", r"\t")
                .replace('"', r"\"")
            )
        elif obj is None:
            return None
        elif isinstance(obj, datetime.date):
            return {"__date__": 0, "data": "%s" % (obj)}
        elif isinstance(obj, datetime.time):
            return {"__time__": 0, "data": "%s" % (obj)}
        elif isinstance(obj, datetime.datetime):
            return {"__datetime__": 0, "data": "%s" % (obj)}
        elif isinstance(obj, (string_types, bool, float) + six_integers):
            return obj
        else:
            raise ValueError("Unsupported type: %s" % (type(obj)))

    @classmethod
    def _extract(cls, parent, obj):
        if parent is ZZ:
            return ZZ(obj)
        elif parent is QQ:
            return QQ(tuple(obj))
        elif isinstance(parent, NumberField_generic):
            base = parent.base_ring()
            obj = [cls._extract(base, c) for c in obj]
            return parent(obj)
        else:
            raise NotImplementedError("Cannot extract element of %s" % (parent))

    @classmethod
    def extract(cls, obj):
        """
        Takes an object extracted by the json parser and decodes the
        special-formating dictionaries used to store special types.
        """
        if isinstance(obj, dict) and "data" in obj:
            if len(obj) == 2 and "__date__" in obj:
                return datetime.datetime.strptime(obj["data"], "%Y-%m-%d").date()
            elif len(obj) == 2 and "__time__" in obj:
                return datetime.datetime.strptime(obj["data"], "%H:%M:%S.%f").time()
            elif len(obj) == 2 and "__datetime__" in obj:
                return datetime.datetime.strptime(obj["data"], "%Y-%m-%d %H:%M:%S.%f")
        return obj


def copy_dumps(inp, typ, recursing=False):
    """
    Output a string formatted as needed for loading by Postgres' COPY FROM.

    INPUT:

    - ``inp`` -- a Python or Sage object that directly translates to a postgres type (e.g. Integer, RealLiteral, dict...
    - ``typ`` -- the Postgres type of the column in which this data is being stored.
    """
    if inp is None:
        return u"\\N"
    elif typ in ("text", "char", "varchar"):
        if not isinstance(inp, string_types):
            inp = str(inp)
        inp = (
            inp.replace("\\", "\\\\")
            .replace("\r", r"\r")
            .replace("\n", r"\n")
            .replace("\t", r"\t")
            .replace('"', r"\"")
        )
        if recursing and ("{" in inp or "}" in inp):
            inp = '"' + inp + '"'
        return inp
    elif typ in ("json", "jsonb"):
        return json.dumps(Json.prep(inp, escape_backslashes=True))
    elif typ[-2:] == "[]":
        if not isinstance(inp, (list, tuple)):
            raise TypeError("You must use list or tuple for array columns")
        if not inp:
            return "{}"
        subtyp = None
        sublen = None
        for x in inp:
            if isinstance(x, (list, tuple)):
                if subtyp is None:
                    subtyp = typ
                elif subtyp != typ:
                    raise ValueError("Array dimensions must be uniform")
                if sublen is None:
                    sublen = len(x)
                elif sublen != len(x):
                    raise ValueError("Array dimensions must be uniform")
            elif subtyp is None:
                subtyp = typ[:-2]
            elif subtyp != typ[:-2]:
                raise ValueError("Array dimensions must be uniform")
        return "{" + ",".join(copy_dumps(x, subtyp, recursing=True) for x in inp) + "}"
    elif isinstance(inp, RealLiteral):
        return inp.literal
    elif isinstance(inp, (Integer, float, RealNumber) + six_integers):
        return str(inp).replace("L", "")
    elif typ == "boolean":
        return "t" if inp else "f"
    elif isinstance(inp, (datetime.date, datetime.time, datetime.datetime)):
        return "%s" % (inp)
    elif typ == "bytea":
        return r"\\x" + "".join(binascii.hexlify(c) for c in inp)
    else:
        raise TypeError("Invalid input %s (%s) for postgres type %s" % (inp, type(inp), typ))
