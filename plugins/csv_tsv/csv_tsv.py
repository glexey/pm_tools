import re

require_plugins = ['csv'] # "import" csv plugin instance to our own global namespace

class CsvPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "csv"
        self.pp.register_plugin(self)

    def process(self, code, filename_or_title, title=None, div_style=None, separator=","):
        """
        Read and import CSV file.  Insert table into the output
        """

        import csv as _csv

        # Remove illegal characters
        code = self.pp.cleanstr(code)

        fn_src, _, update, title = self.pp.get_source(code, filename_or_title, ".csv", None, title)

        csv_handle = _csv.reader(file(fn_src), escapechar="\\", delimiter=separator)

        # Convert to array for downstream code
        rows = [r for r in csv_handle]

        return self.csv2html(title, rows)
    
    def csv2html(self, title, rows, link=None):
        """
        Convert rows from a csv file to an html output
        """

        def clean(s):
            # remove non-ascii chars
            return re.sub(r'[^\x00-\x7F]+', ' ', s).lstrip().rstrip()

        max_size = 0
        for r in rows:
            if len(r) > max_size:
                max_size = len(r)

        # Pad short rows
        for r in rows:
            while (len(r) < max_size):
                r.append("")

        tid = ""
        if title.strip() != "":
            tid = ' id="%s"'%self.pp.title2id("table-" + title)
        s = '<div class="table"%s><table>\n'%tid
        s += "<thead><tr>\n"
        header = rows[0]
        for d in header:
            s += "  <th>%s</th>\n" % clean(d)
        s += "</tr></thead>\n"

        for row in rows[1:]:
            s += "<tr>"
            for d in row:
                s += "  <td>%s</td>\n" % clean(d)
            s += "</tr>"
        s += "</table>\n"
        if title.strip() != "":
            if (link == None):
                s += '<p class="table_caption">%s</p>\n' % title
            else:
                s += '<p class="table_caption">%s (<a href="%s">source xlsx</a>)</p>\n' % (title, link)
        s += "</div>\n\n"

        return s


class TsvPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "tsv"
        self.pp.register_plugin(self)

    def process(self, code, filename_or_title, **kwargs):
        """
        Read and import TSV file or text.  Insert table into the output
        """
        kwargs.update(separator = "\t")
        return csv.process(code, filename_or_title, **kwargs)


new = [CsvPlugin, TsvPlugin]
