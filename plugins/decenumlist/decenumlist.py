import re

class DecenumlistPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "decenumlist"
        self.pp.register_plugin(self)

    def process(self, code, div_style=None):
        """
        Decimal Enumerated List Plugin. Indents and converts 1. 1. 1.1 1.1 1.1 1.1.1 1.1.1 to 1. 2. 2.1 2.2 2.3 2.3.1 2.3.2 etc.
        """
        
        current_level = 0
        current_indent = ""
        sublevel_history = []
        sublevel_history.append(0)
        lines = code.split("\n")
        out = ""
        for line in lines:
            line = re.sub("&", "&amp;", line)
            line = re.sub("<", "&lt;", line)
            line = re.sub(">", "&gt;", line)
            s = line
            #check, parse and strip nested level signature
            if (re.search("^(1.)", line) != None):
                #print "Top level Anchor found "
                current_level = 1
                current_indent = ""
                line = re.sub("^[1]","",line)
                while True:
                    if (re.search("^.1", line) == None): #no more sublevels; increase top level count
                        try:
                            sublevel_history[current_level] += 1
                        except IndexError:
                            sublevel_history.append(1)
                        for i in range(current_level+1, len(sublevel_history)):
                            sublevel_history[i] = 0
                        break
                    #print "Sublevel Anchor found "
                    current_level += 1
                    line = re.sub("^(.1)","",line)
                #apply parsed signature levels to header line
                s = ""
                for i in range(1,current_level+1):
                    s += str(sublevel_history[i])
                    s += "."
                    current_indent += "  "
                s = re.sub("\.$","",s)
                s = s + line
            
            out += current_indent #indent everything with current level indent
            out += s
            #print out
            out += "\n"

        out = out.strip("\n\r") # remove blank lines on top and bottom
        wrapped_code = '\n<div class="DecEnumList"><pre class="DecEnumList"><code class="DecEnumList">%s</code></pre></div>\n' % out
        return wrapped_code

new = DecenumlistPlugin
