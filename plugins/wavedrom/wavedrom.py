import re

class WavedromPlugin(object):

    def __init__(self, preprocessor):
        self.wavedrom_cli = preprocessor.toolpath("plugins/wavedrom/wavedrom-cli/bin/wavedrom-cli.js")
        self.pp = preprocessor
        self.token = "wavedrom"
        self.pp.register_plugin(self)

    def process(self, code, filename_or_title, title=None, div_style=None):
        """
        Process wavedrom code, generate SVG output for insertion
        """

        wdfile, dstfile, update, title = self.pp.get_source(code, filename_or_title, ".wavedrom", ".svg", title, self.process_wavedrom_shorthand)

        if update:
            self.pp._call(r'"%s" "%s" -i "%s" -s "%s"' % (self.pp.phantomjs, self.wavedrom_cli, wdfile, dstfile))

        return self.pp.img2md(dstfile, title, div_style)

    def process_wavedrom_shorthand(self, code):
        """
        Parse wavedrom shorthand syntax and return fully formatted code

          signal name   | waveform | data value list (space separated)

        Grouping headers

          == Header ==

        """
        class Wave(object):
            def __init__(self, name, wave, data, node, group):
                self.name = name
                self.wave = wave
                self.data = data
                self.node = node
                self.group = group

        # Remove leading and trailing newlines
        code = code.lstrip().rstrip()

        # Skip processing if wavedrom syntax already
        if code.startswith("{"): return code

        lines = code.split("\n")
        wavedef = []
        edges = []
        config = []
        last_wave = ""
        current_group = None
        for line in lines:

            if line.lstrip().rstrip() == "":
                # empty line
                wavedef.append(None)
                continue

            if line.lstrip().startswith("#"):
                # Comment
                continue

            # == Title ==
            # = Title =
            # ===Title===
            m = re.search("\s*=+([\w\s]+)=+\s*$", line)
            if m != None:
                # Group marker
                current_group = m.group(1).strip()
                continue

            # Also support underscores
            # __ Title __
            # _ Title _
            # NOT LEGAL: ___Title___
            # ___ Title ___
            m = re.search("\s*_+\s+([\w\s]+)\s+_+\s*$", line)
            if m != None:
                # Group marker
                current_group = m.group(1).strip()
                continue

            # Check for edge definitions
            m = re.search("\s*([a-zA-Z][-><|~]+[a-zA-Z](:?\s+.*|\s*))$", line)
            if (m != None):
                edges.append("'%s'" % m.group(1))
                continue

            # Check for edge markers (nodes)
            if (line.split()[0] == "|"):
                node = line.split()[1]
                if (len(node) != len(last_wave)):
                    self.pp.error("Node definition length does not match preceding waveform length for %s:\n  wave: %s\n  node: %s" % (last_name, last_wave, node))
                if wavedef[-1].node is None:
                    wavedef[-1].node = node
                else:
                    # If more than one line w/o name, assume it's node-only
                    wavedef.append(Wave(None, None, None, node, current_group))
                continue

            # Config search
            m = re.search("\s*(hscale):\s*(.*)$", line)
            if m != None:
                config.append("%s: %s" % (m.group(1), m.group(2)))
                continue

            # If we get here, this must be a regular signal def line
            data = line.split("|")
            if len(data) < 2:
                self.pp.error("Found waveform definition line that is too short.  Each line requires a minimum of 2 columns: %s" % line)
            name = data[0].lstrip().rstrip()
            wave = data[1].lstrip().rstrip()
            last_wave = wave
            last_name = name
            datastr = None
            if len(data) > 2:
                datastr = data[2].lstrip().rstrip()
                # Split at spaces
                data_array = datastr.split()
                datastr = "[ %s ]" % (', '.join(map(lambda x: "'" + x + "'", data_array)))
                
            wavedef.append(Wave(name, wave, datastr, None, current_group))

        # Remove any leading and trailing empty wavedefs
        start_def = -1
        end_def = -1
        for i in range(len(wavedef)):
            if (wavedef[i] != None and start_def < 0):
                start_def = i
            if (wavedef[i] != None):
                end_def = i

        # Splice out the empty lines
        wavedef = wavedef[start_def:end_def + 1]

        # Now we have parsed the string, generate the json
        s  = "{\nsignal: ["
        sig_strings = []
        last_group = None
        for w in wavedef:
            if w == None:
                sig_strings.append("{}")
                continue
            dd = []
            if w.group != None and w.group != last_group: 
                # Close out our working string
                s += ",\n".join(sig_strings)

                if (last_group != None):
                    # Finish our last group
                    s += "]"

                # Add the extra comma, but only if we had signals preceding this
                if (len(sig_strings) > 0):
                    s += ",\n"

                # Start our new group
                s += "['%s',\n" % w.group
                sig_strings = []
                last_group = w.group

            if w.name is not None: dd.append("name: '%s'" % w.name)
            if w.wave is not None: dd.append("wave: '%s'" % w.wave)
            if w.data is not None: dd.append("data: %s" % w.data)
            if w.node is not None: dd.append("node: '%s'" % w.node)
            ss = "{ %s }"%(', '.join(dd))
            sig_strings.append(ss)

        # Close out our working string
        s += ",\n".join(sig_strings)
        if (last_group != None):
            # Finish our last group
            s += "],\n"
        s += "]"

        # Add in edges
        if (len(edges) > 0):
            s += ",\nedge: [%s]" % ",".join(edges)

        # Add in config
        if (len(config) > 0):
            s += ",\nconfig: {%s}" % ",".join(config)

        s += "\n}\n"
        return s

new = WavedromPlugin 
