# -*- encoding: utf-8 -*-

## parse_newton_polygon and parse_abvar_decomp are defined in lmfdb.abvar.fq.search_parsing
from six.moves import range
from six import string_types

import re
from collections import Counter

from lmfdb.utils.utilities import flash_error

SPACES_RE = re.compile(r'\d\s+\d')
LIST_RE = re.compile(r'^(\d+|(\d*-(\d+)?))(,(\d+|(\d*-(\d+)?)))*$')
FLOAT_STR = r'((\d+([.]\d*)?)|([.]\d+))(e[-+]?\d+)?'
LIST_FLOAT_RE = re.compile(r'^({0}|{0}-|{0}-{0})(,({0}|{0}-|{0}-{0}))*$'.format(FLOAT_STR))
BRACKETED_POSINT_RE = re.compile(r'^\[\]|\[\d+(,\d+)*\]$')
BRACKETED_RAT_RE = re.compile(r'^\[\]|\[-?(\d+|\d+/\d+)(,-?(\d+|\d+/\d+))*\]$')
QQ_RE = re.compile(r'^-?\d+(/\d+)?$')
# Single non-negative rational, allowing decimals, used in parse_range2rat
QQ_DEC_RE = re.compile(r'^\d+((\.\d+)|(/\d+))?$')
LIST_POSINT_RE = re.compile(r'^(\d+)(,\d+)*$')
LIST_RAT_RE = re.compile(r'^((\d+((\.\d+)|(/\d+))?)|((\d+((\.\d+)|(/\d+))?)-((\d+((\.\d+)|(/\d+))?))?))(,((\d+((\.\d+)|(/\d+))?)|((\d+((\.\d+)|(/\d+))?)-(\d+((\.\d+)|(/\d+))?)?)))*$')
SIGNED_LIST_RE = re.compile(r'^(-?\d+|(-?\d+--?\d+))(,(-?\d+|(-?\d+--?\d+)))*$')
## RE from number_field.py
#LIST_SIMPLE_RE = re.compile(r'^(-?\d+)(,-?\d+)*$'
#PAIR_RE = re.compile(r'^\[\d+,\d+\]$')
#IF_RE = re.compile(r'^\[\]|(\[\d+(,\d+)*\])$')  # invariant factors
FLOAT_RE = re.compile('^' + FLOAT_STR + '$')
BRACKETING_RE = re.compile(r'(\[[^\]]*\])') # won't work for iterated brackets [[a,b],[c,d]]

class SearchParsingError(ValueError):
    """
    Used for errors raised when parsing search boxes
    """
    pass

class SearchParser(object):
    def __init__(self, f, clean_info, prep_ranges, prep_plus, pass_name, default_field, default_name, default_qfield, error_is_safe, clean_spaces):
        self.f = f
        self.clean_info = clean_info
        self.prep_ranges = prep_ranges
        self.prep_plus = prep_plus
        self.pass_name = pass_name
        self.default_field = default_field
        self.default_name = default_name
        self.default_qfield = default_qfield
        self.error_is_safe = error_is_safe # Indicates that the message in raised exception contains no user input, so it is not escaped
        self.clean_spaces = clean_spaces
    def __call__(self, info, query, field=None, name=None, qfield=None, *args, **kwds):
        try:
            if field is None: field=self.default_field
            inp = info.get(field)
            if not inp: return
            if name is None:
                if self.default_name is None:
                    name = field.replace('_',' ').capitalize()
                else:
                    name = self.default_name
            inp = str(inp)
            if SPACES_RE.search(inp):
                raise SearchParsingError("You have entered spaces in between digits. Please add a comma or delete the spaces.")
            inp = clean_input(inp, self.clean_spaces)
            if qfield is None:
                if field is None:
                    qfield = self.default_qfield
                else:
                    qfield = field
            if self.prep_ranges:
                inp = prep_ranges(inp)
            if self.prep_plus:
                inp = inp.replace('+','')
            if self.pass_name:
                self.f(inp, query, name, qfield, *args, **kwds)
            else:
                self.f(inp, query, qfield, *args, **kwds)
            if self.clean_info:
                info[field] = inp
        except (ValueError, AttributeError, TypeError) as err:
            if self.error_is_safe:
                flash_error("<span style='color:black'>%s</span> is not a valid input for <span style='color:black'>%s</span>. "+str(err)+".", inp, name)
            else:
                flash_error("<span style='color:black'>%s</span> is not a valid input for <span style='color:black'>%s</span>. %s", inp, name, str(err))
            info['err'] = ''
            raise

