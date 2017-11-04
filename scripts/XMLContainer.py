"""
General purpose library for importing general XML into a container object tree
for easy python inspection / manipulation.
"""
import xml.etree.cElementTree as ET
import re
import sys
import argparse
import string
import os
import copy
import textwrap
import traceback
from operator import itemgetter, attrgetter
from StringIO import StringIO

debug = False
exclude_namespace = True

global_key_index = 0

class XMLContainer(object):
    def __init__(self, container_tags={}, suppress_errors=False, unique_names=True, order_tag="xml_order"):
        """
        Anything marked as a container tag is grouped into a parent container

        Container tags format:

        tags = {
            'register': {'container': 'registers', 'access_key': 'name', 'index': 'index'},
            'field': {'container': 'fields', 'access_key': 'name', 'index': 'index'},
            'enum': {'container': None, 'access_key': 'name', 'index': 'index'},
        }

        container: tells the tool to instantiate as a list and if needed add a tag to wrap it
        access_key: tells the tool how to build the attribute name that points to the child container
        index: tells the tool what to call the attribute that describes the index of this instance.

        Sample usage:

        import XMLContainer
        c = XMLContainer.XMLContainer(tags)
        c.parse_xml(r"pmu_crif.xml")
        """
        self.container_tags = container_tags
        self.root = Container()
        self.exclude_list = None
        self.exclude_valid = False
        self.suppress_errors = suppress_errors
        self.unique_names = unique_names
        # Global ordering id for sorting in order of XML.
        self.global_order_id = 0
        self.order_tag = order_tag

    def exclude(self, parent, child, value):
        """
        Exclude any objects that match the provided parameters
        """
        self.exclude_valid = True
        if self.exclude_list == None:
            self.exclude_list = []

        self.exclude_list.append([parent, child, re.compile(value)])

    def add_xml(self, xml):
        self.parse_xml(xml)

    def parse_str(self, s):
        """
        Parse XML and build a dict tree of the result using
        generic "Container" objects that describe that tree.

        This tree allows for easy user inspection of the XML

        USAGE:
        d = XML2Dict(r"foo.xml")
        """
        global debug
        xmlroot = ET.fromstring(s)

        self.populate_children(xmlroot, self.root)
        if (debug): 
            print "XML imported"

    def parse_xml(self, xml):
        """
        Parse XML and build a dict tree of the result using
        generic "Container" objects that describe that tree.

        This tree allows for easy user inspection of the XML

        USAGE:
        d = XML2Dict(r"foo.xml")
        """
        global debug
        xmlfile = find_file(xml, sys.path)
        if (debug): 
            sys.stdout.write("Parsing %s..." % xmlfile)
            sys.stdout.flush()
        x = ET.parse(xmlfile)
        if (debug): 
            sys.stdout.write("XML Parsed...")
            sys.stdout.flush()

        xmlroot = x.getroot()

        self.populate_children(xmlroot, self.root)
        if (debug): 
            print "XML imported"

    def populate_children(self, root, container):
        """
        Recursive function designed to build a container object
        tree to match the incoming XML tree.  

        Flatten xml attribute lists as if they are children

        If the child has a 'key' property, that is used as the handle for it.
        """
        if (len(root.getchildren()) == 0):
            self.populate_items(root.items(), container)
            if (root.text != None):
                # This object has data with no tag.  E.g., for the following
                #  <object name="object_name">data</object>
                # root.text is "data"
                # We want to capture this information, but where do we put it?
                # Save in "__value__" attribute, implement value() method to extract.
                container.__dict__["__value__"] = root.text
        else:
            for child in root.getchildren():
                child_tag = clean_namespace(child.tag)
                if (self.container_tags.has_key(child_tag)):
                    # this one is special.  Make sure we isolate it into its own # group
                    container_key = self.container_tags[child_tag]['container']
                    access_key = self.container_tags[child_tag]['access_key']
                    if (container_key != None and not container.__dict__.has_key(container_key)):
                        # Create our special container for these types of objects
                        # to isolate them from other attributes
                        container.__dict__[container_key] = Container()
                    name = self.get_access_key(child, access_key)
                    name = clean_key(name)

                    if (self.exclude_valid):
                        exclude = False
                        for e in self.exclude_list:
                            if (child.tag == e[0] and access_key == e[1]):
                                m = e[2].search(name)
                                if (m != None):
                                    exclude = True
                                    break
                        if (exclude):
                            continue

                    if (container_key != None):
                        if (container.__dict__[container_key].__dict__.has_key(name)):
                            if (self.unique_names):
                                name = self._get_unique_name(container.__dict__[container_key], name)
                            elif not self.suppress_errors:
                                print "-E- Overwriting '%s' (within %s) due to repeat definition with the same name." % (name, container_key)
                        container.__dict__[container_key].__dict__[name] = Container()
                        container.__dict__[container_key].__dict__[name].__dict__[self.order_tag] = self.global_order_id
                        self.global_order_id += 1
                        self.populate_children(child, container.__dict__[container_key].__dict__[name])
                    else:
                        if (container.__dict__.has_key(name)):
                            # This name has already been declared.
                            if (self.unique_names):
                                # User wants to declare unique names, let's do that.
                                name = self._get_unique_name(container, name)
                            elif not self.suppress_errors:
                                print "-E- Overwriting '%s' (within %s) due to repeat definition with the same name." % (name, container_key)
                        container.__dict__[name] = Container()
                        container.__dict__[name].__dict__[self.order_tag] = self.global_order_id
                        self.global_order_id += 1
                        self.populate_children(child, container.__dict__[name])

                elif (len(child.getchildren()) == 0):
                    if (len(child.items()) > 0):
                        name = clean_key(child.tag)
                        container.__dict__[name] = Container()
                        self.populate_items(child.items(), container.__dict__[name])
                        # This object has data with no tag.  E.g., for the following
                        #  <object item="val">data</object>
                        # root.text is "data"
                        # We want to capture this information, but where do we put it?
                        # Save in "__value__" attribute, implement value() method to extract.
                        container.__dict__[name].__dict__["__value__"] = child.text
                    else:
                        # This is a dead end.  Populate the attribute
                        container.__dict__[clean_key(child.tag)] = child.text
                else:
                    # There is more below, keep searching
                    name = clean_key(child.tag)
                    container.__dict__[name] = Container()
                    self.populate_children(child, container.__dict__[name])

            self.populate_items(root.items(), container)

    def _get_unique_name(self, container, name):
        """
        Given a key to a container, make a unique name
        """
        # Modify key to ensure it is unique
        unique_name = name
        i = 1
        while (container.__dict__.has_key(unique_name)):
            unique_name = "%s_%d" % (name, i)
            i += 1
        return unique_name

    def populate_items(self, items, container):
        """
        Walk the item list, as if it was a child list.  
        But we know each item is a dead end
        """
        for item in items:
            tag = item[0]
            value = item[1]
            container.__dict__[clean_key(tag)] = value

    def get_access_key(self, xmlroot, key):
        """
        Search for 'key' in the xmlroot.  This will be used as the access method
        for the object.
        """
        if (len(xmlroot.getchildren()) > 0):
            for child in xmlroot.getchildren():
                if child.tag == key:
                    if (child.text == None):
                        return ""
                    else:
                        return clean_namespace(child.text)

        if (len(xmlroot.items()) > 0):
            for item in xmlroot.items():
                if item[0] == key:
                    if (item[1] == None):
                        return ""
                    else:
                        return clean_namespace(item[1])

        #if (key == None):
        #    # Make up a key if none is given.
        #    global global_key_index
        #    global_key_index += 1
        #    return "item_%d" % global_key_index
        raise Exception("Expected %s in %s but didn't find it" % (key, xmlroot))

