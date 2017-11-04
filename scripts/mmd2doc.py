# Import/install modules that are not part of minimal python distribution and
# rely on pip to install them from the web
import util
util.import_modules({}, "all")

import hashlib

import re
import sys
import bs4
import subprocess as _subprocess
import argparse as _argparse
import os
import glob
import tempfile as _tempfile
import collections
import formatters
import XMLContainer as _XMLContainer
import traceback
import inspect
import time
import sqlite3
import docsrv
from shutil import copy2

_thisdir = os.path.dirname(os.path.realpath(__file__))
repo_root = os.path.abspath(os.path.join(_thisdir, "..", ".."))

sys.path.append(os.path.join(_thisdir, '..'))
import plugins

valid_ftypes = [".mmd", ".md", ".mds"]

class Globals: pass
g = Globals()

class ParseError(Exception): pass

g.figure_count = 0
g.xml = {}
g.pythoncom_initialized = False
g.anchor_count = collections.Counter()
g.deptree_cleanup = []
g.deptree_depends = []
g.svg_hash = {} # holds SVG content for replacement after pandoc run
g.visio2convert = {} # [filename] => [{"page": .., "fnout": ..}, ...]
g.svg_fixes = [] # [{"svg": fname, "png": fname, "title": title}, ...]

def toolpath(relpath):
    abspath = os.path.join(_thisdir, '..', relpath)
    return os.path.normpath(abspath)

toolcfg = util.get_toolconfig()

# Global definitions
g.css_path = toolpath("stylesheets")
g.font_awesome = toolpath("stylesheets/font-awesome/css/fa_pm_doc.css")
g.liverefresh = toolpath("stylesheets/liverefresh.html")
g.dotx = toolpath("stylesheets/reference.dotx")
g.batik = toolpath("batik/batik-rasterizer.jar")
g.pandoc = toolpath("Pandoc/pandoc.exe")
g.reveal_js = toolpath("reveal.js")
g.reveal_template = toolpath("reveal.js/template.reveal.js")
g.html_template = toolpath("frontend/pm_doc.html")
g.email_template = toolpath("frontend/email.html")
g.template_path = toolpath("templates")
g.svg_template = toolpath("frontend/svg_template.html")
g.phantomjs = toolpath("phantomjs/bin/phantomjs.exe")
g.pm_doc_js = toolpath("frontend/pm_doc.js")
g.wkhtmltopdf = toolpath("wkhtmltopdf/bin/wkhtmltopdf.exe")
g.pdf_footer = toolpath("stylesheets/%s"%toolcfg['pdf_footer_html'])
g.mathjax = '<script type="text/javascript" src="%s"></script>'%toolcfg['mathjax']
g.mathjax4pdf = '<script type="text/javascript" src="%s"></script>'%toolcfg['mathjax4pdf']
g.fonts = '<link rel="stylesheet" href="%s">'%toolcfg['fonts']
g.java_exe = util.locate_java()