def search_parser(f, clean_info=False, prep_ranges=False, prep_plus=False, pass_name=False,
                  default_field=None, default_name=None, default_qfield=None, error_is_safe=False, clean_spaces=True):
    return SearchParser(f, clean_info, prep_ranges, prep_plus, pass_name, default_field, default_name, default_qfield, error_is_safe, clean_spaces)

# Remove whitespace for simpler parsing
# Remove brackets to avoid tricks (so we can echo it back safely)
def clean_input(inp, clean_spaces=True):
    if inp is None: return None
    if clean_spaces:
        return re.sub(r'[\s<>]', '', str(inp))
    else:
        return re.sub(r'[<>]', '', str(inp))
def prep_ranges(inp):
    if inp is None: return None
    return inp.replace('..','-').replace(' ','')

def prep_raw(inp, names={}):
    """
    Prepare an input string for being passed as a ``$raw`` value to the database search.

    INPUT:

    - ``inp`` -- a string from the website.  Aleady split up by commas and .. range indicators
    - ``names`` -- a dictionary providing a translation from user input to column names.  Only keys in the dictionary are accepted.

    OUTPUT:

    A string with implicit multiplications inserted and full column names substituted for short names

    This function will raise a SearchParsingError if there is a syntax error or if there is a variable that's not in the names list
    """
    inp = implicit_mul(inp, level=10) # level = 10 includes (a+b)(c+d) -> (a+b)*(c+d) which isn't safe in Sage but should be okay for us
    def filtered_var(s):
        if s not in names:
            raise SearchParsingError("%s is not a column of this table" % s)
        return var(s)
    # We use Sage's parser to make sure that the user input is well formed
    P = Parser(make_var=filtered_var)
    try:
        P.parse_expression(inp)
    except SyntaxError:
        raise SearchParsingError("syntax error")
    pieces = re.split(r'([A-Za-z_]+)', inp)
    processed = []
    for piece in pieces:
        if piece in names:
            processed.append(names[piece])
        else:
            processed.append(piece)
    return {'$raw': "".join(processed)}

# Various modules need to split a list of integers more simply
def split_list(s):
    s = s.replace(' ','')[1:-1]
    if s:
        return [int(a) for a in s.split(",")]
    return []

# This function can be used by modules to get a list of ints
# or an iterator (Python3 range) that matches the results of parse_ints below
# useful when a module wants to iterate over key values being
# passed into dictionary for postgres.  Input should be a string
def parse_ints_to_list(arg):
    if arg is None:
        return []
    s = str(arg)
    s = s.replace(' ','')
    if not s:
        return []
    if s[0] == '[' and s[-1] == ']':
        s = s[1:-1]
    if ',' in s:
        return [int(n) for n in s.split(',')]
    if '-' in s[1:]:
        i = s.index('-',1)
        min, max = s[:i], s[i+1:]
        return range(int(min),int(max)+1)
    if '..' in s:
        i = s.index('..',1)
        min, max = s[:i], s[i+2:]
        return range(int(min),int(max)+1)
    return [int(s)]

def parse_ints_to_list_flash(arg,name):
    try:
        return parse_ints_to_list(arg)
    except ValueError:
        flash_error("Error: <span style='color:black'>%s</span> is not a valid input for <span style='color:black'>%s</span>. It needs to be an integer (such as 25), a range of integers (such as 2-10 or 2..10), or a comma-separated list of these (such as 4,9,16 or 4-25, 81-121).", arg, name)
        raise

