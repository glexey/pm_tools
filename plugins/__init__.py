import os

_thisdir = os.path.dirname(os.path.realpath(__file__))
g = globals()
modules = []
process_mismatch_callbacks = []
preprocess_callbacks = []
postprocess_soup_callbacks = []
postprocess_html_callbacks = []

pkgnames = [x for x in os.listdir(_thisdir) if os.path.isfile(os.path.join(_thisdir, x, '__init__.py'))]

for pkgname in pkgnames:
    pkg = __import__(pkgname, globals(), locals(), fromlist=[pkgname])
    mod = getattr(pkg, pkgname)
    g[pkgname] = mod
    modules.append(mod)

def initialize(preprocessor):
    token2plugin = {}
    for mod in modules:
        classes = mod.new if hasattr(mod.new, '__iter__') else [mod.new]
        for cls in classes:
            try:
                inst = cls(preprocessor)
            except:
                print "While initializing", mod
                raise
            if inst.token in token2plugin:
                raise Exception("Token '%s' already used"%inst.token)
            token2plugin[inst.token] = inst
    # populate inter-plugin dependencies
    for mod in modules:
        if not hasattr(mod, 'require_plugins'): continue
        for name in mod.require_plugins:
            try:
                setattr(mod, name, token2plugin[name])
            except KeyError:
                raise Exception("While resolving required plugin modules for %s: '%s' not found"%(pkgname, name))
    # "send" inter-plugin "messages"
    for inst in token2plugin.values():
        if not hasattr(inst, 'send'): continue
        for whereto, what in inst.send.iteritems():
            to = token2plugin[whereto]
            to.received[inst.token] = what
    # collect optional callbacks
    for inst in token2plugin.values():
        if hasattr(inst, 'process_mismatch'):
            process_mismatch_callbacks.append(inst.process_mismatch)
        if hasattr(inst, 'preprocess'):
            preprocess_callbacks.append(inst.preprocess)
        if hasattr(inst, 'postprocess_html'):
            postprocess_html_callbacks.append(inst.postprocess_html)
        if hasattr(inst, 'postprocess_soup'):
            postprocess_soup_callbacks.append(inst.postprocess_soup)

# process_mismatch() gets called for the "regular text", i.e. everything
# that is otherwise not explicitly purposed
def process_mismatch(s):
    for func in process_mismatch_callbacks:
        s = func(s)
    return s

# preprocess gets called before pandoc processing
def preprocess(s):
    for func in preprocess_callbacks:
        s = func(s)
    return s

# postprocess_html gets called after pandoc processing on the HTML string
def postprocess_html(s):
    for func in postprocess_html_callbacks:
        s = func(s)
    return s

# postprocess_soup gets called after pandoc processing on the bs4 soup object
def postprocess_soup(soup):
    for func in postprocess_soup_callbacks:
        func(soup)