class PandocPreproc(object):
    def __init__(self, fname, assets="assets", auto="auto", fmt="html"):
        self.token = collections.namedtuple('Token', ['typ', 'value', 'line', 'column'])
        self.legal_tokens = ["visio", "svg"] # these are tightly integrated, the rest comes from plugins/*
        self.assets = assets
        self.assets_paths = set(['.', assets]);
        self.auto = auto
        self.fname = fname
        self.basename = os.path.splitext(os.path.basename(fname))[0]
        self.outf = _tempfile.TemporaryFile("w+b", delete=False)
        self.fmt = fmt
        cleanup_deptree(self.fname)
        # "API" for plugins
        self.token2func = {}
        self.toolpath = toolpath
        self.phantomjs = g.phantomjs
        self.java_exe = g.java_exe
        self.dot_exe = toolpath("Graphviz2.38/bin/dot.exe")
        self._call = _call
        self.exists_and_newer = exists_and_newer
        self.timestamp = timestamp
        self.enums2html = enums2html
        self.formatters = formatters
        self.opts = g.opts
        self.cleanstr = cleanstr
        self.title2id = title2id
        self.register2html = register2html
        self.packet2html = packet2html
        self.find_xml = find_xml
        self.log_dependency = log_dependency # FIXME use get_source() instead
        self.repo_root = repo_root
        # initialize plugins
        plugins.initialize(self)
        # parse the input
        self.parse(fname, self.outf.file)
        self.convert_visio()
        self.fix_broken_svg()
        if self.fmt == "docx" or g.opts.email:
            self.svg2png()

    def register_plugin(self, plugin):
        """
        `plugin` is an instance of a plugin class, expected to have following attributes:
            token - token string by which the plugin is recognized
            process() - processing function that receives plugin invocation markdown
                        code and converts that to some output
        """
        self.legal_tokens.append(plugin.token)
        self.token2func[plugin.token] = plugin.process

    def fix_broken_svg(self):
        """
        Walk through any SVGs that have been identified as bad and replace them
        with PNG equivalents.  This happens when a windows metafile img is embedded
        in them.  The SVG export fails
        """
        def svg_ref_to_png(mo):
            fnimg, title, div_style = g.svg_hash[mo.group(1)]
            for fix in g.svg_fixes:
                if fix["svg"] == fnimg:
                    # match, fix it
                    fnpng = fnimg.replace(".svg", ".png")
                    relpath = os.path.relpath(fix["png"], self.dirs[0])
                    pngstr = "\n![%s](%s)\n" % (title, relpath)
                    return pngstr
            # No match, retain the full string
            return mo.group(0)

        s = open(self.outf.name).read()
        s = re.sub('<!-- INLINE_SVG (\w+) -->', svg_ref_to_png, s)
        open(self.outf.name, 'w').write(s)

    def get_asset(self, fname, throw_err=False):
        """
        Get asset full path and relative path
        """
        # Search for file in all asset paths
        tried = []
        for asset in self.assets_paths:
            full_path = os.path.normpath(os.path.join(self.dirs[-1], asset, fname))
            tried.append(full_path)

            # If asset exist
            if (os.path.isfile(full_path)):

                # Relative path to asset
                relative_path = os.path.relpath(full_path, self.dirs[0])
                log_dependency(self.fname, full_path)
                return full_path, relative_path

        if (throw_err == True):
            err_str = "Could not find '%s', tried:\n" % fname
            err_str += "%s\n" % ('\n'.join(["  %s"%x for x in tried]))
            err_str += "Are you sure you put the file in the right place?"
            error(err_str);

        return None, None

    def tokenize(self, code, token_specification):
        """
        Generator to walk the code and return tokens
        """
        tok_regex = '(?sm)'
        tok_regex += '|'.join('(?P<%s>%s)' % pair for pair in token_specification)
        line_num = 1   # FIXME this is non-functional
        line_start = 0 # FIXME this is non-functional
        next_pos = 0
        for mo in re.finditer(tok_regex, code):
            # Check if we have non-matched text before the match
            # In that case, we want to report it as token type "MISMATCH"
            if mo.start() != next_pos:
                yield self.token("MISMATCH", code[next_pos:mo.start()], 1, 0)
            kind = mo.lastgroup
            value = mo.group(kind)
            column = mo.start() - line_start # FIXME this is non-functional
            yield self.token(kind, value, line_num, column)
            next_pos = mo.end()
        # Yield the rest of code as "MISMATCH"
        if next_pos < len(code):
            yield self.token("MISMATCH", code[next_pos:], 1, 0)

    def tofname(self, s, hash_input=None):
        s = re.sub(r"[ #!:&|+\/<>()]+", "_", s)
        if hash_input is not None:
            h = hashlib.md5(hash_input).hexdigest()[-5:]
            s += '_' + h
        return s

    def img2md(self, fnimg, title, div_style):
        """
        Insert an image to the (markdown) output
        """

        if fnimg.endswith("svg"):
            # Instead of returning HTML for embedded SVG, return a "reference" - just some text 
            # that we can replace with SVG embedding after pandoc creates HTML. The reason is
            # that pandoc is slow when parsing large nested SVG, and sometimes it also corrupts
            # the content
            svgref = (fnimg, title, div_style)
            h = hashlib.md5("%s_%s_%s"%svgref).hexdigest()
            g.svg_hash[h] = svgref 
            return "\n<!-- INLINE_SVG %s -->\n"%h
        else:
            # Return the inserted link and caption
            relpath = os.path.relpath(fnimg, self.dirs[0]).replace('\\', '/')
            return "\n![%s](%s)\n" % (title, relpath)

    def svg2png(self):
        """
        For output formats that don't understand SVG (Microsoft Word),
        convert SVG images to PNG, before submitting to pandoc
        """
        def svg_ref_to_png(mo):
            fnimg, title, div_style = g.svg_hash[mo.group(1)]
            fnpng = fnimg.replace(".svg", ".png")
            _call("%s -jar %s -Xmx16G -m image/png -d \"%s\" \"%s\""%(g.java_exe, g.batik, os.path.dirname(fnpng), fnimg))
            relpath = os.path.relpath(fnpng, self.dirs[0]).replace('\\', '/')
            return "\n![%s](%s)\n" % (title, relpath)
        s = open(self.outf.name).read()
        s = re.sub('<!-- INLINE_SVG (\w+) -->', svg_ref_to_png, s)
        open(self.outf.name, 'w').write(s)

    def get_source(self, code, fn_or_title, src_ext, dst_ext, title, preproc=None, raw_src=False):
        """
        Parses arguments for plugins that accept text (code) as their input.
        If user specified some code as part of plugin call, writes that code
        to a file. Otherwise it expects the file name to be provided by user.
        Returns a tuple of:
          fn_src: the name of a file with code
          fn_dst: the name of an output file based on provided extenstion
          update: indication if fn_dst output needs update
          title: the title, either user-provided or auto-generate from file name.
        """
        if title is None: title = fn_or_title

        if code.strip() == "":
            # Empty code block means user specifies input file name
            fn_user_src, _ = self.get_asset(fn_or_title, True)
            code = open(fn_user_src).read()
        else:
            # Check that specified title doesn't match any actual file
            if fn_or_title.strip() != "":
                if os.path.exists(os.path.join(self.dirs[-1], fn_or_title)):
                    raise Exception("Error: provide either code block or input file name")

        # Pre-process the code
        if preproc is None:
            if (raw_src):
                preproc = lambda x: x
            else:
                preproc = lambda x: x.strip()

        code = preproc(code)

        update = True
        fn_src = os.path.join(self.dirs[-1], self.auto, get_figure_id(self.tofname(title))) + src_ext
        if os.path.exists(fn_src) and equal(fn_src, code):
            # Indicate no update to the source file has happened
            update = False
        else:
            make_dir(self.dirs[-1], self.auto)
            with open(fn_src, 'w') as f:
                f.write(code)

        fn_dst = None
        if dst_ext is not None:
            fn_dst = re.sub(re.escape(src_ext) + "$", dst_ext, fn_src)
            update |= not os.path.exists(fn_dst)

        return fn_src, fn_dst, update, title

    def svg(self, code, filename_or_title, title=None, div_style=None):
        """
        Insert SVG code with the ability to zoom, etc.
        """

        srcfile, _, update, title = self.get_source(code, filename_or_title, ".svg", None, title, None)

        return self.img2md(srcfile, title, div_style)

    def auto_dir(self, level=-1):
        # By default, point to the directory of currently parsed document
        return make_dir(self.dirs[level], self.auto)

    def visio(self, code, fname, sheetname, title=None, format='svg', div_style=None):
        """
        Open up a specific tab of an visio file and dump it to png

        ```visio("fname", "sheetname", "Optional Title")
        """

        if title is None: title = sheetname

        dstfile = fname

        # Pull from the web if the user wants it
        if (fname.startswith("http")):
            try:
                dstfile = save_url(fname, os.path.join(self.dirs[-1], self.auto))
            except Exception as e:
                traceback.print_exc()
                # deal with a bad URL
                return "[%s <mark>_file not found_</mark>](%s)" % (title, fname)

        visiofile, visio_relative = self.get_asset(dstfile, True)

        # Export to the output file
        fname = os.path.split(visiofile)[1]
        imgname = os.path.join(self.auto_dir(), self.tofname("%s_%s" % (fname,sheetname), visio_relative) + '.' + format)

        # Add the file/page to the convert "queue"
        if visiofile not in g.visio2convert:
            g.visio2convert[visiofile] = []

        job = {"page": sheetname, "fnout": imgname, "title": title}
        g.visio2convert[visiofile].append(job)

        return self.img2md(imgname, title, div_style)

    def friendly_errmsg(self, errdict):
        if errdict['status'] == 'ERR_PAGE_NOT_FOUND':
            return "Page '%s' not found in '%s'. Valid pages are: %s"%(errdict['page'], errdict['filename'], errdict['available_pages'])
        if errdict['status'] == 'ERR_OPEN_FAILED':
            return "Opening %s failed with error message:\n%s"%(errdict['filename'], errdict['errmsg'])
        return "%s"%errdict

    def convert_visio(self):
        """
        Convert used pages from Visio files (queued during parsing)
        """
        for visiofile, jobs in g.visio2convert.copy().iteritems():
            # Look to see if we already have the SVG and if it's newer than the visio file.
            # If so, skip the export
            for job in jobs[:]:
                if exists_and_newer(job["fnout"], visiofile):
                    jobs.remove(job)
                    # If PNG file exists too, we probably wanted to replace SVG with PNG
                    pngfile = util.replace_ext(job["fnout"], '.png')
                    if exists_and_newer(job["fnout"], pngfile):
                        g.svg_fixes.append({"svg": job["fnout"], "png": pngfile})
            if not jobs:
                del g.visio2convert[visiofile]
        if not g.visio2convert:
            # Nothing to do
            return
        docsrv.start_session()
        try:
            for visiofile, jobs in g.visio2convert.iteritems():
                cmd_pages = "|".join(["%s|%s"%(job["page"], job["fnout"]) for job in jobs])
                docsrv.submit_job("VISIO_EXPORT_PAGES_BY_NAME|%s|%s"%(visiofile, cmd_pages))
        finally:
            results = docsrv.end_session()
        if results['errors']:
            errstr = '\n'.join("  %s"%self.friendly_errmsg(x) for x in results['errors'])
            error("Visio conversion error:\n%s"%errstr)
        for visiofile, jobs in g.visio2convert.iteritems():
            for job in jobs:
                timestamp(job["fnout"])
        for warn in results['warnings']:
            if warn['status'] == "WARN_NEEDS_PNG":
                g.svg_fixes.append({"svg": warn['svgname'], "png": warn['pngname']})
                timestamp(warn['pngname'])


    def run_plugin(self, token, code, div_style, args, kwargs):
        try:
            # get the function to execute (guaranteed to exist by upstream code)
            func = self.token2func[token.typ.lower()]
        except KeyError:
            # Fall back to name-based match
            func = getattr(self, token.typ.lower())
        kwargs.update(div_style=div_style)
        start_time = time.time()
        if g.opts.perf: sys.stdout.write("Running %s..." % (token.value.splitlines()[0]))
        try:
            inspect.getcallargs(func, code, *args, **kwargs)
        except TypeError:
            print "While processing %s token:\n%s"%(token.typ, token.value)
            help(func)
            print "args=%s, kwargs=%s"%(args, kwargs)
            error("Incorrect argument list for function '%s'"%token.typ.lower())
        try:
            if re.search(r'(?<![\'"\\])```', code):
                raise ParseError("Nested plugins are not supported. Did you forget to close plugin body?")
            result = func(code, *args, **kwargs)
            if g.opts.perf: sys.stdout.write(" completed in %.1fs\n" % (time.time() - start_time))
            return result
        except:
            print "While processing %s token:\n%s"%(token.typ, token.value)
            raise

    def add_named_anchors(self, s):
        # For OPEN/FIXME/TODO, add named "anchors", so that we could auto-link to them

        def anchor_subst(pattern, name, s):
            def repl(matchobj):
                g.anchor_count[name] += 1
                return '<a name="%s_%04d" class="%s">%s</a>'%(name, g.anchor_count[name], name, matchobj.group(0))
            return re.sub(pattern, repl, s)

        # 'OPEN: fix me' -> '<a name="open_0001">OPEN</a>: fix me'
        s = anchor_subst(util.fixme_pattern('OPEN'), "open", s)
        s = anchor_subst(util.fixme_pattern('FIXME'), "fixme", s)
        s = anchor_subst(util.fixme_pattern('TODO'), "todo", s)
        return s

    def insert_file(self, fullpath):
        """
        Read file and collect new tokens
        """
        # Read the file and insert contents into the token queue
        insert_code = open(fullpath, "r").read()
        # Insert a newline at the start
        insert_code = "\n\n" + insert_code + "\n\n"
        new_tokens = [t for t in self.tokenize(insert_code, self.token_specification)]
        return new_tokens

    def parse(self, fname, output):
        """
        Parse the file, build output collateral as needed
        """
        src_code = open(fname, "r").read()
        dirname = os.path.dirname(os.path.abspath(fname))

        # Make sure we have 'auto' instantiated!
        make_dir(dirname, self.auto)

        # self.dirs[0] - top level file dir
        # self.dirs[1] - first level inline file dir
        # ...
        # self.dirs[-1] - directory of currently processed document
        #
        # Usage:
        #   - Use self.dirs[0] when building links relative to top level document
        #   - Use self.dirs[-1] when searching for included files and generating
        #     automatic content 
        self.dirs = [dirname]
        g.hlevel = [0]

        hlevel = 0 # local one is for tracking level within a document

        fignum = 0

        # Set up our token specification
        self.token_specification = []

        # Comments have highest precedence so that we can comment out plugins, inlines, etc..
        self.token_specification.append(("COMMENT", "<!--.*?-->"))

        # Add plugins
        for token in self.legal_tokens:
            self.token_specification.append((token.upper(), "```%s\\b.*?^\s*```(?!\w)" % token.lower()))

        # Add verbatim (`<blah>`) as a token, to skip 'c:\' local drive check in it
        self.token_specification.append(("VERBATIM", r"(?<!\\)`.*?`"))

        # Images, for dependency logging
        # FIXME :: in future, unify inline_file and top-level token processing
        self.token_specification.append(("IMAGE", r"!\[[^\]]*\]\([^\)]+\.(?:jpg|png|svg|JPG|PNG)\)"))

        # Searches for tags of the form: ^[path/to/file.md]$
        # And inserts that file. Tracks heading level and ajdusts inserted file to match
        # the heading level of the containing file
        # User may also include a file glob if desired (*, ?).
        # If the user has defined the tag with a !, the heading level is reset (i.e., supplied
        # by the contained chapter)
        self.token_specification.append(("INSERT_FILE", r"(?m)^\s*\[!?[\w\-\*\?\s\/\.]+.mm?d\]"))
        self.token_specification.append(("HEADER", "(?m)^#+[^#]"))

        # Add code section (````<blah>```) as a token, to skip parsing opens/fixmes in them
        self.token_specification.append(("CODE", "```.*?```"))

        # need to modify list of tokens from the run_plugin function, so convert source
        # to global list of tokens. maybe not the most effective approach..
        self.tokens = [t for t in self.tokenize(src_code, self.token_specification)]

        while self.tokens:
            token = self.tokens.pop(0)
            if (token.typ.lower() in self.legal_tokens):
                s = self.parse_plugin(token)
            elif (token.typ == "IMAGE"):
                s = self.parse_image(token)
            elif token.typ == "MISMATCH":
                s = cleanstr(token.value)
                s = self.add_named_anchors(s) # annotate OPENS/FIXMEs
            elif token.typ in ("COMMENT", "VERBATIM"):
                s = cleanstr(token.value)
            elif token.typ == "INSERT_FILE":
                s = self.parse_insert_file(token)
            elif token.typ == "PUSH_DIR":
                _dir, no_hlevel =  token.value
                self.dirs.append(_dir)
                g.hlevel.append(0 if no_hlevel else hlevel)
                s = ""
            elif token.typ == "POP_DIR":
                self.dirs.pop()
                g.hlevel.pop()
                s = ""
            elif token.typ == "HEADER":
                s = re.sub("(#+)", r"\1%s"%("#" * g.hlevel[-1]), token.value)
                hlevel = s.count("#") # Assume header title doesn't have # inside (bad assumption) 
            else:
                raise Exception("Did not understand token %s" % token.typ)

            s = s.encode('ascii', 'xmlcharrefreplace')

            output.write(s)

            # Check for references to local drive in the output.. catch lots of bugs
            if token.typ not in ("COMMENT", "VERBATIM", "CODE"):
                for line in s.lower().splitlines():
                    if 'c:\\' in line.lower():
                        # The check is very crude, may need to improve in future
                        raise Exception("Reference to local drive in output:\n%s"%line)

        # FIXME - eventually we would prefer to delete this file once it has
        #         been fully processed.
        output.close()


    def parse_insert_file(self, token):
        """
        Token parser for inline files
        """
        fname = re.search(r"\[(.*)\]", token.value).group(1).replace("/", "\\")
        no_hlevel = fname.startswith("!")
        if no_hlevel:
            fname = fname[1:]
        # Find the file
        fullpath = os.path.join(self.dirs[-1], fname)

        # Log the dependency before expanding the glob. If the glob doesn't match, that's fine too,
        # we want to allow for the case there were no files matching, and then some appeared, and 
        # we need to trigger a rebuild due to that
        log_dependency(self.fname, fullpath)

        s = ""

        # Implement glob
        if (len(glob.glob(fullpath)) == 0):
            # Must not be valid.  Ignore it.
            if g.opts.verbose:
                print "Couldn't find inline file: '%s'"%fullpath
            s = token.value
        else:
            for f in sorted(glob.glob(fullpath)):
                new_tokens = self.insert_file(f)
                push_dir = self.token("PUSH_DIR", (os.path.dirname(fullpath), no_hlevel), 0, 0)
                pop_dir = self.token("POP_DIR", 0, 0, 0)
                self.tokens = [push_dir] + new_tokens + [pop_dir] + self.tokens
            s = ""
        return s

    def parse_image(self, token):
        """
        Token parser for images
        """
        s = cleanstr(token.value)
        image_full_path = os.path.join(self.dirs[-1], re.search(r'\[[^\]]*\]\s*\(([^\)]+)\)', s).group(1))
        log_dependency(self.fname, image_full_path)

        # modify image path to be relative to top-level document directory
        image_rel_path = os.path.relpath(image_full_path, self.dirs[0])

        # regex was modified to cover subdirectories that start as numbers.
        # Previously we were using "\1" in the substitute string and when that
        # was appended to an image_rel_path that starts with a number, it was producing
        # garbage.
        s = re.sub(r'(?P<title>\[[^\]]*\]\s*\()[^\)]+\)', r'\g<title>%s)'%image_rel_path.replace('\\', '/'), s)
        return s

    def parse_plugin(self, token):
        """
        Token parser for custom plugins
        """
        s = None
        m = re.search(r"^\s*```%s\((?P<args>[^\n]*)\)(?:\s*\{(?P<div_style>[^\n]+)\})?(?P<code>.*)```\s*$" % token.typ.lower(), token.value, re.DOTALL)
        div_style = None
        if (m != None):
            code, div_style = m.group('code'), m.group('div_style')
            if (m.group('args').rstrip() == ""):
                s  = self.run_plugin(token, code, div_style, [], {})
            else:
                try:
                    def a(*args, **kwargs): return args, kwargs
                    exec("args, kwargs = a(%s)" % m.group('args').replace("\\", "\\\\"))
                except:
                    raise ParseError("Syntax error parsing argument list in '%s'" % token.value)

                s  = self.run_plugin(token, code, div_style, args, kwargs)
        else:
            m = re.search(r"^\s*```(?:\s*\{(?P<div_style>[^\n]+)\})?%s(?P<div_code>.*)```$" % token.typ.lower(), token.value, re.DOTALL)
            if (m != None):
                # No arguments and no parenthesis
                code, div_style = m.group('div_code'), m.group('div_style')
                s  = self.run_plugin(token, code, div_style, [], {})

        if (s == None):
            raise Exception("Processing of %s failed." % (token.typ.lower()))

        s = cleanstr(s)

        # { <css_style> } after the first line of ``` is to surround the generated
        # content in <div style="..."> </div> with specified style
        if div_style is not None:
            s = '<div style="%s">%s</div>'%(m.group('div_style'), s)

        return s