def clean(text):
    """
    unescape text and convert integers and hex to int type.
    """
    if (text == None):
        return ""

    if (not isinstance(text, str)):
        return text

    if (text.isdigit()):
        return int(text)

    if (text.isalnum()):
        if (text.startswith("0x")):
            try:
                return int(text, 16)
            except:
                return text

    s = re.sub(r"\s+", " ", text)
    s = unescape(text).strip()
    s = s.encode("ascii", "replace")
    return s

def clean_key(text):
    """
    remove special chars from the key

    Need to replace numbers with alphanum
    """
    if (text == None):
        return ""

    s = text.replace("/", "_")
    s = text.replace(".", "_")

    if s.isdigit():
        s = "__%s__" % s
    return clean_namespace(s)

def clean_namespace(text):
    """
    If namespace is excluded, remove it from the access key
    """
    if (not exclude_namespace):
        return text

    index = text.find("}")
    if (index > 0):
        return text[index+1:]
    else:
        return text

def unescape(s):
    """
    Replace special characters "&amp;", "&lt;" and "&gt;" with normal characters
    """
    if (type(s) != str):
        return s

    if (s.find("&") >= 0):
        s = s.replace("&lt;", "<")
        s = s.replace("&gt;", ">")
        s = s.replace("&amp;", "&")

    return s

