import re

class Schemdraw2imgPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "schemdraw"
        self.pp.register_plugin(self)

    def process(self, code, filename_or_title, title=None, div_style=None):
        """
        Draw a schematic diagram using SchemDraw module
        """

        sdfile, dstfile, update, title = self.pp.get_source(code, filename_or_title, ".sd.txt", ".svg", title)

        code2 = open(sdfile).read()

        full_code = re.sub(r"^\s*", "", """
        import SchemDraw as schem
        import SchemDraw.elements as e
        import SchemDraw.logic as l
        d = schem.Drawing()
        __CODE__
        d.draw(showplot=False)
        d.save(r"__FIMG__")
        """, flags=re.M).replace('__CODE__', code2).replace('__FIMG__', dstfile)
        exec(full_code)

        return self.pp.img2md(dstfile, title, div_style)

new = Schemdraw2imgPlugin