def title2id(s):
    # Create linkable title from arbitrary capition string
    ans = re.sub(r'[^\w]+', r'-', s.lower())
    return ans

def write_svg_html(svg_zoom_file, svg, title):
    """
    Given an SVG string, integrate it into our SVG zoom template
    and dump to the requested directory
    """

    # Read our template
    s = open(g.svg_template, "r").read()

    # remove xml qualifier
    svg = re.sub(r"<\?xml.*?\?>", "", svg)

    # remove new plantuml attributes that break aspect ratio
    svg = svg.replace(' contentScriptType="application/ecmascript" contentStyleType="text/css" preserveAspectRatio="none"', '')

    s = s.replace("%%TITLE%%", title)
    s = s.replace("%%SVG%%", svg)
    zf = open(svg_zoom_file, "w")
    zf.write(s)
    zf.close()

def find_xml(fname_glob, dirname, find_all=False):
    """
    Search up the tree to find the first instance of this xml file in an assets
    dir.  
    """
    fname_matches = []
    while (True):
        look_in = os.path.join(dirname, "assets")
        test_path = os.path.join(look_in, fname_glob)
        glob_result = glob.glob(test_path)
        if (len(glob_result) > 0):
            # Found it
            if (find_all == False):
                return glob_result[0]
            else:
                # Add it to our list and keep going
                for f in glob_result:
                    fname_matches.append(f)
                dirname = os.path.split(dirname)[0]
        else:
            dirname = os.path.split(dirname)[0]
            if dirname.lower() == repo_root.lower():
                # we have exhausted the path tree.  Give up.
                if (len(fname_matches) == 0):
                    return None
                else:
                    return fname_matches
            elif dirname.lower() == "c:\\":
                # we have exhausted the path tree.  Give up.
                if (len(fname_matches) == 0):
                    return None
                else:
                    return fname_matches

    return fname_matches

