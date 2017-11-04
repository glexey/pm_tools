import os

class DotPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "dot"
        self.pp.register_plugin(self)

    def process(self, code, filename_or_title, title=None, div_style=None):
        """
        Process GraphViz dot code and return the proper insertion string
        """

        srcfile, dstfile, update, title = self.pp.get_source(code, filename_or_title, ".dot", ".svg", title, None)

        if update:
            self.dot2img(srcfile, dstfile)

        return self.pp.img2md(dstfile, title, div_style)

    def dot2img(self, infile, outfile):
        if (not infile.endswith(".dot")):
            raise Exception("Invalid dot file requested: %s" % infile)
        t = os.path.splitext(outfile)[1][1:]
        self.pp._call(r'"%s" -T%s "%s" -o "%s"' % (self.pp.dot_exe, t, infile, outfile))

new = DotPlugin