@search_parser # see SearchParser.__call__ for actual arguments when calling
def parse_list(inp, query, qfield, process=None):
    """
    Parses a string representing a list of integers, e.g. '[1,2,3]'

    Flashes an error and returns true if there are problems parsing.
    """
    cleaned = re.sub(r'[\[\]]','',inp)
    out= [int(a) for a in cleaned.split(',')]
    if process is not None:
        query[qfield] = process(out)
    else:
        query[qfield] = out

def parse_range(arg, parse_singleton=int, use_dollar_vars=True):
    # TODO: graceful errors
    if type(arg) == parse_singleton:
        return arg
    if ',' in arg:
        if use_dollar_vars:
            return {'$or': [parse_range(a) for a in arg.split(',')]}
        else:
            return [parse_range(a) for a in arg.split(',')]
    elif '-' in arg[1:]:
        ix = arg.index('-', 1)
        start, end = arg[:ix], arg[ix + 1:]
        q = {}
        if start:
            q['$gte' if use_dollar_vars else 'min'] = parse_singleton(start)
        if end:
            q['$lte' if use_dollar_vars else 'max'] = parse_singleton(end)
        return q
    else:
        return parse_singleton(arg)

# version above does not produce legal results when there is a comma
# to deal with $or, we return [key, value]
def parse_range2(arg, key, parse_singleton=int, parse_endpoint=None, split_minus=True):
    if parse_endpoint is None:
        parse_endpoint = parse_singleton
    if type(arg) == str:
        arg = arg.replace(' ', '')
    if type(arg) == parse_singleton:
        return [key, arg]
    if ',' in arg:
        tmp = [parse_range2(a, key, parse_singleton, parse_endpoint) for a in arg.split(',')]
        tmp = [{a[0]: a[1]} for a in tmp]
        return ['$or', tmp]
    elif '..' in arg[1:] or (split_minus and '-' in arg[1:]):
        if '..' in arg[1:]:
            ix = arg.index('..', 1)
            stop = ix + 2
        else:
            ix = arg.index('-', 1)
            stop = ix + 1
        start, end = arg[:ix], arg[stop:]
        q = {}
        if start:
            q['$gte'] = parse_endpoint(start)
        if end:
            q['$lte'] = parse_endpoint(end)
        return [key, q]
    else:
        return [key, parse_singleton(arg)]

# Like parse_range2, but to deal with strings which could be rational numbers
# process is a function to apply to arguments after they have been parsed
def parse_range2rat(arg, key, process):
    if type(arg) == str:
        arg = arg.replace(' ', '')
    if QQ_DEC_RE.match(arg):
        return [key, process(arg)]
    if ',' in arg:
        tmp = [parse_range2rat(a, key, process) for a in arg.split(',')]
        tmp = [{a[0]: a[1]} for a in tmp]
        return ['$or', tmp]
    elif '-' in arg[1:]:
        ix = arg.index('-', 1)
        start, end = arg[:ix], arg[ix + 1:]
        q = {}
        if start:
            q['$gte'] = process(start)
        if end:
            q['$lte'] = process(end)
        return [key, q]
    else:
        return [key, process(arg)]

# We parse into a list of singletons and pairs, like [[-5,-2], 10, 11, [16,100]]
# If split0, we split ranges [-a,b] that cross 0 into [-a, -1], [1, b]
def parse_range3(arg, split0 = False):
    if type(arg) == str:
        arg = arg.replace(' ', '')
    if ',' in arg:
        return sum([parse_range3(a, split0) for a in arg.split(',')],[])
    elif '-' in arg[1:]:
        ix = arg.index('-', 1)
        start, end = arg[:ix], arg[ix + 1:]
        if start:
            low = ZZ(str(start))
        else:
            raise SearchParsingError("It needs to be an integer (such as 25), a range of integers (such as 2-10 or 2..10), or a comma-separated list of these (such as 4,9,16 or 4-25, 81-121).")
        if end:
            high = ZZ(str(end))
        else:
            raise SearchParsingError("It needs to be an integer (such as 25), a range of integers (such as 2-10 or 2..10), or a comma-separated list of these (such as 4,9,16 or 4-25, 81-121).")
        if low == high: return [low]
        if split0 and low < 0 and high > 0:
            if low == -1: m = [low]
            else: m = [low,ZZ(-1)]
            if high == 1: p = [high]
            else: p = [ZZ(1),high]
            return [m,p]
        else:
            return [[low, high]]
    else:
        return [ZZ(str(arg))]