def inline_svg(dirname, svg_full_path, title, fmt, div_style):
    """
    Given an SVG file and title, inline it and return the string
    """

    def uniquify_classes(text):
        # Unless we make style classes unique, they may overlap from different svg
        # in the same document
        svg_rel_path = os.path.relpath(svg_full_path, dirname)
        suffix = hashlib.md5(svg_rel_path).hexdigest()[-6:]
        classes = re.findall(r'class="(\w+)"', text)
        re_class = r'\.(%s)\b'%('|'.join(classes))
        def mod_style(mo):
            return re.sub(re_class, r'.\1_'+suffix, mo.group(0))
        text = re.sub(r'(?s)<style.+?</style>', mod_style, text)
        text = re.sub(r'class="(\w+)"', r'class="\1_%s"'%suffix, text)
        return text

    # integrate the SVG here and add in the SVG template link
    svg_zoom_file = re.sub(".svg$", "_zoom.html", svg_full_path)

    # Read in the SVG file
    with open(svg_full_path, "r") as myfile:
        svg = myfile.read()

    #svg = re.sub(r"<v:[^>]+>", "", svg) # Visio data isn't useful

    svg = uniquify_classes(svg)

    # Convert height/width attrubutes to style attributes for consistent
    # rendering between Chrome and IE
    svg = hack_svg_height_width(svg, fmt, div_style)
    write_svg_html(svg_zoom_file, svg, title)
    timestamp(svg_zoom_file)
    zoom_rel_path = os.path.relpath(svg_zoom_file, dirname)

    # Embed SVG into HTML
    svg = re.sub(r"(?s)<\?xml.*?>", "", svg, count=1)
    svg = re.sub(r"(?s)<!DOCTYPE.*?>", "", svg, count=1)
    svg = re.sub(r"(?s)<!\[CDATA\[(.*?)\]\]>", r"\1", svg)

    # Include the classes used by pandoc to get formatting correct
    s = "\n\n<div class=\"figure\">\n"
    s += svg
    hyperlink = '<a xmlns="http://www.w3.org/2000/svg" xlink:href="%s" xmlns:xlink="http://www.w3.org/1999/xlink"><rect x="0" y="0" width="100%%" height="100%%" fill-opacity="0" style="fill:white"/></a>' % (zoom_rel_path)
    s = unicode(s, 'utf-8')
    s = s.replace("</svg>", hyperlink + "</svg>")
    s += "<p class=\"caption\">%s</p></div>" % (title)

    s = s.encode('ascii', 'xmlcharrefreplace')

    return s

