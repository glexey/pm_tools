import os

class Xsd2htmlPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "xsd2html"
        self.pp.register_plugin(self)
        self.msxsl = self.pp.toolpath("plugins/xsd2html/msxsl/msxsl.exe") 
        self.xs3p =  self.pp.toolpath("plugins/xsd2html/msxsl/xs3p.xsl") 

    def process(self, code, fname, title=None, div_style=None):
        """
        Given an xsd file, generate HTML documentation and include a hyperlink to it
        as well as source code
        """
        filename = os.path.join(self.pp.dirs[-1], fname)
        if title is None: title = fname

        basename = os.path.splitext(os.path.basename(filename))[0]
        out_html = os.path.join(self.pp.dirs[-1], self.pp.auto, basename + '.html')
        relative_html = os.path.relpath(out_html, self.pp.dirs[0])
        self.pp.log_dependency(self.pp.fname, filename) # FIXME: use get_source() instead
        self.pp._call(r'"%s" "%s" "%s" -o "%s"' % (self.msxsl, os.path.abspath(filename), self.xs3p, out_html))

        return "\n\n* [%s](%s) ([source](%s))\n\n" % (title, relative_html, fname)

new = Xsd2htmlPlugin