def integer_options(arg, max_opts=None, contained_in=None):
    intervals = parse_range3(arg)
    check = max_opts is not None and contained_in is None
    if check and len(intervals) > max_opts:
        raise ValueError("Too many options.")
    ans = set()
    for interval in intervals:
        if isinstance(interval, list):
            a,b = interval
            if check and len(ans) + b - a + 1 > max_opts:
                raise ValueError("Too many options")
            for n in range(a, b+1):
                if contained_in is None or n in contained_in:
                    ans.add(n)
        else:
            ans.add(int(interval))
        if max_opts is not None and len(ans) >= max_opts:
            raise ValueError("Too many options")
    return sorted(list(ans))

def collapse_ors(parsed, query):
    # work around syntax for $or
    # we have to foil out multiple or conditions
    if parsed[0] == '$or' and '$or' in query:
        newors = []
        for y in parsed[1]:
            oldors = [dict.copy(x) for x in query['$or']]
            for x in oldors:
                x.update(y)
            newors.extend(oldors)
        parsed[1] = newors
    query[parsed[0]] = parsed[1]

def _parse_subset(inp, query, qfield, mode, radical, product):
    def add_condition(kwd):
        if qfield in query:
            query[qfield][kwd] = inp
        else:
            query[qfield] = {kwd: inp}
    if mode == 'exclude':
        add_condition('$notcontains')
    elif mode == 'subset':
        # sadly, jsonb GIN indexes don't support <@, so we don't want to use
        # $containedin if we can help it.
        # Even more sadly, even switching to querying on the radical doesn't help,
        # since the query planner still uses an index scan on the primary key.
        #if len(inp) <= 5 and radical is not None:
        #    if radical in query:
        #        raise SearchParsingError("Cannot specify containment and equality simultaneously")
        #    query[radical] = {'$or': [product(X) for X in subsets(inp)]}
        #else:
        add_condition('$containedin')
    elif mode == 'include' or not mode: # include is the default
        add_condition('$contains')
    elif mode == 'exactly':
        if radical is not None:
            query[radical] = product(inp)
            return
        inp = sorted(inp)
        if inp:
            dup_free = [inp[0]]
            for i,x in enumerate(inp[1:]):
                if x != inp[i]:
                    dup_free.append(x)
        else:
            dup_free = []
        if qfield in query:
            raise SearchParsingError("Cannot specify containment and equality simultaneously")
        query[qfield] = dup_free
    else:
        raise ValueError("Unrecognized mode: programming error in LMFDB code")

def _multiset_code(n):
    # We encode multiplicities by appending consecutive letters: A, B,..., BA, BB, BC,...
    if n == 0:
        return 'A'
    return ''.join(chr(65+d) for d in reversed(ZZ(n).digits(26)))

def _multiset_encode(L):
    # L should be a list of strings
    distinguished = []
    seen = Counter()
    for x in L:
        distinguished.append(x + _multiset_code(seen[x]))
        seen[x] += 1
    return distinguished