def hack_svg_height_width(svg, fmt, div_style):
    """
    Convert height/width attrubutes to style attributes for consistent
    rendering between Chrome and IE
    """
    m = re.search("<svg.*?>", svg, re.DOTALL)
    start = m.start()
    end = m.end()

    final_svg = svg[:start]
    svg_tag = svg[start:end]

    # If style doesn't exist, add it in for now.  MS explorer doesn't like the lack of style
    m = re.search('\s*viewBox="([^"]+)"', svg_tag, re.IGNORECASE)
    if (m != None):
        x1, y1, x2, y2 = [float(x) for x in m.group(1).split()]
        width, height = int(x2 - x1), int(y2 - y1)

        # If user has provided a div style width in pixels, scale SVG to match
        if div_style is not None:
            mo = re.search(r'(?i)width\s*:\s*([\d\.]+)\s*(?:px|;|$)', div_style)
            if mo:
                user_width = float(mo.group(1))
                ratio = user_width / width
                width = int(width * ratio + 0.5)
                height = int(height * ratio + 0.5)

        # FIXME Work-around for tall SVG display in wkhtml2pdf
        # http://stackoverflow.com/questions/40513877/wkhtmltopdf-javascript-element-clientwidth-returns-zero
        if fmt == "pdf":
            MAX_WIDTH = 800.0
            if (width > MAX_WIDTH):
                ratio = MAX_WIDTH / width
                width = int(width * ratio + 0.5)
                height = int(height * ratio + 0.5)

        # Remove style, height and width
        svg_tag = re.sub('\s*(width|height|style)="[^"]+"', "", svg_tag, re.DOTALL)

        # Add back in our corrected style
        svg_tag = re.sub("\s*>$", " style=\"width:%spx; height:%spx\">" % (width, height), svg_tag, re.DOTALL)

    final_svg += svg_tag
    final_svg += svg[end:]

    return final_svg

def sendme_email(dirname, filename):
    from email.MIMEMultipart import MIMEMultipart
    from email.MIMEText import MIMEText
    from email.MIMEImage import MIMEImage
    import smtplib

    try:
        me = _subprocess.check_output(['git', 'config', 'user.email']).strip()
    except:
        # Use a compute server and idsid instead
        me = toolcfg["default_email"]

    msg = MIMEMultipart('related')
    msg['subject'] = "pm_doc"
    msg['To'] = me
    msg['From'] = me

    imgs = []

    doc = bs4.BeautifulSoup(open(filename).read(), "html.parser")
    for img_id, img in enumerate(doc.find_all("img")):
        fn_img = os.path.join(dirname, img["src"])
        msgImage = MIMEImage(open(fn_img, "rb").read())
        msgImage.add_header('Content-ID', '<img%d>'%img_id)
        img["src"] = "cid:img%d"%img_id
        imgs.append(msgImage)

    msg.attach(MIMEText(str(doc), 'html'))

    for img in imgs: msg.attach(img)

    s = smtplib.SMTP(toolcfg['smtp_server'])
    s.sendmail(me, [me], msg.as_string())

    #open('email_debug.txt', 'wb').write(msg.as_string())

def get_src_path(fn):
    # This function tries to determine the source path for the file
    # relative to the repo root, even when mmd2doc is run on a file
    # in the 'distrib' directory
    src_dir, src_path = os.path.split(fn)
    # Find repo root, if none return bare name
    cfg = util.get_config(src_dir)
    if cfg is None:
        return 'UNRELEASED', src_path # bare file name
    relpath = os.path.relpath(fn, cfg['root'])
    # Read the deptree.db, if exists
    fn_deptree = os.path.join(cfg['root'], "deptree.db")
    if os.path.exists(fn_deptree):
        deptree_conn = sqlite3.connect(fn_deptree)
        result = deptree_conn.execute("SELECT src_path FROM distmap WHERE dist_path=?", (relpath,))
        row = result.fetchone()
        if row is not None:
            relpath = row[0]
        deptree_conn.close()
    return cfg["repo_name"], relpath.replace('\\', '/')

def build_doc(opts):
    # Fixme - look into options for handling criticmarkup
    # Use glob to expand it

    final_file_list = []
    for f in opts.markdown_files:
        globlist = glob.glob(f)
        for x in globlist:
            final_file_list.append(x)

    if opts.markdown_files and not final_file_list:
        raise Exception('Couldn\'t locate input file(s): %s'%(', '.join(opts.markdown_files)))

    for filename in final_file_list:

        fnabs = os.path.abspath(filename) # also normalizes slashes to backslashes

        ftype = os.path.splitext(fnabs)[1]
        if (not ftype in valid_ftypes):
            raise Exception("Invalid file type %s.  Valid types include: %s" % (ftype,  ",".join(valid_ftypes)))

        if (opts.fmt == "docx"):
            outfile = util.replace_ext(fnabs, ".docx")
        elif (opts.fmt == "html"):
            if opts.email:
                outfile = util.replace_ext(fnabs, ".email.html")
            else:
                outfile = util.replace_ext(fnabs, ".html")
        elif (opts.fmt == "pdf"):
            pdf_file = util.replace_ext(fnabs, ".pdf")     # Final pdf output
            outfile = util.replace_ext(fnabs, "_pdf.html") # Temporary html to feed to wkhtmltopdf
            log_dependency(pdf_file, fnabs)
        cleanup_deptree(outfile)
        log_dependency(outfile, fnabs)
        cwd_outfile = os.path.split(outfile)[1]

        # Check for any pre-processing
        infile = fnabs
        if (not opts.nopre):
            # preproc is *enabled* (default behavior)
            preproc = PandocPreproc(fnabs, fmt=opts.fmt)
            infile = preproc.outf.name # tmp file in tmp directory
                                       # TODO: wouldn't hurt to clean up those tmp files from time to time

        dirname = os.path.dirname(fnabs)
        assert dirname != ""

        # Add toolver and other variables
        variables = ' --variable=toolver:"%s"'%util.get_toolver()
        variables += ' --variable=date:"%s"'%util.date()

        # repo name for subscriptions, source name for comments and subscriptions
        src_repo, src_path = get_src_path(fnabs)
        variables += ' --variable=src_path:"%s:%s"'%(src_repo, src_path)

        # release script will overwrite username meta data-* field, but it is useful
        # to populate it here with something for local debug
        variables += ' --variable=username:"%s"'%os.environ['USERNAME']

        # Call pandoc to render (pre-processed) markdown
        if (opts.fmt == "docx"):
            _call('"%s" %s -s "%s" -t docx --normalize --number-sections --reference-docx=%s -o "%s"' % (g.pandoc, variables, infile, g.dotx, cwd_outfile), cwd=dirname)

        elif (opts.email):
            cmd = '"%s" "%s" -o "%s" %s'%(g.pandoc, infile, cwd_outfile, opts.pandoc_args)
            cmd += ' --template "%s"'%g.email_template
            # FIXME: Formulas not currently supported

            _call(cmd, cwd=dirname)

            sendme_email(dirname, outfile)

        elif (opts.fmt == "html" or opts.fmt == "pdf"):
            cmd = '"%s" "%s" -o "%s" %s'%(g.pandoc, infile, cwd_outfile, opts.pandoc_args)

            # Common always present options
            cmd += " --standalone --self-contained --section-divs"

            # Formula rendering
            cmd += ' --mathjax'

            if opts.slides or fnabs.endswith(".mds"):
                relative_reveal = os.path.relpath(g.reveal_js, dirname).replace("\\", "/")
                cmd += ' --to revealjs'
                if (opts.template == "auto"):
                    cmd += ' --template "%s"'%g.reveal_template
                else:
                    cmd += ' --template "%s"'%(os.path.join(g.template_path, opts.template))
                cmd += ' --no-highlight'
                cmd += ' --variable=revealpath:"%s"'%relative_reveal
            else:
                if (opts.template == "auto"):
                    cmd += ' --template "%s"'%g.html_template
                else:
                    cmd += ' --template "%s"'%(os.path.join(g.template_path, opts.template))
                cmd += ' --highlight-style=tango --normalize'
                cmd += ' --include-in-header="%s"'%os.path.join(g.css_path, "common.css")
                cmd += ' --include-in-header="%s"'%g.pm_doc_js
                if (opts.fmt == "pdf"):
                    cmd += " --number-sections"
                else:
                    cmd += " --toc --toc-depth=6"
                    cmd += ' --css "%s"'%(g.font_awesome) # Only used for side bar, do not include for PDF
                if (opts.live):
                    cmd += "--include-in-header=%s" % g.liverefresh
                # apply user-specified style
                if g.opts.style is not None:
                    css = os.path.join(g.css_path, "%s.css"%opts.style)
                    if not os.path.exists(css):
                        error("Unable to find %s from style reference '%s'"%(css, opts.style))
                    cmd += ' --include-in-header="%s"'%css

            cmd += variables

            _call(cmd, cwd=dirname)

            def replace_svg_ref(mo):
                # Replace SVG references with actual content
                fname, title, div_style = g.svg_hash[mo.group(1)]
                return inline_svg(dirname, fname, title, opts.fmt, div_style)

            ids = set()
            def get_id(text):
                # Generate unique 8-char IDs based on the contents
                # For repeated contents just generate a random number
                ans = hashlib.md5(text).hexdigest()[-8:]
                if ans in ids: ans = get_id(text + g.last_id)
                ids.add(ans)
                g.last_id = ans
                return ans

            # Post-process pandoc's HTML output
            s = open(outfile).read()
            s = re.sub('<!-- INLINE_SVG (\w+) -->', replace_svg_ref, s)
            if opts.fmt != 'pdf':
                # By some inexplicable reason including fonts break mathjax in PDF
                s = s.replace('<!-- FONTS -->', g.fonts, 1)
            s = s.replace('<!-- MATHJAX -->', g.mathjax4pdf if opts.fmt == "pdf" else g.mathjax, 1)
            s = s.replace('%PMDB_SERVER_URL%', "'%s'"%toolcfg['pmdb_server'], 1)

            doc = bs4.BeautifulSoup(s, "html5lib")
            # Convert native tables into mmd2doc-style tables
            for tbl in doc("table"):
                cap = tbl.find("caption")
                if not cap: continue
                assert not (tbl.parent.name == "div" and tbl.parent.attrs.get("class", None) == "table")
                tid = title2id("table-" + cap.string)
                div = doc.new_tag("div", **{"class":"table", "id":tid})
                pcap = doc.new_tag("p", **{"class":"table_caption"})
                cap.name = "p"
                cap.attrs["class"] = "table_caption"
                tbl.wrap(div)
                tbl.insert_after(cap)

            # Add paragraph ids for easier feedback location
            for e in doc.find_all(['p', 'li']):
                e['id'] = get_id(str(e))
            open(outfile, 'w').write(str(doc))

            # If PDF is requested, take the next step to convert the html to PDF
            if (opts.fmt == "pdf"):
                pdf_footer_link = "file:///" + os.path.abspath(g.pdf_footer).replace("\\", "/")
                # javascript-delay 25000 needed to make sure wkhtmltopdf doesn't cut off
                # mathjax and other javascript in the middle
                _call('"%s" --javascript-delay 25000 --footer-html "%s" --margin-bottom 15mm --margin-top 15mm --print-media-type "%s" "%s"' % (g.wkhtmltopdf, pdf_footer_link, outfile, pdf_file), errors_are_warnings=True)

                # And go ahead and remove the source html file when done
                #os.remove(outfile)

            if (opts.chrome):
                chrome(outfile)
        #endif HTML or PDF

        log_dependency(outfile, outfile) # self-dependency to track completion

