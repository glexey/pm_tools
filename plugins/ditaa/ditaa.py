import os
import re

class DitaaPlugin(object):

    def __init__(self, preprocessor):
        self.ditaa_jar = preprocessor.toolpath("plugins/ditaa/ditaa.jar")
        self.pp = preprocessor
        self.token = "ditaa"
        self.pp.register_plugin(self)
        # Also instantiate and register sigint plugin
        self.sigint = SigintPlugin(preprocessor, self)

    def process(self, code, filename_or_title, title=None, div_style=None):
        """
        Process ditaa code and return the proper insertion string
        """

        srcfile, dstfile, update, title = self.pp.get_source(code, filename_or_title, ".ditaa", ".png", title, None, raw_src=True)

        if update:
            self.ditaa2png(srcfile, dstfile)

        # Return the inserted link and caption
        return "\n![%s](%s)\n" % (title, os.path.relpath(dstfile, self.pp.dirs[0]).replace('\\', '/'))

    def ditaa2png(self, infile, outfile):
        self.pp._call(r'%s -jar "%s" --no-shadows --round-corners -o "%s" "%s"' % (
            self.pp.java_exe, self.ditaa_jar, infile, outfile))

class SigintPlugin(object):

    def __init__(self, preprocessor, ditaa):
        self.pp = preprocessor
        self.token = "sigint"
        self.pp.register_plugin(self)
        self.ditaa2png = ditaa.ditaa2png

    def process(self, code, filename_or_title, title=None, div_style=None):
        """
        Process signal interface definition and produce a drawing and summary table
        """
        netlist = self.parse_sigint(code)
        if (len(netlist) == 0):
            return ""

        block_diagram = self.netlist2blocks(netlist)

        srcfile, dstfile, update, title = self.pp.get_source(block_diagram, filename_or_title, ".ditaa", ".png", title, None)

        if update:
            self.ditaa2png(srcfile, dstfile)

        # Return the inserted link and caption
        relative_path = os.path.relpath(dstfile, self.pp.dirs[0]).replace('\\', '/')
        return "\n![%s](%s)\n\n%s" % (title, relative_path, self.netlist_summary(netlist))

    def netlist2blocks(self, netlist):
        """
        Produce a ditaa diagram
        """
        reverse_dir = {
                "->" : "<-",
                "<-" : "->",
                "<->" : "<->",
        }

        # First line dictates src vs. dst IP
        srcip_width = len(netlist[0].srcip) 
        dstip_width = len(netlist[0].dstip)

        signame_width = 0
        for net in netlist:
            signame_width = max(signame_width, len(net.signame))

        # Build Diagram
        top_bottom = "+%s+ %s +%s+\n" % ("-"*(srcip_width+2), " "*signame_width, "-"*(dstip_width+2))

        # Set up the formats for each line
        noline_fmt  = "| %%%ds | %%%ds | %%%ds |\n" % (srcip_width, signame_width, dstip_width)
        right_fmt   = "| %%%ds *-%s>| %%%ds |\n" % (srcip_width, "-"*signame_width, dstip_width)
        left_fmt    = "| %%%ds |<%s-* %%%ds |\n" % (srcip_width, "-"*signame_width, dstip_width)
        bidir_fmt   = "| %%%ds |<%s>| %%%ds |\n" % (srcip_width, "-"*signame_width, dstip_width)

        diagram = top_bottom
        diagram += noline_fmt % (netlist[0].srcip, " "*signame_width, netlist[0].dstip)
        for net in netlist:
            diagram += noline_fmt % ("", net.signame, "")
            direction = net.ptr
            if (net.srcip != netlist[0].srcip):
                # Reverse the direction
                direction = reverse_dir[direction]

            if (direction == "->"):
                diagram += right_fmt % ("", "")
            elif (direction == "<-"):
                diagram += left_fmt % ("", "")
            elif (direction == "<->"):
                diagram += bidir_fmt % ("", "")
        diagram += top_bottom
        return diagram

    def parse_sigint(self, code):
        """
        Syntax is as follows:

          == srcip -> dstip: signame
          clock: X
          power: Y
          description

          = 0 | enum0
          = 1 | enum1

        Variations:

          == srcip <- dstip: signame
          Dest to Src direction

          == srcip <-> dstip: signame
          Bidirectional

          == srcip <-> dstip: signame[1:0]
          Bus

          == srcip <-> dstip: signame[i]
        """

        class Net(object):
            pass

        netlist = []

        iplist = []
        # Split on \n== for each bit field
        siglist = re.split('\n==', code)
        for sig in siglist:
            if sig.strip() == "":
                continue
            lines = sig.split("\n")
            sigdef = lines[0]
            m = re.search(r"^\s*(\w+)\s*(<-|->|<->)\s*(\w+)\s*:\s*(.*)$", sigdef)
            if (m == None):
                raise Exception("Did not understand syntax for signal definition: %s" % sigdef)
            srcip = m.group(1)
            ptr = m.group(2)
            dstip = m.group(3)
            signame = m.group(4)
            
            # Now, gather the description and power/clock as appropriate
            power = ""
            clock = ""
            description = ""
            enums = []
            for line in lines[1:]:
                if line.startswith("power:"):
                    power = line[6:].strip()
                elif line.startswith("clock:"):
                    clock = line[6:].strip()
                else:
                    enum = self.extract_enum(line)
                    if (enum == None):
                        # Must be a regular line
                        description += line
                        description += "\n"
                    else:
                        enums.append(enum)


            net = Net()
            net.srcip = srcip
            net.dstip = dstip
            net.ptr = ptr
            net.signame = signame
            net.clock = clock
            net.power = power
            net.description = description
            net.enums = enums
            netlist.append(net)

            if (srcip not in iplist): iplist.append(srcip)
            if (dstip not in iplist): iplist.append(dstip)
            if (len(iplist) > 2):
                raise Exception("Found more than 2 IP names in the definition.  This plugin only supports two IPs: %s" % lines[0])

        return netlist

    def netlist_summary(self, netlist):
        """
        Build a table summary of the netlists
        """
        table = "<table>"
        header = ["Signal", "Src IP", "Dir", "Dst IP", "Power", "Clock", "Description"]
        table += "<tr> "
        for h in header:
            table += "<th>%s</th> " % h
        table += "<tr>\n"

        arrow_map = {"->": "&rarr;", "<-": "&larr;", "<->": "&harr;"}

        for net in netlist:
            table += "<tr> "
            table += "<td>%s</td> " % net.signame
            table += "<td align=\"center\">%s</td> " % net.srcip
            table += "<td align=\"center\">%s</td> " % arrow_map[net.ptr]
            table += "<td align=\"center\">%s</td> " % net.dstip
            table += "<td align=\"center\">%s</td> " % net.power
            table += "<td align=\"center\">%s</td> " % net.clock
            desc = net.description
            if (len(net.enums) > 0):
                desc += self.pp.enums2html(net.enums)

            table += "<td>%s</td> " % desc
            table += "<tr>\n"

        table += "</table>\n"
        return table

    def extract_enum(self, line):
        """
        Read a line. If there is an enum in it, return an array of
        [name, value]
        """
        if (not line.startswith("=")):
            # not an enum
            return None

        enum = re.sub(r"^=\s*", "", line)
        enum_line = re.split(r"\s*\|\s*", enum)
        if (len(enum_line) > 2):
            error("Improperly formatted enum: %s" % enum)
        value = enum_line[0]
        text = enum_line[1]
        try:
            value = self.pp.formatters.to_int(value)
            return [value, text]
        except ValueError:
            return [value, text]

        
new = DitaaPlugin
