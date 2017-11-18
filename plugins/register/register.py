import re
import collections
from operator import attrgetter

class RegisterPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "register"
        self.pp.register_plugin(self)

    def process(self, code, regname, struct=False, div_style=None):
        """
        Process rich register markdown, produce HTML to describe it.
        """
        attrs, fields = self.parse(code, regname, struct=struct)

        return self.pp.register2html(fields, attrs, regname, 'rich')

    def parse(self, code, regname, struct=False):
        """
        Parse out the rich register from the embedded code

        YAML style header
        ---
        attr1: value
        attr2: value
        ...

        Fields declared on their own line
        == 41:41 | DC6 Ready

        'struct' style fields are packed from LSB to MSB
        == 16 | 16bit field
        == 1 | 1 bit field

        Descriptions follow

        Enumerations optional
        = 0 | Power Down
        = 1 | Power Up
        """
        # Extract header first
        m = re.search(r"^\s*(---.*?\n\.\.\.)(.*)", code, re.DOTALL|re.MULTILINE)
        attributes = []
        if (m != None):
            header = m.group(1)[3:-3]
            code = m.group(2)

            attributes = self._extract_attributes(header)

        # Split on \n== for each bit field
        initial_fields = re.split('\n==', code)

        field_strings = []
        for f in initial_fields:
            if (f.strip() != ""):
                field_strings.append(f)

        # Declare our base object type
        Field = collections.namedtuple("field", ["msb", "lsb", "name", "desc", "enums", "access_type", "reset_default"])

        # Break up the register definition into its components
        fields = []
        next_lsb = 0
        for f in field_strings:
            msb, lsb, name, description, enums, access_type, reset_default = self.extract_rich_params(f, regname, next_lsb, struct)
            fields.append(Field(msb, lsb, name, description, enums, access_type, reset_default))
            next_lsb = int(msb) + 1

        # return attributes if any
        # sort fields by lsb
        return attributes, sorted(fields, key=attrgetter('lsb'))

    def _extract_attributes(self, header):
        # Extract attributes
        startpos = []
        for x in re.finditer(r"^(.*?):", header, re.MULTILINE):
            startpos.append(x.start())
        if (len(startpos) > 0):
            # append the end of the string
            startpos.append(len(header)-1)

        attrlist = []
        for i in range(len(startpos)-1):
            attr = header[startpos[i]:startpos[i+1]]
            attrlist.append(attr)

        # Now we have an array.  Split each into a name and value pair
        attrs = []
        for attr in attrlist:
            name = re.split(":", attr)[0].rstrip().lstrip()
            value = attr[len(name)+1:].rstrip().lstrip()
            attrs.append([name, value])

        return attrs

    def extract_rich_params(self, code, regname, next_lsb=0, struct=False):
        """
        Given a bit field, extract out the parameters within it
        """
        valid_access_types = collections.OrderedDict([
                ("RO", "Read Only"),
                ("RW", "Read/Write"),
                ("RWP", "Read/Write, Persistent (sticky) - only reset on PowerGood"),
                ("RWO", "Read/Write Once (locked on first write)"),
                ("RW0CV", "Read/Write zero clears with volatile HW control"),
                ("WO", "Write Only"),
                ("ROV", "Read Only, Volatile (H/W can change the bit, so two reads may return different results)"),
                ("RWV", "Read/Write, Volatile (H/W can change the bit, so S/W read may return different value from what was written)"),
                ("RWVP", "Read/Write, Volatile, Persistent (sticky)"),
                ("RWVL", "Read/Write, Volatile (see above), with Lock capability"),
                ("RW0C", "Read/Write 0 to Clear: S/W can only write 0, H/W may set"),
                ("RW1S", "Read/Write 1 to Set: S/W can only write 1, H/W may clear"),
                ("RW1C", "Read/Write 1 to Clear: S/W can only write 1, which clears the bit (sets it to 0)"),
                ("RWL", "Read/Write, with Lock capability"),
                ("RW1SV", "Set by H/W, cleared on S/W read? - review usages"),
                ])
        access_types_help_msg = ''.join(["\n  %s - %s"%x for x in valid_access_types.iteritems()])

        access_type = None
        reset_default = None

        lines = code.split("\n")

        # msb:lsb | name
        msb = 0
        lsb = 0
        if '|' not in lines[0]:
            self.pp.error("Register %s: expected '|', got: %s"%(regname, lines[0].strip()))
        else:
            params = [x.strip() for x in lines[0].split("|")]
            if (len(params) < 2):
                self.pp.error("Register %s bitfield has an incorrect definition: '%s'" % (regname, lines[0].strip()))
            bits = params[0]
            name = params[1]
            if (not struct):
                if (bits.find(":") > 0):
                    msb, lsb = map(int, bits.split(":"))
                elif (bits.isdigit()):
                    # assume msb = lsb
                    msb = int(bits)
                    lsb = int(bits)
                else:
                    self.pp.error("Register %s bitfield has an incorrect bit definition: '%s'" % (regname, lines[0].strip()))

                # Fix incorrectly ordered bit fields
                if lsb > msb:
                    lsb, msb = msb, lsb
            else:
                size = int(bits)
                if (size == 0):
                    self.pp.error("Register %s bitfield has an invalid 0-sized field (did you intend to use struct formatting?): '%s'" % (regname,
                        lines[0].strip()))
                lsb = next_lsb
                msb = size + lsb - 1
            if (len(params) > 2):
                access_type = params[2].replace("/", "").upper()
                if (access_type not in valid_access_types):
                    self.pp.error("Register field %s.%s has an invalid/unsupported access type: '%s'. Valid access types are: %s" % (regname, name, access_type, access_types_help_msg))
            if (len(params) > 3):
                value = params[3]
                try:
                    reset_default = self.pp.formatters.to_int(value)
                    if (reset_default > (2**(msb - lsb + 1)) - 1):
                        self.pp.error("Register field %s.%s default value 0x%x cannot be encoded with %d bits." % (regname, name, reset_default, msb - lsb + 1))
                except ValueError:
                    reset_default = value

        # Description up to end or ^=, whichever is first
        desc = ""
        i = 1
        for line in lines[1:]:
            if (line.startswith("=")):
                break
            # make sure we include newlines for markdown text preservation
            desc += line + "\n"
            i += 1

        enums = None
        if i <= len(lines):
            enums = []
            for line in lines[i:]:
                if line.rstrip() == "": continue
                if (not line.startswith("=")):
                    # Append this to the description
                    desc += line
                    continue
                enum = re.sub(r"^=\s*", "", line)
                enum_line = re.split(r"\s*\|\s*", enum)
                if (len(enum_line) > 2):
                    self.pp.error("Improperly formatted enum: %s" % enum)
                value = enum_line[0]
                text = enum_line[1]
                try:
                    enums.append([self.pp.formatters.to_int(value), text])
                except ValueError:
                    enums.append([value, text])

        assert isinstance(msb, int) and isinstance(lsb, int)

        return msb, lsb, name, desc, enums, access_type, reset_default

    def is_rich_register(self, code):
        """
        Detect if this is a rich register or a simple one
        """
        # Remove starting whitespace
        code = code.lstrip()

        # if starts with == or ---, it is a rich register
        if (code.startswith("==") or code.startswith("---")):
            return True
        else:
            return False


class SimpleregPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "simplereg"
        self.pp.register_plugin(self)

    def process(self, code, regname, div_style=None):
        """
        Process simple register markdown, produce HTML to describe it.
        """
        fields = self.parse(code, regname)

        return self.pp.register2html(fields, None, regname, 'simple')

    def parse(self, code, name):
        """
        Parse out simple register from the embedded code
        """
        # Split on \n
        lines = code.splitlines()

        Field = collections.namedtuple("field", ["msb", "lsb", "name", "desc", "enums", 'access_type', 'reset_default'])
        fields = []
        msb = -1
        for f in lines:
            if f.strip() == "":
                continue
            # msb:lsb | field [| description]  -OR-  numbits | field [| description]
            m = re.search(r"^\s*(\d+)(?::(\d+))?\s*\|\s*(.*?)(?:\s*\|\s*(.*))?$", f)
            if m:
                if m.group(2):
                    msb, lsb = int(m.group(1)), int(m.group(2))
                else:
                    msb, lsb = msb + int(m.group(1)), msb + 1
                if (msb < lsb):
                    msb, lsb = lsb, msb
                desc = m.group(4)
                if not desc:
                    desc = m.group(3)
                fields.append(Field(msb, lsb, m.group(3), desc, None, None, None))
            else:
                print "Error in '%s': %s" % (name, f)

        # sort by lsb
        return sorted(fields, key=attrgetter('lsb'))

new = [RegisterPlugin, SimpleregPlugin]