def cleanup_leading_spaces(text):
    lines = text.splitlines()
    nspaces = [len(x)-len(x.lstrip()) for x in lines[1:] if x.strip() != ""]
    if nspaces == []: return text
    min_n_spaces = min(nspaces)
    lines[1:] = [re.sub(r'^\s{%d}'%min_n_spaces, '', x) for x in lines[1:]]
    return '\n'.join(lines)

def packet2html(lines, fields, regname, width, resolution="bit", name_defaults = False, exclude_desc=False):
    """
    Extract out bit fields and produce a packet definition

    A packet is a compressed visualization of a series of bit fields followed by bit
    level definition
    """

    # Need to pad with newlines, else pandoc can get VERY confused :)
    packet = '\n\n<div class="packet">\n'
    if (regname != None):
        packet += "\n\n<p><b>%s</b>:</p>\n" % regname

    wdclass = 'wd64'
    if width <= 32: wdclass = 'wd32'
    if width <= 16: wdclass = 'wd16'

    packet += '<table class="packet %s">\n'%wdclass
    packet += "  <tr>\n"

    # FIXME - save HTML and embed this style in the css

    # First print the header with bit positions
    for i in reversed(range(int(width))):
        washout = '' if (i%8 == 0) or (i == width-1) or width <=16 else ' style="color:white"'
        packet += '  <td class="bitnum %s"%s>%d</td>\n'%(wdclass, washout, i)
    if len(lines) > 1:
        if (resolution == "bit"):
            packet += "  <td class=\"bitnum\">Bit</td>\n"
            packet += "  <td class=\"bitnum\">Byte</td>\n"
        else:
            # byte resolution
            packet += "  <td class=\"bitnum\">Byte</td>\n"
            packet += "  <td class=\"bitnum\">Qword</td>\n"

    packet += "  </tr>\n"

    # Walk each line and dump fields within them
    i = 0
    for line in lines:
        line_bitpos = width - 1
        packet += "  <tr>\n"

        # Should already be ordered by msb to lsb within the line

        for f in line:
            msb_in_line = (f.msb) % width
            if (msb_in_line < line_bitpos):
                # fill in blanks
                packet += "  <td class=\"rsvd\" colspan=%s align=center></td>\n" % (line_bitpos - msb_in_line)
                line_bitpos = msb_in_line
            if (name_defaults and f.reset_default != None):
                if (isinstance(f.reset_default, int) and f.reset_default > 9):
                    packet += "  <td colspan=%s align=center>%s (0x%x)</td>\n" % (f.msb - f.lsb + 1, f.name, f.reset_default)
                else:
                    packet += "  <td colspan=%s align=center>%s (%s)</td>\n" % (f.msb - f.lsb + 1, f.name, f.reset_default)
            else:
                if f.name.strip() == "":
                    packet += "  <td class=\"rsvd\" colspan=%s align=center>%s</td>\n" % (f.msb - f.lsb + 1, f.name)
                else:
                    packet += "  <td colspan=%s align=center>%s</td>\n" % (f.msb - f.lsb + 1, f.name)
            line_bitpos = ((f.lsb) % width) - 1

        if len(lines) > 1:
            packet += '  <td class="bitnumr">%d</td>\n' % (i * width)
            packet += '  <td class="bitnumr">%d</td>\n' % (i * width / 8)
        packet += "  </tr>\n"
        i += 1

    packet += "  </tr>\n"
    packet += "</table>\n"

    # Now, add the description of each detailed field
    if (not exclude_desc):
        packet += register2html(fields, None, None, 'packet')

    packet += '</div>\n'
    return packet


