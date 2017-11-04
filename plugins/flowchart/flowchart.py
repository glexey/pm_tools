import os

class WavedromPlugin(object):

    def __init__(self, preprocessor):
        self.flowchart_path = preprocessor.toolpath("plugins/flowchart/flowchart-cli")
        self.pp = preprocessor
        self.token = "flowchart"
        self.pp.register_plugin(self)

    def process(self, code, filename_or_title, title=None, div_style=None):
        """
        Process flowchart code and return the proper insertion string
        """

        fchfile, outfile, update, title = self.pp.get_source(code, filename_or_title, ".fch", ".svg", title)

        if update:
            self.flowchart2img(fchfile, outfile, "svg")

        return self.pp.img2md(outfile, title, div_style)

    def flowchart2img(self, infile, outfile=None, t="png"):
        if outfile and os.path.exists(outfile):
            os.unlink(outfile)
        cmd = [self.pp.phantomjs, 'flowchart-cli.js', infile, outfile]
        self.pp._call(cmd, cwd=self.flowchart_path)

new = WavedromPlugin