def nf_string_to_label(FF):  # parse Q, Qsqrt2, Qsqrt-4, Qzeta5, etc
    if FF in ['q', 'Q']:
        return '1.1.1.1'
    if FF.lower() in ['qi', 'q(i)']:
        return '2.0.4.1'
    # Change unicode dash with minus sign
    FF = FF.replace(u'\u2212', '-')
    # remove non-ascii characters from F
    # we need to encode and decode for Python 3, as 'str' object has no attribute 'decode'
    # Remove non-ascii characters
    FF = re.sub(r'[^\x00-\x7f]', r'', FF)
    F = FF.lower() # keep original if needed
    if len(F) == 0:
        raise SearchParsingError("Entry for the field was left blank.  You need to enter a field label, field name, or a polynomial.")
    if F[0] == 'q':
        if '(' in F and ')' in F:
            F=F.replace('(','').replace(')','')
        if F[1:5] in ['sqrt', 'root']:
            try:
                d = ZZ(str(F[5:])).squarefree_part()
            except (TypeError, ValueError):
                d = 0
            if d == 0:
                raise SearchParsingError("After {0}, the remainder must be a nonzero integer.  Use {0}5 or {0}-11 for example.".format(FF[:5]))
            if d == 1:
                return '1.1.1.1'
            if d % 4 in [2, 3]:
                D = 4 * d
            else:
                D = d
            absD = D.abs()
            s = 0 if D < 0 else 2
            return '2.%s.%s.1' % (s, str(absD))
        if F[0:5] == 'qzeta':
            if '_' in F:
                F = F.replace('_','')
            match_obj = re.match(r'^qzeta(\d+)(\+|plus)?$', F)
            if not match_obj:
                raise SearchParsingError("After {0}, the remainder must be a positive integer or a positive integer followed by '+'.  Use {0}5 or {0}19+, for example.".format(F[:5]))

            d = ZZ(str(match_obj.group(1)))
            if d % 4 == 2:
                d /= 2  # Q(zeta_6)=Q(zeta_3), etc)

            if match_obj.group(2):  # asking for the totally real field
                from lmfdb.number_fields.web_number_field import rcyclolookup
                if d in rcyclolookup:
                    return rcyclolookup[d]
                else:
                    raise SearchParsingError('%s is not in the database.' % F)
            # Now not the totally real subfield
            from lmfdb.number_fields.web_number_field import cyclolookup
            if d in cyclolookup:
                return cyclolookup[d]
            else:
                raise SearchParsingError('%s is not in the database.' % F)
        raise SearchParsingError('It is not a valid field name or label, or a defining polynomial.')
    # check if a polynomial was entered
    F = F.replace('X', 'x')
    if 'x' in F:
        F1 = F.replace('^', '**')
        # print F
        from lmfdb.number_fields.number_field import poly_to_field_label
        F1 = poly_to_field_label(F1)
        if F1:
            return F1
        raise SearchParsingError('%s does not define a number field in the database.'%F)
    # Expand out factored labels, like 11.11.11e20.1
    if not re.match(r'\d+\.\d+\.[0-9e_]+\.\d+',F):
        raise SearchParsingError("A number field label must be of the form d.r.D.n, such as 2.2.5.1.")
    parts = F.split(".")
    def raise_power(ab):
        if ab.count("e") == 0:
            return ZZ(ab)
        elif ab.count("e") == 1:
            a,b = ab.split("e")
            return ZZ(a)**ZZ(b)
        else:
            raise SearchParsingError("Malformed absolute discriminant.  It must be a sequence of strings AeB for A and B integers, joined by _s.  For example, 2e7_3e5_11.")
    parts[2] = str(prod(raise_power(c) for c in parts[2].split("_")))
    return ".".join(parts)