def register2html(fields, attrs, regname, cls=""):
    """
    Extract out bit fields and produce a register definition

    Input field list is already sorted by lsb
    """
    # See if access type or reset default exists anywhere
    has_access_type = False
    has_reset_default = False
    colspan = 2
    if (fields != None):
        for f in fields:
            if (f.access_type != None): has_access_type = True
            if (f.reset_default != None): has_reset_default = True

    if (has_access_type): colspan += 1
    if (has_reset_default): colspan += 1

    # With several column attributes, field name looks better at the top of description
    field_in_desc = (colspan >= 3)
    if field_in_desc: colspan -= 1

    # Add name as an attribute, if not specified
    if attrs is None: attrs = []
    if regname is not None and not any(x[0].upper() == 'NAME' for x in attrs):
        attrs.insert(0, ['Name', regname])

    table = '<table class="register %s">\n'%cls

    # Add column elements so that css can specify column attributes
    table += '<col class="register %s bits" />\n'%cls
    if not field_in_desc:
        table += '<col class="register %s field" />\n'%cls
    if (has_access_type):
        table += '<col class="register %s access" />\n'%cls
    if (has_reset_default):
        table += '<col class="register %s default" />\n'%cls
    table += '<col class="register %s description" />\n'%cls
    
    table += '<tbody class="nobreak">'

    if (attrs != None):
        for attr in attrs:
            # FIXME - remove <p></p> wrapping from markdown?
            md = cleanstr(attr[1])
            # compress to a single line
            md = re.sub("^<p>", "", md)
            md = re.sub("</p>$", "", md)
            table += "<tr><td colspan=%d align=right><b>%s</b></td><td>%s</td></tr>\n" % (colspan, attr[0], md)

    if (fields == None or len(fields) == 0):
        # We are done
        table += "</table>"
        return table

    table += "  <tr>\n"
    table += "  <th>Bits</th>\n"
    if not field_in_desc:
        table += "  <th>Field</th>\n"
    if (has_access_type):
        table += "  <th>Access</th>\n"
    if (has_reset_default):
        table += "  <th>Default</th>\n"
    table += "  <th>Description</th>\n"
    table += "  </tr>\n"

    for i, f in enumerate(fields):
        # Check for overlapping fields
        assert isinstance(f.msb, int) and isinstance(f.lsb, int)
        if i > 0 and f.lsb <= fields[i-1].msb:
            raise Exception("Fields %s and %s are overlapping"%(f.name, fields[i-1].name))

        desc = cleanup_leading_spaces(f.desc)
        # Unfortunately, several docs still have this unclean text.
        desc = cleanstr(desc)

        # compress to a single line
        desc = re.sub("^<p>", "", desc)
        desc = re.sub("</p>$", "", desc)
        if (f.enums != None and len(f.enums) > 0):
            # Populate enums
            desc += enums2html(f.enums)

        table += "  <tr>\n"
        table += '  <td class="field_bits">%s:%s</td>\n' % (f.msb, f.lsb)
        if not field_in_desc:
            # Insert soft hyphens at underscores to prevent very long field names from
            # stretching the table too much (only works in Chrome)
            table += '  <td class="field_name">%s</td>\n' % f.name.replace("_", "_<wbr>")
        if (has_access_type):
            table += '  <td class="field_access">%s</td>\n' % f.access_type
        if (has_reset_default):
            if (isinstance(f.reset_default, str)):
                table += '  <td class="field_reset">%s</td>\n' % f.reset_default
            elif (f.reset_default < 2):
                table += '  <td class="field_reset">%d</td>\n' % f.reset_default
            else:
                table += '  <td class="field_reset">0x%x</td>\n' % f.reset_default
        if field_in_desc:
            table += '  <td><p class="field_name">%s</p>%s</td>\n' % (f.name, desc)
        else:
            table += "  <td>%s</td>\n" % desc
        table += "  </tr>\n"
        if i == 0:
            # Group header and first row such that header is never alone on a page
            # (doesn't work in WebKit today, but maybe will someday)
            table += "  </tbody>\n"

    table += "</table>"

    return table

def enums2html(enums):
    """
    Given a list of enumerated value / name pairs, create an HTML output
    to represent legal combinations
    """
    s = "\n"
    #s += "<br><u>Legal Settings</u><br>\n<table>\n"
    s += '<table class="enum">\n'
    s += "  <thead><tr><th>Value</th><th>Definition</th></tr></thead>\n"
    for e in enums:
        s += "  <tr><td align=center>%s</td><td align=left>%s</td></tr>\n" % (e[0], e[1])
    s += "</table>\n"
    return s

def get_figure_id(title=""):
    """
    Return unque string for this file build
    Source file could be a figure or table or whatever.  This function
    just names it ambiguously "f%d"
    """
    g.figure_count += 1
    if (title == ""):
        return "f%d" % g.figure_count
    else:
        return "f%d.%s" % (g.figure_count, title)

def save_url(url, dirname):
    """
    Given a url and directory name, save the file locally
    Note: dirname should be 'auto' directory, not 'assets'. Using 'assets' for downloads
    while also checking it into the repo brakes dependency checking and leads to always
    triggering document rebuild by build.py, given that external document is newer than the one in 'assets'
    (even if the copy in "distrib" is already updated).
    """
    import filecmp
    import msweb

    dstfile = os.path.join(dirname, os.path.split(url)[1])
    dstfile = dstfile.replace("%20", " ")

    try:
        resp, body = msweb.http_request(url, {})
        assert resp.status == 200
    except:
        # Failed to download, that's OK
        warn("Read failed.  Reverting to checked in file copy.  URL=%s" % url)
        return dstfile

    tmpfile = dstfile
    if (os.path.exists(dstfile)):
        # write to a tmp file, check to see if there are diffs, and copy
        # only if there are.
        f = _tempfile.TemporaryFile("w+b", delete=False)
        tmpfile = f.name
    else:
        f = open(tmpfile, "wb")

    f.write(body)
    f.close()

    if (tmpfile != dstfile):
        # Check for diffs, copy if different.
        if (not filecmp.cmp(tmpfile, dstfile)):
            print "Copying %s to %s" % (tmpfile, dstfile)
            copy2(tmpfile, dstfile)

        # delete the tempfile
        os.remove(tmpfile)

    return dstfile

def _call(cmd, wait=True, verbose=False, errors_are_warnings=False, **args):
    verbose |= g.opts.verbose
    if (isinstance(cmd, list)):
        if verbose:
            print " ".join(cmd)
    else:
        if verbose:
            print cmd

    info = _subprocess.STARTUPINFO()
    if (not verbose):
        info.dwFlags |= _subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = _subprocess.SW_HIDE

    if (wait):
        try:
            process = _subprocess.check_output(cmd, creationflags = _subprocess.CREATE_NEW_CONSOLE, startupinfo = info, stderr=_subprocess.STDOUT, **args)
            return process
        except _subprocess.CalledProcessError, e:
            if (errors_are_warnings):
                warn("Ignoring error when running `%s`\n\nError:\n%s" % (cmd, e.output))
            else:
                error("Error incurred when running `%s`\n\nError:\n%s" % (cmd, e.output))

    else:
        try:
            process = _subprocess.Popen(cmd, creationflags = _subprocess.CREATE_NEW_CONSOLE, startupinfo = info, stderr=_subprocess.STDOUT, **args)
            return process
        except _subprocess.CalledProcessError, e:
            error("Error incurred when running `%s`\n\nError:\n%s" % (cmd, e.output))

