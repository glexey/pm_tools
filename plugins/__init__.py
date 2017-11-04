import os

_thisdir = os.path.dirname(os.path.realpath(__file__))
g = globals()
modules = []

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
