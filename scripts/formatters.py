import re

def to_int(s):
    """
    Convert strings of the following formats into hex:
    8'hf1
    8'b001001
    0xf1
    """
    if (s == None): raise ValueError("hex conversion is not possible on None type")

    if s == "ZERO": return 0

    # If value is already an integer, just return it
    try:
        return int(s)
    except ValueError:
        pass

    s = s.replace('_', '')

    m = re.match("^(?:\d+'?h'?|0x)([a-f\d]+)$", s, re.IGNORECASE)
    if (m != None): return int(m.group(1), 16)

    m = re.match("^\d*'?b'?([01]+)$", s, re.IGNORECASE)
    if (m != None): return int(m.group(1), 2)

    m = re.match("^\d*'?d'?([0-9]+)$", s, re.IGNORECASE)
    if (m != None): return int(m.group(1))

    # numerical formula (server uses that)
    m = re.match(r"^[\d\+\-\*\/\s\(\)]{3,}$", s)
    if (m != None): return eval(s)

    raise ValueError("Did not understand numerical formatting for %s" % s)

