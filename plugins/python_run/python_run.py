import os
import sys
import tempfile
from subprocess import check_output

class PythonrunPlugin(object):

    def __init__(self, preprocessor):
        self.pp = preprocessor
        self.token = "python_run"
        self.pp.register_plugin(self)
        self.received = {} # Populated by plugins/__init__.py receiving ext paths from other plugins
                           # received['from'] = [messages]

    def process(self, code, output="markdown", source=False, name=None, div_style=None):
        """
        Execute given python code and capture the output

        Ensure support of full pre-processing
        """
        if name is None:
            f = tempfile.NamedTemporaryFile(mode='w', delete=False)
        else:
            # User wants to name the file for subsequent use
            f = open("%s/auto/"%self.pp.dirs[-1]+name+".py", "w")
        code = code.strip(' \t\n\r')
        if code == '' and name is not None:
            fpath, rpath = self.pp.get_asset(name + ".py", True)
            code = open(fpath).read()
        f.write(code)
        f.close()
        new_env = os.environ.copy()
        # Automatically set up a search path to search in this order:
        #  1. Tools scripts dir
        #  2. Plugins-exported paths
        #  3. markdown doc dir
        #  4. ./assets
        #  5. ../assets
        #  6. ../../assets
        #  etc.
        #
        #  Stop at repo_root
        paths = []
        paths.append(self.pp.toolpath('scripts'))
        for _from, msglist in self.received.iteritems():
            for msg in msglist:
                paths.append(msg)
        paths.append(os.path.split(self.pp.fname)[0])

        # Start with the path of the file we are working on, add its assets subdir.
        curdir = paths[-1]
        while (True):
            if (os.path.exists(os.path.join(curdir, "assets"))):
                paths.append(os.path.join(curdir, "assets"))
            if curdir == self.pp.repo_root: break # doc repo root
            parent = os.path.abspath(os.path.join(curdir, ".."))
            if parent == curdir: break # filesystem root (we're outside doc repo)
            curdir = parent
        
        new_env['PYTHONPATH'] = ";".join(paths)
        result = check_output([sys.executable, f.name], env=new_env, cwd=os.path.dirname(f.name))
        if name is None:
            os.remove(f.name)
        ans = ""
        if (source):
            # Include python source in the output
            ans += "```python\n%s\n```\n"%code
        if output == "parse" or output == "markdown":
            # re-parse the output (useful for simple table generation)
            # Insert as new tokens into our array to get the full pre-processing.
            self.pp.tokens = [t for t in self.pp.tokenize(result, self.pp.token_specification)] + self.pp.tokens
        elif output == "verbatim":
            # Output in a frame as if python was writing to console
            ans += "```\n%s\n```\n"%result
        else:
            raise ValueError("Option output='%s' is not supported, valid choices are: markdown, verbatim"%output)

        return ans

new = PythonrunPlugin