# Similar to parsing a number field name, but with different output,
# here coefficients low to high separated by .,
# and different behavior if the entry is not in the database
def input_to_subfield(inp):
    def finish(result):
        return '.'.join([str(z) for z in result])

    def notq():
        raise SearchParsingError("The rational numbers $\Q$ cannot be a proper intermediate field.")

    # Change unicode dash with minus sign
    inp = inp.replace(u'\u2212', '-')

    # remove non-ascii characters from inp
    # we need to encode and decode for Python 3, as 'str' object has no attribute 'decode'
    inp = re.sub(r'[^\x00-\x7f]', r'', inp)
    if len(inp) == 0:
        return None

    # Do we have a nf label
    if re.match(r'\d+\.\d+\.[0-9e_]+\.\d+',inp):
        from lmfdb import db
        myfield = db.nf_fields.lookup(inp)
        if myfield:
            return finish(myfield['coeffs'])
        else:
            raise SearchParsingError("It is not the label for a subfield in the database.")

    F = inp.lower() # keep original if needed
    # Is it a polynomial
    if 'x' in F:
        F1 = F.replace('^', '**')
        R = PolynomialRing(ZZ, 'x')
        pol = PolynomialRing(QQ,'x')(str(F1))
        pol *= pol.denominator()
        if not pol.is_irreducible():
            raise SearchParsingError("It is not an irreducible polynomial.")
        coeffs = R(pari(pol).polredabs()).coefficients(sparse=False)
        if coeffs == [0,1]:
            notq()
        return finish(coeffs)
    # Nicknames
    if F == 'q':
        notq()
    if F in ['qi', 'q(i)']:
        return '1.0.1'
    if F[0] == 'q':
        if '(' in F and ')' in F:
            F=F.replace('(','').replace(')','')
            inp=inp.replace('(','').replace(')','')
        if F[1:5] in ['sqrt', 'root']:
            try:
                d = ZZ(str(F[5:])).squarefree_part()
            except (TypeError, ValueError):
                d = 0
            if d == 0 or d == 1:
                raise SearchParsingError("After {0}, the remainder must be a nonzero integer which is not a perfect square.  Use {0}5 or {0}-11 for example.".format(inp[:5]))
            # Recursion has it use polredabs to get the polynomial
            return input_to_subfield("x^2 - (%s)" % d)
        # Look for cyclotomic
        if F[0:5] == 'qzeta':
            if '_' in F:
                F = F.replace('_','')
            match_obj = re.match(r'^qzeta(\d+)(\+|plus)?$', F)
            if not match_obj:
                raise SearchParsingError("After {0}, the remainder must be a positive integer or a positive integer followed by '+'.  Use {0}5 or {0}19+, for example.".format(F[:5]))

            d = ZZ(str(match_obj.group(1)))
            if d % 4 == 2:
                d /= 2  # Q(zeta_6)=Q(zeta_3), etc)
            if d < 1:
                raise SearchParsingError("After {0}, the remainder must be a positive integer or a positive integer followed by '+'.  Use {0}5 or {0}19+, for example.".format(F[:5]))
            if d==1: # asking for Q
                notq()

            if match_obj.group(2):  # asking for the totally real field
                from lmfdb.number_fields.web_number_field import rcyclolookup
                if d < 5: # again, asking for subfield Q
                    notq()
                if d in rcyclolookup:
                    return input_to_subfield(rcyclolookup[d])
                else:
                    raise SearchParsingError("Subfield %s is not available." % F)
                f = pari.polcyclo(d)
                return input_to_subfield(str(f))
                # Want polcyclo here
                raise SearchParsingError('%s is not in the database.' % F)
            f = pari.polcyclo(d)
            return input_to_subfield(str(f))
    raise SearchParsingError('It is not a valid field nickname or label, or a defining polynomial.')

@search_parser # see SearchParser.__call__ for actual arguments when calling
def parse_subfield(inp, query, qfield):
    sf = input_to_subfield(inp)
    if sf: # Might return none
        query[qfield] = {'$contains': sf}


@search_parser # see SearchParser.__call__ for actual arguments when calling
def parse_nf_string(inp, query, qfield):
    query[qfield] = nf_string_to_label(inp)

def pol_string_to_list(pol, deg=None, var=None):
    if var is None:
        from lmfdb.hilbert_modular_forms.hilbert_field import findvar
        var = findvar(pol)
        if not var:
            var = 'a'
    pol = PolynomialRing(QQ, var)(str(pol))
    if deg is None:
        fill = 0
    else:
        fill = deg - pol.degree() - 1
    return [str(c) for c in pol.coefficients(sparse=False)] + ['0']*fill

@search_parser # see SearchParser.__call__ for actual arguments when calling
def parse_bool(inp, query, qfield, process=None, blank=[]):
    if inp in blank:
        return
    if process is None: process = lambda x: x
    if inp in ["True", "yes", "1", "even"]: # artin reps use parse_bool for an is_even parity field
        query[qfield] = process(True)
    elif inp in ["False", "no", "-1", "0", "odd"]:
        query[qfield] = process(False)
    elif inp == "Any":
        # On the Galois groups page, these indicate "All"
        pass
    else:
        raise SearchParsingError("It must be True or False.")

