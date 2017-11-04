import os

class Excel2imgPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "xlsimg"
        self.pp.register_plugin(self)

    def process(self, code, fname, sheet="", range="", title=None, div_style=None):
        """
        Snapshot specified range from Excel file as picture  and dump it to png

        ```xlsimg("fname", "optional sheet", "optional range", "optional title")
        """
        if title is None:
            # construct default title
            atitle = []
            if sheet != '': atitle.append(sheet)
            if range != '': atitle.append(range)
            if atitle == []: atitle.append(os.path.splitext(os.path.basename(fname))[0])
            title = '_'.join(atitle)

        fn_base = self.pp.tofname("%s_%s_%s"%(fname, sheet, range))

        fn_input, fname = self.pp.get_asset(fname, False)

        fn_out = os.path.join(self.pp.dirs[-1], self.pp.auto, fn_base + '.png')
        fn_out_relative = os.path.relpath(fn_out, self.pp.dirs[0])

        if sheet == '': sheet = None
        if range == '': range = None

        if (not self.pp.exists_and_newer(fn_out, fn_input)):
            import excel2img
            excel2img.export_img(fn_input, fn_out, sheet, range)
            self.pp.timestamp(fn_out)

        # Return the link to the new png file
        return "\n<div class=\"figure\">\n[![%s](%s)](%s)<p class=\"caption\">%s</p></div>" % (title, fn_out_relative, fname, title)

new = Excel2imgPlugin
