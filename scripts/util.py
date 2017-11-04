import os
import sys
try:
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0) # Unbuffered stdout
except:
    pass # maybe we're imported under Jupyter QtConsole or similar

import stat
import re
import subprocess
from shutil import copy2, copystat, Error
import traceback
import time
import collections
import pkg_resources

found_error = False
mypath = os.path.dirname(__file__)

pip_modules = { # map import_name to pip install arguments
        'PyInstaller': 'pyinstaller',
        'xlsxwriter': 'xlsxwriter',
        'excel2img': 'excel2img==1.1',
        'SchemDraw': 'SchemDraw',
        'openpyxl': 'openpyxl==2.4.0',
        'markdown': 'markdown',
        'tabulate': 'tabulate',
        'coverage': 'coverage',
        'psutil': 'psutil',
        'clr': 'pythonnet',
        'bs4': 'bs4',
        'html5lib': 'html5lib==0.999',
        'yaml': 'pyyaml',
        'lxml': 'lxml==3.8.0', # for word2mmd
                               # Using 3.8 as 4.0 doesn't contain Windows binaries
        }

def import_modules(namespace, import_names):
    """
    Import/install modules that are not part of minimal python distribution and
    rely on pip install (from the web)
    """

    pip_todo = []

    if import_names == 'all':
        import_names = pip_modules.keys()

    check_only = (namespace == {})

    for import_name in import_names:
        pip_module = pip_modules[import_name]
        module, version = (re.split(r'[><=]+', pip_module) + [None])[:2]
        # try importing the module, and if failed, add to install list
        try:
            # if namespace is empty, assume we just want to check module
            # version and don't care about actual import
            if check_only:
                mod_version = pkg_resources.get_distribution(module).version
                if version is not None:
                    assert mod_version == version
            else:
                namespace[module] = __import__(import_name)
                if version is not None:
                    assert namespace[module].__version__ == version
        except:
            pip_todo.append(import_name)

    if pip_todo:
        import pip
        for import_name in pip_todo:
            print "Auto-installing %s"%pip_modules[import_name]
            pip.main(['install', pip_modules[import_name], '--disable-pip-version-check'])
            namespace[module] = __import__(import_name)

def error(s):
    """
    Print error string
    """
    print s
    sys.stdout.flush()
    global found_error
    found_error = True

def copytree(src, dst, ignore=None, mtime_dict = None, copy_map = None):
    """
    http://code.activestate.com/lists/python-list/191783/
    """

    names = os.listdir(src)
    if ignore is not None:
        ignored_names = ignore(src, names)
    else:
        ignored_names = set()

    try:
        os.makedirs(dst)
    except OSError, exc:
        if "file already exists" in exc[1]:  # Windows
            pass
        elif "File exists" in exc[1]:        # Linux
            pass
        else:
            raise

    errors = []
    for name in names:
        if name in ignored_names:
            continue
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        if copy_map is not None:
            copy_map[dstname] = srcname
        try:
            if os.path.isdir(srcname):
                copytree(srcname, dstname, ignore, mtime_dict, copy_map)
            else:
                if (os.path.exists(dstname)):
                    # Copy but only if the local file is newer than the dest file
                    srctime = os.stat(srcname).st_mtime
                    dsttime = os.stat(dstname).st_mtime
                    if (srctime > dsttime):
                        copy2(srcname, dstname)
                        # Force files to be writeable
                        os.chmod(dstname, stat.S_IWRITE)
                    if mtime_dict is not None:
                        mtime_dict[dstname] = srctime
                else:
                    copy2(srcname, dstname)
                    # Force files to be writeable
                    os.chmod(dstname, stat.S_IWRITE)
                    if mtime_dict is not None:
                        mtime_dict[dstname] = os.stat(srcname).st_mtime
        except (IOError, os.error), why:
            errors.append((srcname, dstname, str(why)))
        # catch the Error from the recursive copytree so that we can
        # continue with other files
        except Error, err:
            errors.extend(err.args[0])
    try:
        copystat(src, dst)
    except WindowsError:
        # can't copy file access times on Windows
        pass
    except OSError, why:
        errors.extend((src, dst, str(why)))
    if errors:
        raise Error, errors

def call(cmd, verbose=False, **args):
    if (isinstance(cmd, list)):
        if (verbose): print " ".join(cmd)
    else:
        if (verbose): print cmd

    try:
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, **args)
        return result
    except subprocess.CalledProcessError, e:
        # FIXME - log error to log file, e.output
        error("Error running `%s`" % cmd)
        traceback.print_exc()

def get_toolver(fn = None):
    if fn is None:
        fn = os.path.join(mypath, "../version.txt")
    ver = open(fn).read(1000)
    m = re.search(r'(?mi)\bversion\s*=\s*([\d\.]+)', ver)
    if m is None: return '0.0'
    return m.group(1)

def date():
    """
    Return date string
    """
    return time.strftime("%B %d, %Y")

class Tokenizer(object):
    def __init__(self, token_specification):
        self.token = collections.namedtuple('Token', ['typ', 'value', 'line', 'column'])
        self.tok_regex = None
        self.get_token = None
        self.token_spec(token_specification)

    def token_spec(self, ts):
        """
        Update the token specification

        Token spec must be an array of tuples with:
        (NAME, "regex")
        """
        self.tok_regex = '|'.join('(?P<%s>%s)' % pair for pair in ts)

    def tokenize(self, string):
        """
        Generator to walk the code and return tokens

        Used as an iterator.  For example:

          for token in T.tokenize(src_code):

        """
        # TODO: add line number and col number tracking
        for match in re.finditer(self.tok_regex, string, re.DOTALL):
            kind = match.lastgroup
            value = match.group(kind)
            yield self.token(kind, value, 0, 0)

