# PM_TOOLS

**pm_tools** is a framework for authoring technical documentation in markdown. Basic markdown
capabilities are provided by pandoc. Pm_tools extends pandoc-flavored markdown with "plugin" syntax
that allows embedding:

* [Plantuml](http://plantuml.com) diagrams
* [Graphviz](http://www.graphviz.org) charts
* [Wavedrom](http://wavedrom.com) waveform diagrams
* [Ditaa](http://ditaa.sourceforge.net) diagrams
* [Flowchart.js](http://flowchart.js.org) diagrams
* [Schemdraw](https://cdelker.bitbucket.io/SchemDraw/SchemDraw.html) circuit diagrams
* [Mathjax](https://www.mathjax.org) formulas
* Arbitrary python code output
* Data structure (registers, packets) definitions
* MS Visio diagrams (as zoomable SVG)
* Excel tables (as HTML tables)
* Excel "screenshots" (as PNG)
* csv/tsv
* XSD schemas

Main output format is HTML (single-file), with PDF also supported.

Principles of pm_doc:

* Ability to edit documents fully offline
* Ability to view documents fully offline (Mathjax formulas currently require online connection or
  cached Mathjax)
* Single output document contained in a single HTML file (to make easy to copy / send by e-mail)

# Requirements

* Windows
* Python 2.7
* MS Visio (for embedding Visio diagrams)
* MS Excel (for embedding Excel "screenshots")

# Quick start

Create a file named `hello.md` with the following content:

    <!--
    # Quick start example

    ## Hello, World

    ```plantuml("Communication to the world")
    Pm_doc -> World: Hello there
    ```
    -->

Run from the console:

    python $PM_DOC/scripts/mmd2doc.py hello.md

An overview of all features with the examples is in `doc/Example.mmd`.

# FIXME

The following features are missing from this **pm_doc** distribution:

* Word2mmd conversion
* Test/regressions
* Build/release automation
* Python 3 support
* Linux support
* Firefox and Safari browser support
