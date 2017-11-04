import os

class PlantumlPlugin(object):

    def __init__(self, preprocessor):
        self.plantuml_jar = preprocessor.toolpath("plugins/plantuml/plantuml.jar")
        self.plantuml_cfg = preprocessor.toolpath("plugins/plantuml/plantuml.config")
        self.pp = preprocessor
        self.token = "plantuml"
        self.pp.register_plugin(self)

    def process(self, code, filename_or_title, title=None, div_style=None):
        """
        Process plantuml code and return the proper insertion string
        """

        def plantuml_bracket(code):
            # Add outer @startuml/@enduml statements if not provided by user
            if '@startuml' not in code:
                code = "@startuml\n%s\n@enduml"%code
            return code

        pufile, outfile, update, title = self.pp.get_source(code, filename_or_title, ".pu", ".svg", title, plantuml_bracket)

        if update:
            self.plantuml2img(pufile, outfile, "svg")

        return self.pp.img2md(outfile, title, div_style)

    def plantuml2img(self, infile, outfile=None, t="png"):
        try:
            if outfile and os.path.exists(outfile):
                os.unlink(outfile)
            self.pp._call(r'%s -DGRAPHVIZ_DOT="%s" -splash:no -jar "%s" -config "%s" "%s" -t%s' % (
                self.pp.java_exe, self.pp.dot_exe, self.plantuml_jar, self.plantuml_cfg, infile, t))
        except SystemExit:
            # If plantuml failed, but generated output SVG, that SVG contains error description
            # so should be good enough to continue
            if outfile and os.path.exists(outfile):
                print "Ignoring the error above. See plantuml output diagram for detailed error description"
            else:
                raise

new = PlantumlPlugin
