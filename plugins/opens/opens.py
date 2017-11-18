import re
import util

class OpensPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "opens"
        self.pp.register_plugin(self)
        self.keywords = ('FIXME', 'OPEN', 'TODO')
        self.items = dict([x.lower(), []] for x in self.keywords)
        self.repdict = {}

    def process(self, code, keyword, numbered=False, div_style=None):
        assert keyword in self.keywords, "Did not understand '%s', should be one of: %s"%(keyword, self.keywords)
        repstr = "<!-- COLLECT:%s:%s -->\n\n"%(keyword, numbered)
        self.repdict[repstr] = (keyword, numbered)
        return "\n\n%s\n\n"%repstr

    def preprocess(self, s):
        for repstr, repitem in self.repdict.iteritems():
            keyword, numbered = repitem
            prefix = '1.' if numbered else '* '
            lststr = '\n'.join("%s [%s](#%s)"%(prefix, re.sub(r'([\[\]])', r'\\\1', text), tag) for text, tag in self.items[keyword.lower()])
            s = s.replace(repstr, lststr)
        return s

    def process_mismatch(self, s):
        # For OPEN/FIXME/TODO, add named "anchors", so that we could auto-link to them
        for keyword in self.keywords:
            r = re.compile(util.fixme_pattern(keyword))
            a = r.split(s)
            # => text (OPEN) text (OPEN) text
            s = a.pop(0)
            name = keyword.lower()
            while a:
                key = a.pop(0)
                text = a.pop(0)
                n = len(self.items[name]) + 1
                tag = "%s_%04d"%(name, n)
                s += '<a name="%s" class="%s">%s</a>%s'%(tag, name, key, text)
                # cut the text to extract the content of the open
                text = re.sub(r"\n\s*\n.*|\n\s*(?:\*|\-|\+|\d+\.|[a-zA-Z]\.)\s.*", "", text)
                text = re.sub(r"\*+$|\*\*", "", text)
                text = re.sub(r"^([^(]+)\).*", r"\1", text)
                text = re.sub(r"^([^[]+)\].*", r"\1", text)
                text = text[:1].upper() + text[1:] # Capitalize first letter, if any
                self.items[name].append((text, tag))
        
        return s

new = OpensPlugin
