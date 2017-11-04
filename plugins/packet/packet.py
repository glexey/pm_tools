import re
from collections import namedtuple
from operator import attrgetter

require_plugins = ['register', 'simplereg', 'struct', 'packet'] # "import" plugins that we depend on

class PacketPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "packet"
        self.pp.register_plugin(self)

    def process(self, code, regname, width=32, resolution="bit", struct=False, name_defaults=False, div_style=None, exclude_desc=False):
        """
        Process register markdown, produce HTML to describe it.

        If the 'struct=True' flag is passed, that indicates to treat the bit definitions
        as a size and bits as an ordered list.  Else they are treated as msb:lsb.
        """

        # Start with field list
        # Guess at the register format
        fields = None
        attrs = None
        if (register.is_rich_register(code)):
            attrs, fields = register.parse(code, regname, struct=struct)
        else:
            fields = simplereg.parse(code, regname)

        # Create another line-based container that is split based
        # on the width
        lines = self.parse(fields, width, resolution)

        # Generate the html file
        return self.pp.packet2html(lines, fields, regname, width, resolution, name_defaults, exclude_desc)

    def parse(self, fields, width, resolution="bit"):
        """
        Create a list of packet lines based on the subfields and how they
        align to the width
        """
        Field = namedtuple("field", ["msb", "lsb", "name", "desc", "enums", "access_type", "reset_default"])

        bit_or_byte = 1
        if (resolution == "byte"):
            bit_or_byte = 8

        lines = {}
        for f in fields:
            start_line = int(f.lsb / bit_or_byte / width)
            end_line = int(f.msb / bit_or_byte / width)
            if (start_line == end_line):
                # Fully contained within a line
                if (not lines.has_key(start_line)):
                    lines[start_line] = []

                linefield = Field(f.msb/bit_or_byte, f.lsb/bit_or_byte, self._make_name(f.name, f.msb/bit_or_byte - f.lsb/bit_or_byte + 1), f.desc, f.enums, f.access_type, f.reset_default)
                lines[start_line].append(linefield)
            else:
                # Not contained within the line.  We need to split up this
                # field and map it across two
                field_count = end_line - start_line + 1
                packet_lsb = f.lsb/bit_or_byte
                lsb = 0
                for i in range(field_count):
                    # Extract as many bits as possible, to the end of this
                    # line or MSB, whichever is nearest
                    bits_this_line = min((width - (packet_lsb % width)), f.msb/bit_or_byte - packet_lsb + 1)

                    if bits_this_line < 2:
                        line_name = "%s[%d]" % (f.name, lsb)
                    else:
                        line_name = "%s[%d:%d]" % (f.name, lsb + bits_this_line - 1, lsb)
                    splitfield = Field(packet_lsb + bits_this_line - 1, packet_lsb, line_name, f.desc, f.enums, f.access_type, f.reset_default)
                    line = int(splitfield.lsb / width)
                    if (not lines.has_key(line)):
                        lines[line] = []

                    lines[line].append(splitfield)

                    lsb += bits_this_line
                    packet_lsb += bits_this_line

        # Find any missing bits
        valid_bits = []
        for linenum in lines.keys():
            line = lines[linenum]
            failed = False
            valid_bits += [0] * width
            for f in line:
                # Tricky, don't divide by bit_or_byte here, we already did that above.
                for i in range(f.lsb, f.msb + 1):
                    valid_bits[i] = 1

        lsb = 0
        while (lsb < len(valid_bits)):
            if (valid_bits[lsb] == 0):
                # find the end of this missing field
                filler_added = False
                for msb in range(lsb, len(valid_bits)):
                    if (valid_bits[msb] == 1):
                        # Add our filler field
                        line = int((msb-1) / width)
                        lines[line].append(Field(msb - 1, lsb, "", "", None, None, None))
                        lsb = msb
                        filler_added = True
                        break
                if (not filler_added):
                    # If we got here, then the missing bits extend to the end of the packet
                    line = int((msb-1) / width)
                    lines[line].append(Field(len(valid_bits) - 1, lsb, "", "", None, None, None))
                    lsb = len(valid_bits)
            else:
                lsb += 1

        # sort by lsb per line, highest LSB first
        sorted_lines = []
        for line in sorted(lines.keys()):
            this_line = lines[line]
            sorted_lines.append(reversed(sorted(this_line, key=attrgetter('lsb'))))

        return sorted_lines

    def _make_name(self, name, size):
        """
        Calculate a TLA name for a field in case it is short
        """
        if (size > 2):
            return name

        # Short field, clone and change the name to a TLA
        newname = ""
        started = False

        # Allow surrounding the field with <mark>..</mark>, etc.
        tokens = re.split(r'(<[^>]+>)', name)

        for i, t in enumerate(tokens):
            if i % 2 or t == '':
                newname += t
            else:
                for word in re.sub(r'[_()]', " ", t).split()[:3]:
                    if started and (self.pp.fmt == "html" or self.pp.fmt == "docx"):
                        newname += "<br>"
                    started = True
                    newname += word[0].upper()
        return newname


class PacketdiagramPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "packetdiagram"
        self.pp.register_plugin(self)

    def process(self, code, regname, width=32, resolution="bit", struct=False, name_defaults=False, **kwargs):
        """
        Redirect to the main packet handler, but exclude register description.
        """
        kwargs.update(exclude_desc=True)
        return packet.process(code, regname, width, resolution, struct, name_defaults, **kwargs)


class StructPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "struct"
        self.pp.register_plugin(self)

    def process(self, code, regname, width=32, resolution="bit", name_defaults=False, div_style=None, exclude_desc=False):
        """
        Process register markdown, produce HTML to describe it.

        The 'struct' type is the same as a packet, but it uses struct typedef style instantiation.

        Syntax is not an exact match to struct typedef.  But the concept of defining bit width
        and then the SW packs the data in is the same.

        Data is packed in from LSB to MSB

        """

        # Start with field list
        # Guess at the register format
        fields = None
        attrs = None
        if (register.is_rich_register(code)):
            attrs, fields = register.parse(code, regname, struct=True)
        else:
            fields = simplereg.parse(code, regname)

        # Create another line-based container that is split based
        # on the width
        lines = packet.parse(fields, width, resolution)

        return self.pp.packet2html(lines, fields, regname, width, resolution, name_defaults, exclude_desc)

class StructdiagramPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "structdiagram"
        self.pp.register_plugin(self)

    def process(self, code, regname, width=32, resolution="bit", name_defaults=False, **kwargs):
        """
        Redirect to the main packet handler, but exclude register description.
        """
        kwargs.update(exclude_desc=True)
        return struct.process(code, regname, width, resolution, name_defaults, **kwargs)


new = [PacketPlugin, PacketdiagramPlugin, StructPlugin, StructdiagramPlugin]