@search_parser # see SearchParser.__call__ for actual arguments when calling
def parse_bool_unknown(inp, query, qfield):
    # yes, no, not_no, not_yes, unknown
    if inp == 'yes':
        query[qfield] = 1
    elif inp == 'not_no':
        query[qfield] = {'$gt' : -1}
    elif inp == 'not_yes':
        query[qfield] = {'$lt' : 1}
    elif inp == 'no':
        query[qfield] = -1
    elif inp == 'unknown':
        query[qfield] = 0

@search_parser
def parse_restricted(inp, query, qfield, allowed, process=None, blank=[]):
    if inp in blank:
        return
    if process is None: process = lambda x: x
    allowed = [str(a) for a in allowed]
    if inp not in allowed:
        if len(allowed) == 0:
            allowed_str = "unspecified"
        if len(allowed) == 1:
            allowed_str = allowed[0]
        elif len(allowed) == 2:
            allowed_str = " or ".join(allowed)
        else:
            allowed_str = ", ".join(allowed[:-1]) + " or " + allowed[-1]
        raise SearchParsingError("It must be %s"%allowed_str)
    query[qfield] = process(inp)

@search_parser
def parse_noop(inp, query, qfield, func=None):
    if func is not None:
        inp = func(inp)
    query[qfield] = inp

@search_parser
def parse_equality_constraints(inp, query, qfield, prefix='a', parse_singleton=int, shift=0): # Note that postgres -> index is one-based
    for piece in inp.split(','):
        piece = piece.strip().split('=')
        if len(piece) != 2:
            raise SearchParsingError("It must be a comma separated list of expressions of the form %sN=T"%(prefix))
        n,t = piece
        n = n.strip()
        if not n.startswith(prefix):
            raise SearchParsingError("%s does not start with %s"%(n, prefix))
        n = int(n[len(prefix):]) + shift
        t = parse_singleton(t.strip())
        query[qfield + '.%s'%n] = t

def parse_paired_fields(info, query, field1=None, name1=None, qfield1=None, parse1=None, kwds1={},
                                     field2=None, name2=None, qfield2=None, parse2=None, kwds2={}):
    tmp_query1 = {}
    tmp_query2 = {}
    parse1(info,tmp_query1,field1,name1,qfield1,**kwds1)
    parse2(info,tmp_query2,field2,name2,qfield2,**kwds2)
    #print tmp_query1
    #print tmp_query2
    def remove_or(D):
        assert len(D) <= 1
        if '$or' in D: return D['$or']
        elif D: return [D]
        else: return []
    def combine(D1, D2):
        # For key='qfield',
        # Values can be singletons or a dict with keys '$lte' and '$gte' and values singletons.
        # For key='$or',
        # Values are lists of such dicts (with key qfield)
        # Analogous to collapse_ors, we update D2
        L1 = remove_or(D1)
        L2 = remove_or(D2)
        #print L1
        #print L2
        if not L1:
            return L2
        elif not L2:
            return L1
        else:
            return [{A.keys()[0]:A.values()[0], B.keys()[0]:B.values()[0]} for A in L1 for B in L2]
    L = combine(tmp_query1,tmp_query2)
    #print L
    if len(L) == 1:
        query.update(L[0])
    else:
        collapse_ors(['$or',L], query)