def find_file(name, path):
    """
    Find the file named path in the sys.path.
    Returns the full path name if found, croaks if not found
    """
    if os.path.isfile(name):
        return name

    for dirname in path:
        filepath = os.path.join(dirname, name)
        if os.path.isfile(filepath):
            return filepath

    raise Exception("Could not find %s in the search path" % name)

class Container(object):
    """
    Generic container class for exploring the XML
    """
    def clone(self):
        x = Container()
        for k in self.__dict__.keys():
            if (isinstance(self.__dict__[k], Container)):
                x.__dict__[k] = self.__dict__[k].clone()
            else:
                x.__dict__[k] = self.__dict__[k]
        return x

    def __repr__(self):
        """
        Generic string to represent this class object
        """
        s = ""
        maxwidth = 0
        for k in self.keys():
            maxwidth = max(maxwidth, len(k))

        fmt = "%%-%ds: %%s\n" % maxwidth
        # single line first
        for k in sorted(self.keys()):
            obj_str = repr(self.__dict__[k])
            if (obj_str.find("\n") >= 0):
                continue
            else:
                s += fmt % (k, self.__dict__[k])
        if self.__dict__.has_key("__value__"):
            s += "(value: %s)\n" % self.__dict__["__value__"]

        # Now multi-line
        fmt = "%%-%ds\n%%s" % maxwidth
        for k in sorted(self.keys()):
            obj_str = repr(self.__dict__[k])
            if (obj_str.find("\n") >= 0):
                # Multiline, indent it
                obj_str = indent(obj_str, 4)
                obj_str = "  L " + obj_str[4:]
                s += fmt % (k, obj_str)

        s += "\n"
        return s

    def keys(self):
        """
        Pretend this is a dict
        """
        klist = [x for x in self.__dict__.keys() if x != "__value__"]
        return klist

    def __getattribute__(self, item):
        if (item == "__dict__"):
            return object.__getattribute__(self, item)
        else:
            # Clean xml text on demand.  This is for performance.
            return clean(object.__getattribute__(self, item))

    def __getitem__(self, item):
        '''
        Pretend this is a dict
        '''
        return self.__dict__[item]

    def __setitem__(self, key, value):
        '''
        Pretend this is a dict
        '''
        self.__dict__[key] = value

    def __delitem__(self, key):
        '''
        Pretend this is a dict. remove this item.
        '''
        del(self.__dict__[key])

    def get(self, k):
        """
        look up object attribute using a string
        """
        return self.__dict__[k]

    def set(self, k, value):
        """
        set object attribute using a string
        """
        self.__dict__[k] = value

    def value(self):
        """
        Some objects have a value with no tag to categorize it.
        """
        return self.__dict__["__value__"]

    def has_attr(self, k):
        """
        return true if we have the key
        """
        return self.__dict__.has_key(k)

    def has_key(self, k):
        """
        return true if we have the key
        """
        return self.__dict__.has_key(k)

    def search(self, regex, start=True):
        self.find(regex, start)

    def find(self, regex, start=True):
        """
        Search all keys, fields, and descriptions for a match of this text.
        Search is recursive.  If anywhere in the child tree there is a 
        match of the regex, return that field upstream and the calling
        parent will print the full depth.
        """
        string_search = re.compile(regex)

        match_list = []
        for k in self.keys():
            m = string_search.search(str(k))
            if (m != None):
                match_list.append(k)
            elif (not isinstance(self.__dict__[k], Container)):
                s = self.__dict__[k]
                if (isinstance(s, unicode)):
                    s = s.encode("ascii", "replace")
                if (not isinstance(s, str)):
                    s = str(s)
                m = string_search.search(s)
                if (m != None):
                    match_list.append(k)
            else:
                # Search children for a match
                child_list = self.__dict__[k].find(regex, start=False)
                for child in child_list:
                    match_list.append("%s.%s" % (k, child))

        if (start == True):
            for m in match_list:
                print m
        else:
            return match_list

    def delete(self, attr):
        del(self.__dict__[attr])

    def sorted_list(self, *attrs):
        """
        Return a sorted list of objects.  Flatten any arrays.
        Sorted by attribute of user's choosing
        If none is sent, none is sorted.
        """
        # No sorting, just return in random order
        raw_list = []
        for k in self.keys():
            raw_list.append(self.__dict__[k])

        if (len(attrs) == 0):
            return raw_list

        sorted_list = sorted(raw_list, key=attrgetter(*attrs))
        return sorted_list