def replace_ext(fn, suffix):
    """
    Convinience function to replace an extension of a given file name with a given suffix
    e.g.1: ('input.html', '.pdf') -> 'input.pdf'
    e.g.2: ('input.html', '_tmp.pdf') -> 'input_tmp.pdf'
    """
    assert '.' in suffix
    return os.path.splitext(fn)[0] + suffix

def fixme_pattern(word):
    """
    It is essential to have same pattern between build.py and mmd2doc.py,
    so keeping pattern construction here
    """
    # **OPEN**: blah
    # OPEN[John Doe]: blah blah
    # **OPEN[John Doe]:** blah blah
    # <mark>OPEN[John Doe]:</mark> blah blah
    # <mark>OPEN[John Doe]</mark>: blah blah
    # OPEN - blah blah blah
    return r'(?i)\b%s\b(?:\\?\[[^]]+\\?\]|</mark>|[ \t]*[:\-\*]+)+[ \t]*(?=\S)'%word

def check_hooks(cfg):
    hooks = [
            {'hook': 'post-merge', 'option': 'pull_tools_on_merge', 'default': True},
            {'hook': 'pre-push',   'option': 'notify_on_push',      'default': True},
            ]
    for hook in hooks:
        src = os.path.join(mypath, hook['hook'])
        dst = os.path.join(cfg['root'], '.git', 'hooks', hook['hook'])
        if not cfg.get(hook['option'], hook['default']):
            if os.path.exists(dst): os.unlink(dst)
            continue
        need_update = True
        if os.path.exists(dst):
            if open(dst).read() == open(src).read():
                need_update = False
        if need_update:
            open(dst, 'w').write(open(src).read())

def get_config(start_dir='.', skip_hooks=False):
    path = os.path.abspath(start_dir)
    while True:
        fn = os.path.join(path, "build.cfg")
        if os.path.exists(fn):
            config = {'root': path}
            execfile(fn, config)
            def norm_paths(k1, k2):
                for dict1 in config[k1]:
                    dict1[k2] = os.path.normpath(dict1[k2])
            norm_paths('build_targets', 'src')
            norm_paths('build_targets', 'dst')
            # Side effect: if we're in the repo, check and populate git hooks
            if not skip_hooks:
                if os.path.isdir(os.path.join(path, '.git')):
                    check_hooks(config)
            return config
        # Go one directory up and check again
        path, rest = os.path.split(path)
        if rest == '':
            # top level dir, bail out
            return None

def get_toolconfig():
    config = {}
    for fn in ['tools.cfg', 'tools.ovrd.cfg']:
        ffn = os.path.join(mypath, '..', fn)
        if not os.path.isfile(ffn): continue
        execfile(ffn, config)
    return config

def src2dest(srcname, targets):
    # map given source file/dir name to "distrib" file/dir name(s),
    # according to provided targets list.
    # targets is a list of src:dst mappings from build.cfg
    dst_list= []
    src = os.path.normpath(srcname)
    for t in targets:
        s, d = [os.path.normpath(x) for x in (t['src'], t['dst'])]
        if src.lower().startswith(s.lower()):
            # Careful with case: see unittests
            answer = t['dst'] + src[len(s):]
            dst_list.append(os.path.normpath(answer))
        elif src.lower().startswith(d.lower()):
            # Given path already in dest
            answer = t['dst'] + src[len(d):]
            dst_list.append(os.path.normpath(answer))
    return dst_list

def src2dest_unittest():
    t = [
            {'src': 'src/Foo',         'dst': 'dist/src/Foo'},
            {'src': 'src/Foo/bar.txt', 'dst': 'dist/foobar.txt'},
            ]
    assert src2dest('src/foo/Dir/Abc.def', t) == ['dist\\src\\Foo\\Dir\\Abc.def']
    assert src2dest('src/foo/bar.txt', t) == ['dist\\src\\Foo\\bar.txt', 'dist\\foobar.txt']
    assert src2dest('dist/src/foo/bar.txt', t) == ['dist\\src\\Foo\\bar.txt']
    assert src2dest('src', t) == []

def which(program):
    # https://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None

def locate_java():
    import _winreg as wr
    aReg = wr.ConnectRegistry(None, wr.HKEY_LOCAL_MACHINE)
    # http://stackoverflow.com/a/3930575/1924207
    paths = [r'JavaSoft\Java Runtime Environment', r'Wow6432Node\JavaSoft\Java Runtime Environment',
            r'JavaSoft\Java Development Kit', r'Wow6432Node\JavaSoft\Java Development Kit']
    for p in paths:
        try:
            aKey = wr.OpenKey(aReg, r'Software\%s'%p)
        except WindowsError:
            continue
        ver = str(wr.QueryValueEx(aKey, r'CurrentVersion')[0])
        aKey = wr.OpenKey(aReg, r'Software\%s\%s'%(p, ver))
        javahome = str(wr.QueryValueEx(aKey, r'JavaHome')[0])
        return javahome + r'\bin\java.exe'
    # Try PATH
    java_exe = which('java.exe')
    if java_exe:
        return java_exe
    raise Exception("Java not found")

# If run as a script, check/download all non-standard modules
if __name__ == "__main__":
    import_modules({}, "all")
    if '--test' in sys.argv:
        src2dest_unittest()