@search_parser
def parse_list_start(inp, query, qfield, index_shift=0, parse_singleton=int):
    bparts = BRACKETING_RE.split(inp)
    parts = []
    for part in bparts:
        if not part:
            continue
        if part[0] == '[':
            parts.append(part)
        else:
            subparts = part.split(',')
            for subpart in subparts:
                subpart = subpart.strip()
                if subpart:
                    parts.append(subpart)
    def make_sub_query(part):
        sub_query = {}
        if part[0] == '[':
            ispec = part[1:-1].split(',')
            for i, val in enumerate(ispec):
                key = qfield + '.' + str(i+index_shift)
                sub_query[key] = parse_range2(val, key, parse_singleton)[1]

            # MongoDB is not aware that all the queries above imply that qfield
            # must all contain all those elements, we aid MongoDB by explicitly
            # saying that, and hopefully it will use a multikey index.
            parsed_values = list(sub_query.values())
            # asking for each value to be in the array
            if parse_singleton is str:
                all_operand = [val for val in parsed_values if  type(val) == parse_singleton and '-' not in val and ','  not in val ]
            else:
                all_operand = [val for val in parsed_values if  type(val) == parse_singleton]

            if all_operand:
                sub_query[qfield] = {'$all' : all_operand}

            # if there are other condition, we can add the first of those
            # conditions the query, in the hope of reducing the search space
            elemMatch_operand = [val for val in parsed_values if type(val) != parse_singleton and type(val) is dict]
            if elemMatch_operand:
                if qfield in sub_query:
                    sub_query[qfield]['$elemMatch'] = elemMatch_operand[0]
                else:
                    sub_query[qfield] = {'$elemMatch' : elemMatch_operand[0]}
            # we could add more than one $elemMatch operand, but 
            # at the moment, the operator $all cannot handle other $ operators 
            # A workaround would be to wrap everything around with an $and
            # but that doesn't end up speeding up things. 
        else:
            key = qfield + '.' + str(index_shift)
            sub_query[key] = parse_range2(part, key, parse_singleton)[1]
        return sub_query
    if len(parts) == 1:
        query.update(make_sub_query(parts[0]))
    else:
        collapse_ors(['$or',[make_sub_query(part) for part in parts]], query)

@search_parser
def parse_string_start(inp, query, qfield, sep=" ", first_field=None, parse_singleton=int, initial_segment=[], names={}):
    def parse_one(x):
        ## Remember to add clean_spaces=True
        #if re.search(r'[A-Za-z]', x):
        #    return parse_range2(x, first_field, lambda inp: prep_raw(inp, names), split_minus=False)
        #else:
        return parse_range2(x, first_field, parse_singleton)
    bparts = BRACKETING_RE.split(inp)
    parts = []
    for part in bparts:
        if not part:
            continue
        if part[0] == '[':
            parts.append(part)
        else:
            subparts = part.split(',')
            for subpart in subparts:
                subpart = subpart.strip()
                if subpart:
                    parts.append(subpart)
    def make_sub_query(part):
        sub_query = {}
        part = part.strip()
        if not part:
            raise SearchParsingError("Every count specified must be nonempty.")
        if part[0] == '[':
            ispec = initial_segment + [x.strip() for x in part[1:-1].split(',')]
            if not all(ispec):
                raise SearchParsingError("Every count specified must be nonempty.")
            if len(ispec) == 1 and first_field is not None:
                sub_query[first_field] = parse_one(ispec[0])[1]
            else:
                if any('-' in x[1:] for x in ispec):
                    raise SearchParsingError("Ranges not supported.")
                sub_query[qfield] = {'$startswith':' '.join(ispec) + ' '}
        elif first_field is not None:
            sub_query[first_field] = parse_one(part)[1]
        else:
            if '-' in part[1:]:
                raise SearchParsingError("Ranges not supported.")
            sub_query[qfield] = {'$startswith':'%s %s '%(' '.join(initial_segment), part)}
        return sub_query
    if len(parts) == 1:
        query.update(make_sub_query(parts[0]))
    else:
        collapse_ors(['$or',[make_sub_query(part) for part in parts]], query)

def parse_count(info, default=50):
    try:
        info['count'] = int(info['count'])
    except (KeyError, ValueError):
        info['count'] = default
    return info['count']

def parse_start(info, default=0):
    try:
        start = int(info['start'])
        count = info['count']
        if start < 0:
            start += (1 - (start + 1) / count) * count
    except (KeyError, ValueError):
        start = default
    return start