def equal(fname, code):
    """
    Check to see if the code matches the file
    """
    f_src = open(fname).read()
    if (f_src == code):
        return True
    else:
        return False

def timestamp(fname):
    """
    Create a file that is our timestamp for a generated file
    This is written to fool the syncplicity which keeps on reverting
    timestamps
    """
    f = open(fname + ".time", "w")
    f.write("Updated at %s" % time.time())
    f.close()


def exists_and_newer(generated_file, source_file):
    """
    Return True if the generated file exists and is newer than the source file
    """
    if (not os.path.exists(generated_file) or not os.path.exists(generated_file + ".time")):
        return False
    if (not os.path.exists(source_file)):
        return False

    gen_time = os.stat(generated_file + ".time").st_mtime
    src_time = os.stat(source_file).st_mtime
    if (gen_time < src_time):
        return False
    else:
        return True

def make_dir(root, subdir):
    dirname = os.path.join(root, subdir)
    if not os.path.exists(dirname):
        try:
            os.mkdir(dirname)
        except:
            # Don't fail right away just on mkdir exception: in parallel build
            # another process may have created the directory after we checked
            if not os.path.exists(dirname):
                print "Failed to create directory:", dirname
                raise
    return dirname

def cleanstr(s):
    """
    Remove non-ascii (some specific and frequent chars > 0x7f)

     's/\%x85/.../ge'
     's/\%x91/' . "'/ge"
     's/\%x92/' . "'/ge"
     's/\%x93/"/ge'
     's/\%x94/"/ge'
     's/\%x95/*/ge'
     's/\%x96/-/ge'
     's/\%x97/-/ge'
    """
    if (s == None): return ""
    if (not isinstance(s, str)):
        s = "%s" % s
    s = re.sub(r'[\x85]' , '...', s)  # ellipses
    s = re.sub(r'[\x91\x92]', "'", s) # smart quote
    s = re.sub(r'[\x93\x94]', '"', s) # smart quote
    s = re.sub(r'[\x95]', 'o', s)   # special bullet character
    s = re.sub(r'[\xA0]', ' ', s)   # "no break space".  just replacing with space
    s = re.sub(r'[\x96\xE2\x97]', '-', s)   # long dash
    s = re.sub(r'[\xA6]', '|', s)   # special vertical characther
    s = re.sub(r'[\xA9]', '&copy;', s)   # copyright
    s = re.sub(r'[\xAe]', '&reg;', s)   # registered
    s = re.sub(r'[\xbc]', '1/4', s)
    s = re.sub(r'[\xbf]', ' ', s)       # inverted question mark??
    s = re.sub(r'[\xE2\x80\x99]', "", s)   # random chars
    s = re.sub(r'[\xb0]', "&deg;", s)   # Degree character
    s = re.sub(r'[\xd7]', 'x', s)   # special x char
    s = re.sub(r'[\xb1]', '&plusmn;', s)   # special x char

    # Use HTML "micro" entity for 1us, 0.8uV, 100uA, and so on
    s = fix_units(s)
    return s

def fix_units(s):
    """
    Replace common SI units having 'u' prefix to have "micro" HTML entity prefix
    """
    s = re.sub(r'(?<=\d)u(?=[smAVWF]\b)', '&micro;', s)
    return s

def error(message):
    print message
    if (g.opts.waitonerr):
        print "\nHit any key to continue"
        import msvcrt
        msvcrt.getch()
    exit(1)

def warn(message):
    print message

def log_dependency(out_name, dep_name):
    """
    This routine will log the dependency of output file on the provided input file
    as well as the mtime of the input file. This routine should be called before
    reading in the input file, so that if input file gets modified while build 
    is still running, we can be sure the output gets re-built later.
    """
    if g.opts.deptree is None: return

    dep_files = glob.glob(dep_name)
    if len(dep_files) == 0:
        dep_mtime = 0 # special meaning: no files matching
    else:
        dep_mtime = max(map(os.path.getmtime, dep_files))

    # file names in DB are relative to the directory where deptree db file is located
    deptree_dir = os.path.dirname(g.opts.deptree)
    dep_path = os.path.relpath(os.path.abspath(dep_name), deptree_dir)
    out_path = os.path.relpath(os.path.abspath(out_name), deptree_dir)

    g.deptree_depends.append((out_path, dep_path, dep_mtime))

def cleanup_deptree(out_name):
    """
    Delete deptree records associated with a particular output
    """
    if g.opts.deptree is None: return

    # file names in DB are relative to the directory where deptree db file is located
    deptree_dir = os.path.dirname(g.opts.deptree)
    out_path = os.path.relpath(os.path.abspath(out_name), deptree_dir)

    g.deptree_cleanup.append((out_path,))

def deptree_commit():
    if g.opts.deptree is None: return
    db = sqlite3.connect(g.opts.deptree)
    db.executemany("DELETE FROM DEPTREE WHERE DST LIKE ?", g.deptree_cleanup)
    db.executemany("INSERT INTO DEPTREE (DST, SRC, SRC_MTIME) VALUES (?,?,?)", g.deptree_depends)
    db.commit()
    db.close()

def main():
    if (g.opts.dotx != None):
        g.dotx = g.opts.dotx

    build_doc(g.opts)

    deptree_commit()

def chrome(f):
    """
    Call chrome on the current file
    """
    # Need a non-blocking call in case chrome isn't already up.
    _call(r'"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" "%s"' % f, wait=False)

# Set up our argument parser
def setup_parser():
    """
    Set up the argument parser
    """
    parser = _argparse.ArgumentParser(description='Convert markdown to misc formats build collateral')
    parser.add_argument('--chrome', required=False, default=False, action="store_true", help='Launch chrome on the output')
    parser.add_argument('--live', required=False, default=False, action="store_true", help='Set a tag in the output to force live updates')
    parser.add_argument('--dotx', required=False, default=None, help='MS reference docx override.')
    parser.add_argument('--slides', required=False, default=False, action="store_true", help='Set if you wish to build slides')
    parser.add_argument('--template', required=False, default="auto", help='Set the template to use when building the output. If set to "auto" the tool chooses.')
    parser.add_argument('--fmt', required=False, default="html", choices=["docx", "pdf", "html"], help='Outpuf file format')
    parser.add_argument('--nopre', required=False, default=False, action="store_true", help='Disable preprocessor')
    parser.add_argument('--waitonerr', required=False, default=False, action="store_true", help='Stall execution upon an error, require user to acknowledge')
    parser.add_argument('--style', required=False, help='Set the style type')
    parser.add_argument('--perf', required=False, default=False, help='Set to true to look at the latency of each plugin run.')
    parser.add_argument('markdown_files', metavar="*.mmd", type=str, nargs="+", default=None, help='markdown file for conversion.')
    parser.add_argument('--pandoc_args', required=False, default="", help='Arguments to pass on to pandocs (Optional).')
    parser.add_argument('--deptree', metavar="DB_FILENAME", required=False, help='Log dependencies into the sqlite database')
    parser.add_argument('--verbose', required=False, action="store_true", help='Output debugging information')
    parser.add_argument('--fast', required=False, action="store_true", default=False, help='Skip HSD-ES queries')
    parser.add_argument('--email', required=False, action="store_true", default=False, help='Send self an email with the document content')

    return parser

if __name__ == "__main__":
    parser = setup_parser()
    g.opts = parser.parse_args(sys.argv[1:])
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        error("Build tool crashed.  Please contact owner for support.  Error message:\n%s" % str(e))