class CRIFContainer(XMLContainer):
    def __init__(self, container_tags={}, suppress_errors=False, unique_names=True, order_tag="xml_order"):
        # identical to the XML container object, but this
        # one has pre-defined tags for register space partitioning
        self.container_tags = {
            'registerFile': {'container': 'registerFiles', 'access_key': 'name'},
            'register': {'container': 'registers', 'access_key': 'name'},
            'field': {'container': 'fields', 'access_key': 'name'},
        }
        self.root = Container()
        self.exclude_list = None
        self.exclude_valid = False
        # Global ordering id for sorting in order of XML.
        self.global_order_id = 0
        self.order_tag = order_tag

class FUSEContainer(XMLContainer):
    def __init__(self, container_tags={}, suppress_errors=False, unique_names=True, order_tag="xml_order"):
        # identical to the XML container object, but this
        # one has pre-defined tags for fuse rdl partitioning
        self.container_tags = {
            'fuse': {'container': None, 'access_key': 'name'},
            'property': {'container': None, 'access_key': 'name'},
            'enum': {'container': None, 'access_key': 'name'},
        }
        self.root = Container()
        self.exclude_list = None
        self.exclude_valid = False
        # Global ordering id for sorting in order of XML.
        self.global_order_id = 0
        self.order_tag = order_tag

class TAPContainer(XMLContainer):
    def __init__(self, container_tags={}, suppress_errors=False, unique_names=True, order_tag="xml_order"):
        # identical to the XML container object, but this
        # one has pre-defined tags for tap xml partitioning
        self.container_tags = {
            'sTap': {'container': 'taps', 'access_key': 'StapName'},
            'TDR': {'container': None, 'access_key': 'ID'},
            'BitField': {'container': None, 'access_key': 'Label'},
            'Instruction': {'container': None, 'access_key': 'Name'},
        }
        self.root = Container()
        self.exclude_list = None
        self.exclude_valid = False
        # Global ordering id for sorting in order of XML.
        self.global_order_id = 0
        self.order_tag = order_tag

    def fixup(self):
        """
        Custom routine for replacing Tap container TDR ID's with instruction
        names
        """
        self.recursive_fix(self.root)

    def recursive_fix(self, root, path=[]):
        for k in root.keys():
            if (isinstance(root[k], Container)):
                self.recursive_fix(root[k], path + [k])
            if (k == "TDRs"):
                # We want to replace all TDRs children ID's with their parent
                # sTapInstructions names
                for tdr_id in root[k].keys():
                    name = None
                    name = self.find_tdr_name(int(tdr_id), root['sTapInstructions'].sorted_list(), path + [k])
                    if (name == None):
                        # Replace with Name
                        name = root[k][tdr_id].Name

                    if (name == None):
                        raise Exception("Unable to find name for %s" % (".".join([path + [k]])))

                    # Make it legal
                    name = name.replace(" ", "_")
                    if (root.has_key(name)):
                        raise Exception("Found repeat name of %s in TDRs" % name)

                    root[k].__dict__[name] = root[k].__dict__[tdr_id]
                    del root[k].__dict__[tdr_id]

    def find_tdr_name(self, ID, instructions, path):
        """
        Walk a list of instructions, find a match between the instruction and the ID
        """
        tested = {}
        for instr in instructions:
            tested[instr.Name] = instr.MappedTDRID
            if (ID == instr.MappedTDRID):
                return instr.Name

        #print ("-W- Cound not find instruction name for ID %s at %s.  Ignoring." % (ID, ".".join(path)))
        return None

def indent(lines, column):
    """
    Insert spaces to shift this string right by the column count
    """
    columns = " " * column
    output_string = ""

    if (not isinstance(lines, list)):
        lines = lines.splitlines()

    for line in lines:
        output_string += columns + line + "\n"

    return output_string
